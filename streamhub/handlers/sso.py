"""OpenID Connect login: authorization code flow with PKCE.

The issuer and every endpoint it publishes must be HTTPS (unless `insecure-http`, for development), and
the discovery document must name the configured issuer. ID tokens are verified with the provider's
signing keys (JWKS) and an algorithm allowlist, then `iss`, `aud`, `azp`, `exp` and `nonce` are checked.
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from urllib.parse import urlencode

import tornado.httpclient
import tornado.web

from streamhub import auth
from streamhub.config import OIDC_ALGORITHMS
from streamhub.handlers.base import BaseHandler, safe_next

log = logging.getLogger(__name__)

FLOW_COOKIE = "oidc"
FLOW_MINUTES = 10
DISCOVERY_SECONDS = 3600
JWKS_REFRESH_SECONDS = 60  # an unknown key ID refetches the JWKS at most this often (key rotation)
ENDPOINTS = ("authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri")


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def check_id_token(claims, issuer, client_id, nonce, now=None):
    """Raises ValueError unless the ID token was issued by `issuer`, for `client_id`, for this login.

    The signature is checked first, by OidcProvider.verify_id_token.
    """
    now = now or time.time()
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    if claims.get("iss") != issuer:
        raise ValueError(f"unexpected issuer {claims.get('iss')!r}")
    if client_id not in audiences:
        raise ValueError("the ID token is for another client")
    if "azp" in claims and claims["azp"] != client_id:
        raise ValueError("the ID token was issued to another party (azp)")
    if len(audiences) > 1 and "azp" not in claims:
        raise ValueError("an ID token with several audiences needs azp")
    if float(claims.get("exp", 0)) < now - 60:
        raise ValueError("the ID token has expired")
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValueError("nonce mismatch")


def as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def same_issuer(a, b):
    return str(a or "").rstrip("/") == str(b or "").rstrip("/")


class OidcProvider:
    """Discovery document (cached for an hour) and signing keys (refetched when a new key ID appears)."""

    def __init__(self, settings, http_client):
        self.settings = settings
        self.http = http_client
        self._discovery = None
        self._fetched = 0.0
        self._keys = {}           # key ID -> PyJWK
        self._keys_fetched = None

    @property
    def config(self):
        return self.settings.oidc

    def check_url(self, url, what):
        """`url`, or ValueError when it is missing or not HTTPS (http:// only with `insecure-http`)."""
        if not isinstance(url, str) or not url:
            raise ValueError(f"the provider did not publish {what}")
        if not url.startswith("https://") and not (self.config.get("insecure-http") and url.startswith("http://")):
            raise ValueError(f"{what} must be https: {url}")
        return url

    async def fetch_json(self, url, what, **kwargs):
        """Fetch JSON without following redirects (a redirect could leave HTTPS)."""
        response = await self.http.fetch(self.check_url(url, what), follow_redirects=False, **kwargs)
        return json.loads(response.body)

    async def discovery(self):
        if self._discovery is None or time.monotonic() - self._fetched > DISCOVERY_SECONDS:
            issuer = self.config["issuer"]
            document = await self.fetch_json(issuer.rstrip("/") + "/.well-known/openid-configuration",
                                             "the discovery document", request_timeout=10)
            if not same_issuer(document.get("issuer"), issuer):
                raise ValueError(f"the discovery document names issuer {document.get('issuer')!r}, not {issuer!r}")
            for key in ENDPOINTS:
                if key in document or key != "userinfo_endpoint":  # userinfo is optional
                    self.check_url(document.get(key), key)
            self._discovery, self._fetched = document, time.monotonic()
        return self._discovery

    async def signing_key(self, token):
        """The provider key that signed `token`. An unknown key ID refetches the JWKS (key rotation)."""
        import jwt

        kid = jwt.get_unverified_header(token).get("kid")
        stale = self._keys_fetched is None or time.monotonic() - self._keys_fetched > JWKS_REFRESH_SECONDS
        if kid not in self._keys and stale:
            discovery = await self.discovery()
            data = await self.fetch_json(discovery["jwks_uri"], "jwks_uri", request_timeout=10)
            keys = [k for k in data.get("keys", []) if isinstance(k, dict) and k.get("use", "sig") == "sig"]
            usable = jwt.PyJWKSet.from_dict({"keys": keys}).keys if keys else []
            self._keys = {key.key_id: key for key in usable}
            self._keys_fetched = time.monotonic()
        if kid is None and len(self._keys) == 1:
            return next(iter(self._keys.values()))
        if kid not in self._keys:
            raise ValueError(f"the ID token was signed with an unknown key {kid!r}")
        return self._keys[kid]

    async def verify_id_token(self, token, nonce):
        """The claims of a correctly signed ID token for this client and this login; ValueError otherwise."""
        import jwt

        discovery = await self.discovery()
        client_id = self.config["client-id"]
        algorithms = list(self.config.get("algorithms") or OIDC_ALGORITHMS)
        try:
            key = await self.signing_key(token)
            claims = jwt.decode(token, key=key.key, algorithms=algorithms, audience=client_id,
                                issuer=discovery["issuer"], leeway=60,
                                options={"require": ["iss", "aud", "exp", "iat", "sub"]})
        except jwt.PyJWTError as exc:
            raise ValueError(f"invalid ID token: {exc}") from exc
        check_id_token(claims, discovery["issuer"], client_id, nonce)
        return claims


class _OidcHandler(BaseHandler):
    """OIDC routes exist only when `oidc` is configured (404 otherwise)."""

    def prepare(self):
        super().prepare()
        if not self.hub.settings.oidc:
            raise tornado.web.HTTPError(404)

    @property
    def config(self):
        return self.hub.settings.oidc

    def redirect_uri(self):
        return self.config.get("redirect-uri") or f"{self.request.protocol}://{self.request.host}/login/oidc/callback"


class OidcLoginHandler(_OidcHandler):
    """Start the login: remember state, nonce and PKCE verifier, then redirect to the provider."""

    async def get(self):
        try:
            discovery = await self.hub.oidc.discovery()
        except (ValueError, KeyError, OSError, tornado.httpclient.HTTPClientError) as exc:
            log.error("OpenID provider discovery failed: %s", exc)
            self.set_status(502)
            self.render("login.html", target="/", login_status=4, needs_setup=False,
                        oidc_label=self.config.get("label") or "Single sign-on")
            return
        flow = {"state": secrets.token_urlsafe(24), "nonce": secrets.token_urlsafe(24),
                "verifier": secrets.token_urlsafe(48), "next": safe_next(self.get_argument("next", "/"))}
        self.set_signed_cookie(FLOW_COOKIE, json.dumps(flow), expires_days=FLOW_MINUTES / 1440,
                               httponly=True, samesite="Lax", secure=self.request.protocol == "https")
        query = {
            "response_type": "code",
            "client_id": self.config["client-id"],
            "redirect_uri": self.redirect_uri(),
            "scope": " ".join(self.config.get("scopes") or ["openid", "profile", "email"]),
            "state": flow["state"],
            "nonce": flow["nonce"],
            "code_challenge": b64url(hashlib.sha256(flow["verifier"].encode()).digest()),
            "code_challenge_method": "S256",
        }
        self.redirect(discovery["authorization_endpoint"] + "?" + urlencode(query))


class OidcCallbackHandler(_OidcHandler):
    """The provider redirects here with a code: exchange it, check the ID token, map groups, log in."""

    async def get(self):
        raw = self.get_signed_cookie(FLOW_COOKIE, max_age_days=FLOW_MINUTES / 1440)
        self.clear_cookie(FLOW_COOKIE)  # single use: a replayed callback finds no flow
        try:
            flow = json.loads(raw) if raw else None
            if flow is None:
                raise ValueError("the login took too long or cookies are blocked")
            if self.get_argument("error", ""):
                raise ValueError(f"{self.get_argument('error')}: {self.get_argument('error_description', '')}")
            if not hmac.compare_digest(self.get_argument("state", ""), flow["state"]):
                raise ValueError("state mismatch")
            name, groups = await self._identity(flow)
        except (ValueError, KeyError, OSError, tornado.httpclient.HTTPClientError) as exc:
            auth.audit.warning("OIDC login failed from %s: %s", self.request.remote_ip, exc)
            self._refuse()
            return
        user = auth.sso_user(name, "oidc", groups, self.hub.settings, self.hub.catalog)
        if user is None:
            auth.audit.warning("OIDC user '%s' refused: no group mapping matched", name)
            self._refuse(3)
            return
        self.set_session(user)
        self.redirect(flow["next"])

    def _refuse(self, status=2):
        self.set_status(401 if status == 2 else 403)
        self.render("login.html", target="/", login_status=status, needs_setup=False,
                    oidc_label=self.config.get("label") or "Single sign-on")

    async def _identity(self, flow):
        """(user name, groups) from the ID token, completed by the userinfo endpoint."""
        discovery = await self.hub.oidc.discovery()
        client_id = self.config["client-id"]
        form = {"grant_type": "authorization_code", "code": self.get_argument("code"),
                "redirect_uri": self.redirect_uri(), "code_verifier": flow["verifier"], "client_id": client_id}
        secret = self.hub.settings.oidc_client_secret
        basic = secret and self.config.get("token-auth", "basic") == "basic"
        if secret and not basic:
            form["client_secret"] = secret
        provider = self.hub.oidc
        tokens = await provider.fetch_json(
            discovery["token_endpoint"], "token_endpoint", method="POST", body=urlencode(form), request_timeout=15,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            auth_username=client_id if basic else None, auth_password=secret if basic else None)
        claims = await provider.verify_id_token(tokens["id_token"], flow["nonce"])
        if discovery.get("userinfo_endpoint") and tokens.get("access_token"):
            extra = await provider.fetch_json(
                discovery["userinfo_endpoint"], "userinfo_endpoint", request_timeout=15,
                headers={"Authorization": f"Bearer {tokens['access_token']}", "Accept": "application/json"})
            if extra.get("sub") == claims.get("sub"):  # same subject only; the ID token wins on conflicts
                claims = {**extra, **claims}
        claim = self.config.get("username-claim", "preferred_username")
        name = claims.get(claim) or claims.get("email") or claims.get("sub")
        if not name:
            raise ValueError("the ID token has no user name")
        return str(name), as_list(claims.get(self.config.get("groups-claim", "groups")))
