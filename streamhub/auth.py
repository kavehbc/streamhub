"""Passwords, sessions, SSO group mapping, LDAP, roles and access rules."""
import base64
import binascii
import functools
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import deque

log = logging.getLogger(__name__)
audit = logging.getLogger("streamhub.audit")

ROLES = {"guest": 0, "user": 1, "manager": 2, "admin": 3}
# What each role may do, for the admin page's role selects.
ROLE_HELP = {"guest": "Guest: opens the boards it is given",
             "user": "User: opens the boards it is given",
             "manager": "Manager: also starts, stops and monitors apps on the admin page",
             "admin": "Admin: everything, including apps, users and settings"}
SSO_SOURCES = ("oidc", "ldap")
HASH_PREFIX = "pbkdf2_sha256"
HASH_ITERATIONS = 600_000


def hash_password(password, iterations=None):
    """`pbkdf2_sha256$<iterations>$<salt>$<digest>`, as printed by `streamhub passwd`.

    Deliberately slow (about half a second): call it from an executor, not on the event loop.
    """
    iterations = iterations or HASH_ITERATIONS
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "$".join([HASH_PREFIX, str(iterations), base64.b64encode(salt).decode(),
                     base64.b64encode(digest).decode()])


def _split_hash(stored):
    """(iterations, salt, digest) of a well-formed hash; raises ValueError otherwise."""
    prefix, iterations, salt, digest = str(stored).split("$")
    if prefix != HASH_PREFIX or int(iterations) < 1:
        raise ValueError("not a pbkdf2_sha256 hash")
    try:
        return int(iterations), base64.b64decode(salt, validate=True), base64.b64decode(digest, validate=True)
    except binascii.Error as exc:
        raise ValueError("bad base64") from exc


def is_hashed(stored):
    """True when `stored` is a well-formed password hash (and so not a raw password)."""
    try:
        _split_hash(stored)
        return True
    except ValueError:
        return False


_warned_plaintext = set()


def verify_password(stored, given, username=""):
    """Constant-time check of `given` against a stored hash. Raw (plain-text) passwords are refused."""
    try:
        iterations, salt, expected = _split_hash(stored)
    except ValueError:
        if username not in _warned_plaintext:
            _warned_plaintext.add(username)
            log.error("User '%s' has no valid password hash and cannot log in; "
                      "run `streamhub hash-passwords <config>` or set a hash from `streamhub passwd`", username)
        return False
    digest = hashlib.pbkdf2_hmac("sha256", given.encode(), salt, iterations)
    return hmac.compare_digest(digest, expected)


DEMO_ADMIN_PASSWORD = "admin"  # the default of the Docker image, Compose and `make demo`


def demo_password_in_use():
    """True when STREAMHUB_ADMIN_PASSWORD is the demo default, which anyone can guess."""
    return os.environ.get("STREAMHUB_ADMIN_PASSWORD") == DEMO_ADMIN_PASSWORD


def needs_setup(catalog, settings):
    """True while nobody can administer the hub, so the setup page may create the first admin: no admin in a
    valid users file, no STREAMHUB_ADMIN_PASSWORD, and no OpenID Connect or LDAP (their admins come from
    group mapping). An invalid users file never counts as empty."""
    if settings.oidc or settings.ldap or "users" in catalog.errors():
        return False
    return not any(user.role == "admin" and user.source == "local" for user in catalog.users().values())


@functools.lru_cache(maxsize=4)
def env_password(value):
    """STREAMHUB_ADMIN_PASSWORD as a hash: used as is if it already is one, else hashed once in memory."""
    return value if is_hashed(value) else hash_password(value)


def hash_users(data):
    """Hash every raw password of a users-file mapping in place. Returns the names that changed.

    Each new hash is checked against its password before it replaces it; SSO entries have no password.
    """
    changed = []
    for name, entry in data.items():
        if not isinstance(entry, dict) or "password" not in entry or entry.get("source", "local") != "local":
            continue
        raw = str(entry["password"])
        if is_hashed(raw):
            continue
        hashed = hash_password(raw)
        if not verify_password(hashed, raw, name):
            raise RuntimeError(f"hash check failed for '{name}'")
        entry["password"] = hashed
        changed.append(name)
    return changed


def role_at_least(user, role):
    return user is not None and ROLES.get(user.role, 0) >= ROLES[role]


def can_view_board(user, board):
    """`board` is a Board, or None for the landing page."""
    if board is None or not board.auth:
        return True
    return user is not None and ("*" in user.boards or board.name in user.boards)


def can_access_app(user, app, catalog):
    """An app is reachable when any of its boards is viewable by `user`. Built-in tools use roles."""
    if app.min_role:
        return role_at_least(user, app.min_role)
    if app.app_id == "help.cmd":
        return True
    if role_at_least(user, "admin"):
        return True
    for name in app.boards:
        if name == "":
            return True
        board = catalog.board(name)
        if board is not None and can_view_board(user, board):
            return True
    return False


class LoginThrottle:
    """Allows `limit` failed attempts per client per `window` seconds.

    `reserve()` counts an attempt before it is checked, so concurrent attempts cannot all pass the limit
    before their failures are recorded. Each reservation is settled with `failed`, `succeeded`
    or `cancel`. Limits are per hub instance.
    """

    def __init__(self, limit=10, window=300):
        self.limit = limit
        self.window = window
        self._failures = {}   # client -> deque of failure times
        self._pending = {}    # client -> attempts in progress
        self._pruned = time.monotonic()

    def _recent(self, client):
        """Number of the client's failures inside the window (older ones are dropped)."""
        failures = self._failures.get(client)
        if failures is None:
            return 0
        cutoff = time.monotonic() - self.window
        while failures and failures[0] < cutoff:
            failures.popleft()
        if not failures:
            del self._failures[client]
        return len(failures)

    def _prune(self):
        """Forget clients without a recent failure, at most once per window."""
        now = time.monotonic()
        if now - self._pruned >= self.window:
            self._pruned = now
            for client in list(self._failures):
                self._recent(client)

    def blocked(self, client):
        return self._recent(client) + self._pending.get(client, 0) >= self.limit

    def reserve(self, client):
        """Claim one attempt for `client`; False when it is at its limit."""
        self._prune()
        if self.blocked(client):
            return False
        self._pending[client] = self._pending.get(client, 0) + 1
        return True

    def cancel(self, client):
        """Give back a reservation that was neither a failure nor a success."""
        left = self._pending.get(client, 0) - 1
        if left > 0:
            self._pending[client] = left
        else:
            self._pending.pop(client, None)

    def failed(self, client, reserved=False):
        if reserved:
            self.cancel(client)
        self._failures.setdefault(client, deque()).append(time.monotonic())

    def succeeded(self, client, reserved=False):
        if reserved:
            self.cancel(client)
        self._failures.pop(client, None)


def sign_identity(token, user, role):
    """HMAC sent as X-Streamhub-Signature, so built-in tools can trust the identity headers."""
    return hmac.new(token.encode(), f"{user}|{role}".encode(), hashlib.sha256).hexdigest()


# -- identity assertions for apps --
IDENTITY_ISSUER = "streamhub"
IDENTITY_SECONDS = 300


def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def app_key(secret, app_id):
    """The key one app verifies X-Streamhub-Identity with (STREAMHUB_APP_KEY). Each app gets its own."""
    return hmac.new(secret.encode(), f"app-key|{app_id}".encode(), hashlib.sha256).hexdigest()


def identity_assertion(key, user, app_id, now=None):
    """X-Streamhub-Identity: an HS256 JWT naming the user, for one app (`aud`), valid for five minutes."""
    now = int(now or time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {"iss": IDENTITY_ISSUER, "aud": app_id, "sub": user.name, "role": user.role, "source": user.source,
              "iat": now, "exp": now + IDENTITY_SECONDS}
    signing_input = ".".join(_b64url(json.dumps(part, separators=(",", ":")).encode()) for part in (header, claims))
    signature = hmac.new(key.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def verify_identity(token, key, app_id, now=None, leeway=30):
    """The claims of an X-Streamhub-Identity value, checked for signature, audience and expiry.

    Raises ValueError otherwise. Apps without Streamhub installed can use any JWT library instead
    (HS256, key STREAMHUB_APP_KEY, audience STREAMHUB_APP_ID, issuer "streamhub").
    """
    try:
        signing_input, _, signature = str(token).rpartition(".")
        header_part, claims_part = signing_input.split(".")
        header, claims = json.loads(_b64url_decode(header_part)), json.loads(_b64url_decode(claims_part))
        expected = hmac.new(key.encode(), signing_input.encode(), hashlib.sha256).digest()
        valid = header.get("alg") == "HS256" and hmac.compare_digest(_b64url_decode(signature), expected)
    except (ValueError, AttributeError, binascii.Error) as exc:
        raise ValueError("malformed identity assertion") from exc
    if not valid:
        raise ValueError("bad identity signature")
    now = now or time.time()
    if claims.get("iss") != IDENTITY_ISSUER or claims.get("aud") != app_id:
        raise ValueError("the identity assertion is for another app")
    if not claims.get("iat", now + leeway + 1) - leeway <= now <= claims.get("exp", 0) + leeway:
        raise ValueError("the identity assertion has expired")
    return claims


# -- sessions --
def session_value(user, sid=None, issued=None):
    """Content of the signed `user` cookie; `i` is the session ID (sessions.py), `t` the login time."""
    data = {"n": user.name, "s": user.source, "r": user.role, "b": list(user.boards)}
    if sid:
        data.update(i=sid, t=int(issued or time.time()))
    return json.dumps(data, separators=(",", ":"))


def session_meta(value):
    """(session ID, login time, name, source) of a cookie; ID and time are None for cookies before 2.2."""
    try:
        data = json.loads(value)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        return None, None, value, "local"
    return data.get("i"), data.get("t"), data.get("n"), data.get("s", "local")


def user_from_session(value, catalog):
    """The user a session cookie stands for, or None.

    Local users are looked up in the users file on every request, so edits and removals apply at once.
    SSO users carry their role and boards in the cookie, unless the users file has an entry for them
    with the same `source`; while the users file is unreadable, SSO sessions are refused. A 2.0 cookie
    holds a bare user name and is read as a local user.
    """
    from streamhub.catalog import User

    try:
        data = json.loads(value)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        user = catalog.user(value)
        return user if user is not None and user.source == "local" else None
    name, source = data.get("n"), data.get("s", "local")
    entry = catalog.user(name)
    if source == "local" or (entry is not None and entry.source == source):
        return entry if entry is not None and entry.source == source else None
    if source not in SSO_SOURCES or not name:
        return None
    if catalog.users_error:  # the users file may hold an override we can't read: fail closed
        return None
    role = data.get("r") if data.get("r") in ROLES else "guest"
    return User(name=name, password="", role=role, boards=list(data.get("b") or []), source=source)


# -- single sign-on --
def map_groups(groups, mapping, default_role):
    """(role, boards) for an SSO user's groups, or None when no rule matches and there is no default role.

    Group names compare case-insensitively. The highest matching role wins; boards are combined.
    """
    wanted = {str(g).casefold() for g in groups}
    role, boards, matched = None, [], False
    for rule in mapping:
        group = str(rule.get("group", "")).casefold()
        if group != "*" and group not in wanted:
            continue
        matched = True
        rule_role = rule.get("role", "user")
        if rule_role in ROLES and (role is None or ROLES[rule_role] > ROLES[role]):
            role = rule_role
        boards += [b for b in rule.get("boards", []) if b not in boards]
    if not matched:
        return None if default_role is None else (default_role, [])
    return role or default_role or "user", boards


def sso_user(name, source, groups, settings, catalog):
    """The User for an SSO login, or None when the account may not sign in."""
    from streamhub.catalog import User

    entry = catalog.user(name)
    if entry is not None and entry.source == source:
        return entry
    if catalog.users_error:
        log.error("SSO login of '%s' refused: %s", name, catalog.users_error)
        return None
    mapped = map_groups(groups, settings.group_mapping, settings.sso_default_role)
    if mapped is None:
        return None
    return User(name=name, password="", role=mapped[0], boards=mapped[1], source=source)


class LdapTlsError(Exception):
    """The LDAP connection could not be secured; nothing was sent over it."""


def ldap_authenticate(config, bind_password, username, password):
    """(username, groups) when the directory accepts `password`, else None. Blocking: run it in an executor.

    Either binds directly as `user-dn` (with `{username}`), or binds as `bind-dn`, finds the user under
    `search-base` with `search-filter`, then binds as the user found.
    """
    if not username or not password:  # an empty password is an anonymous bind: always refuse it
        return None
    import ssl

    import ldap3  # optional `ldap` extra: imported only when LDAP is configured
    from ldap3.utils.conv import escape_filter_chars
    from ldap3.utils.dn import escape_rdn

    plaintext = bool(config.get("allow-plaintext")) and not config.get("starttls")
    # Certificate and host name are verified for ldaps:// and STARTTLS (system CAs, or `ca-file`).
    tls = None if plaintext else ldap3.Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=config.get("ca-file") or None)
    server = ldap3.Server(config["url"], get_info=ldap3.NONE, connect_timeout=10, tls=tls)
    group_attribute = config.get("group-attribute", "memberOf")

    def bind(dn, secret):
        """A bound connection, or None. A failed STARTTLS closes the connection before any bind."""
        conn = ldap3.Connection(server, dn, secret, receive_timeout=10, raise_exceptions=False)
        try:
            conn.open()
            if config.get("starttls") and not conn.start_tls():
                raise LdapTlsError(f"STARTTLS to {config['url']} failed; not sending credentials")
            if conn.bind():
                return conn
        except BaseException:
            conn.unbind()
            raise
        conn.unbind()
        return None

    if config.get("user-dn"):
        user_dn = config["user-dn"].format(username=escape_rdn(username))
        conn = bind(user_dn, password)
        if conn is None:
            return None
        conn.search(user_dn, "(objectClass=*)", search_scope=ldap3.BASE, attributes=[group_attribute])
    else:
        service = bind(config.get("bind-dn"), bind_password)
        if service is None:
            log.error("LDAP bind as %s failed", config.get("bind-dn"))
            return None
        query = config.get("search-filter", "(uid={username})").format(username=escape_filter_chars(username))
        service.search(config["search-base"], query, attributes=[group_attribute])
        entries = list(service.entries)
        service.unbind()
        if len(entries) != 1:
            return None
        user_dn = entries[0].entry_dn
        conn = bind(user_dn, password)
        if conn is None:
            return None
        conn.search(user_dn, "(objectClass=*)", search_scope=ldap3.BASE, attributes=[group_attribute])
    groups = []
    if conn.entries and group_attribute in conn.entries[0]:
        groups = [str(g) for g in conn.entries[0][group_attribute].values]
    conn.unbind()
    return username, groups
