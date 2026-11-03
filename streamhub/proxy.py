"""HTTP and WebSocket reverse proxy for running apps."""
import asyncio
import logging
from http.cookies import SimpleCookie

import tornado.httpclient
import tornado.httputil
import tornado.iostream
import tornado.routing
import tornado.web
import tornado.websocket

from streamhub import auth
from streamhub.handlers.base import INSTANCE_COOKIE, UiMixin, set_instance_cookie

log = logging.getLogger(__name__)

HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
              "transfer-encoding", "upgrade", "host", "content-length"}
WS_HANDSHAKE = {"sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions",
                "sec-websocket-protocol", "origin"}
HUB_COOKIES = {"user", "_xsrf", "oidc", INSTANCE_COOKIE}
IDENTITY_HEADERS = ("X-Streamhub-User", "X-Streamhub-Role", "X-Streamhub-Signature", "X-Streamhub-Identity")
BODY_METHODS = ("POST", "PUT", "PATCH", "DELETE")
BODY_QUEUE_CHUNKS = 16  # request body chunks (64 KB each) buffered per upload before reading pauses
_ABORT = object()       # ends a streamed request body when the browser disconnects


def split_app_path(path):
    """'/app.sl/x/y' -> ('app.sl', 'x/y'); None when the path has no '/<id>/' prefix."""
    parts = path.split("/", 2)
    if len(parts) < 3 or not parts[1]:
        return None
    return parts[1], parts[2]


class RunningAppMatcher(tornado.routing.Matcher):
    """Matches '/<app_id>/...' for apps that are ready, split by WebSocket upgrade or plain HTTP."""

    def __init__(self, manager, websocket):
        self.manager = manager
        self.websocket = websocket

    def match(self, request):
        split = split_app_path(request.path)
        if split is None:
            return None
        inst = self.manager.running(split[0])
        if inst is None or not inst.ready:
            return None
        is_ws = request.headers.get("Upgrade", "").lower() == "websocket"
        if is_ws != self.websocket:
            return None
        return {"path_args": [], "path_kwargs": {"app_id": split[0], "rest": split[1]}}


class _ProxyMixin:
    """Shared by both proxy handlers. `self.hub` is the Hub object (see app.py)."""

    def prepare_proxy(self, app_id, rest):
        """Upstream URL for this request, or None after redirecting an anonymous user to the login page."""
        self.inst = self.hub.manager.running(app_id)
        if self.inst is None:
            raise tornado.web.HTTPError(404)
        user = self.current_user_obj
        if not auth.can_access_app(user, self.inst.app, self.hub.catalog):
            if user is None:
                self.redirect(f"/login/?next=/{app_id}/")
            else:
                raise tornado.web.HTTPError(403)
            return None
        return self.inst.url_for(rest, self.request.query)

    def forward_headers(self, exclude=()):
        """Client headers minus hop-by-hop, hub cookies and spoofed X-Streamhub-*; plus forwarding and identity."""
        headers = tornado.httputil.HTTPHeaders()
        for name, value in self.request.headers.get_all():
            lower = name.lower()
            if lower in HOP_BY_HOP or lower in exclude or lower.startswith("x-streamhub-"):
                continue
            if lower == "cookie":
                value = strip_hub_cookies(value)
                if not value:
                    continue
            headers.add(name, value)
        prefix = f"/{self.inst.app_id}"
        headers["X-Forwarded-For"] = self.request.remote_ip
        headers["X-Forwarded-Proto"] = self.request.protocol
        headers["X-Forwarded-Host"] = self.request.host
        headers["X-Forwarded-Prefix"] = prefix
        user = self.current_user_obj
        if user is not None:
            headers["X-Streamhub-User"] = user.name
            headers["X-Streamhub-Role"] = user.role
            headers["X-Streamhub-Signature"] = auth.sign_identity(self.hub.internal_token, user.name, user.role)
            # Verifiable by the app with its STREAMHUB_APP_KEY, and only by it.
            key = auth.app_key(self.hub.internal_token, self.inst.app_id)
            headers["X-Streamhub-Identity"] = auth.identity_assertion(key, user, self.inst.app_id)
        return headers


def has_body(headers):
    """True when a request announces a body (a non-zero Content-Length, or chunked encoding)."""
    if "chunked" in headers.get("Transfer-Encoding", "").lower():
        return True
    return headers.get("Content-Length", "0").strip() not in ("", "0")


def strip_hub_cookies(header):
    """Cookie header without the hub's own cookies. Unparseable headers are passed through unchanged."""
    try:
        jar = SimpleCookie()
        jar.load(header)
    except Exception:
        return header
    return "; ".join(f"{k}={m.coded_value}" for k, m in jar.items() if k not in HUB_COOKIES)


@tornado.web.stream_request_body
class ProxyHTTPHandler(UiMixin, _ProxyMixin, tornado.web.RequestHandler):
    """Streams any HTTP request to the app in both directions.

    The upstream request starts in prepare(); request body chunks go through a small queue, so reading
    from the browser pauses while the app is slower. Response headers arrive via _on_header and
    response body chunks via _on_chunk.
    """
    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE", "PATCH", "OPTIONS")

    def initialize(self, hub):
        self.hub = hub
        self._upstream = None  # the upstream fetch, started by prepare()
        self._body = None      # queue of request body chunks; None ends the body
        self._counted = False  # in hub.active_requests

    def _uncount(self):
        if self._counted:
            self._counted = False
            self.hub.active_requests -= 1

    def on_finish(self):
        self._uncount()

    def check_xsrf_cookie(self):
        pass  # apps handle their own CSRF; the hub's token is not theirs

    def get_current_user(self):
        return self.hub.user_from_cookie(self)

    def prepare(self):
        set_instance_cookie(self, self.hub)
        self.current_user_obj = self.current_user
        url = self.prepare_proxy(self.path_kwargs["app_id"], self.path_kwargs["rest"])
        if url is None:
            return
        self.inst.touch(count="text/html" in self.request.headers.get("Accept", ""))  # count page loads only
        self.hub.active_requests += 1  # until on_finish or on_connection_close (draining)
        self._counted = True
        connection = self.request.connection
        if hasattr(connection, "set_max_body_size"):
            connection.set_max_body_size(self.hub.settings.max_upload_mb * 1024 * 1024)
            connection.set_body_timeout(self.hub.settings.proxy_timeout)
        if self.request.method in BODY_METHODS and has_body(self.request.headers):
            self._body = asyncio.Queue(maxsize=BODY_QUEUE_CHUNKS)
        self._headers_sent = False
        self._upstream = asyncio.ensure_future(self._fetch(url))

    async def _fetch(self, url):
        """Run the upstream request; returns the connection error, if any."""
        headers = self.forward_headers(exclude={"expect"})
        body = body_producer = None
        if self._body is not None:
            if "Content-Length" in self.request.headers:  # else Tornado sends it chunked
                headers["Content-Length"] = self.request.headers["Content-Length"]
            body_producer = self._produce
        elif self.request.method in ("POST", "PUT", "PATCH"):
            body = b""  # Tornado's client requires a body for these methods
        request = tornado.httpclient.HTTPRequest(
            url, method=self.request.method, headers=headers, body=body, body_producer=body_producer,
            follow_redirects=False, decompress_response=False, allow_nonstandard_methods=True, connect_timeout=10,
            request_timeout=self.hub.settings.proxy_timeout,
            header_callback=self._on_header, streaming_callback=self._on_chunk)
        try:
            await self.hub.http_client.fetch(request, raise_error=False)
        except Exception as exc:  # connection refused, timeouts, DNS errors, an aborted upload
            return exc
        return None

    async def _produce(self, write):
        """Body producer of the upstream request: relays queued chunks until the end of the body."""
        while True:
            chunk = await self._body.get()
            if chunk is None:
                return
            if chunk is _ABORT:
                raise tornado.iostream.StreamClosedError()
            await write(chunk)

    async def _feed(self, item):
        """Queue a body chunk (None: end of body) unless the upstream request has already ended."""
        if self._upstream is None or self._upstream.done():
            return
        put = asyncio.ensure_future(self._body.put(item))
        await asyncio.wait([put, self._upstream], return_when=asyncio.FIRST_COMPLETED)
        if not put.done():
            put.cancel()

    async def data_received(self, chunk):
        if self._body is not None:
            await self._feed(chunk)  # waits while the queue is full: backpressure on the browser

    def on_connection_close(self):
        """The browser went away: end the upload so the upstream request stops too."""
        super().on_connection_close()  # ends the wait for the rest of the body
        self._uncount()
        if self._body is not None:
            while not self._body.empty():
                self._body.get_nowait()
            self._body.put_nowait(_ABORT)

    async def _proxy(self, app_id, rest):
        """Called once the whole request body has been received."""
        if self._upstream is None:
            return
        if self._body is not None:
            await self._feed(None)
        error = await self._upstream
        if error is not None and not self._headers_sent:
            log.warning("Proxy to %s failed: %s", self.inst.upstream, error)
            self.set_status(502)
            self.write(self.render_string("error.html", app=self.inst.app, port=self.inst.port,
                                          message=f"The app did not answer: {error}",
                                          log_tail=self.hub.log_tail(self.inst)))
        if not self._finished:
            self.finish()

    def _on_header(self, line):
        """Called per upstream header line; the blank line ends the headers."""
        line = line.rstrip("\r\n")
        if line.startswith("HTTP/"):
            self._status_line = tornado.httputil.parse_response_start_line(line)
            self._upstream_headers = tornado.httputil.HTTPHeaders()
        elif line:
            self._upstream_headers.parse_line(line)
        else:
            self._send_upstream_headers()

    def _send_upstream_headers(self):
        """Copy the upstream status and headers to the client (Location rewritten under the prefix)."""
        status = self._status_line
        if status.code == 100:  # "100 Continue" interim response: wait for the real one
            return
        self.set_status(status.code, status.reason or None)
        self.clear_header("Content-Type")
        replaced = set()
        for name, value in self._upstream_headers.get_all():
            lower = name.lower()
            if lower in HOP_BY_HOP and not (lower == "content-length" and self.request.method == "HEAD"):
                continue
            if lower == "location":
                value = self.rewrite_location(value)
            if lower not in replaced:  # upstream values replace Tornado's defaults (Date, Server, ...)
                self.clear_header(name)
                replaced.add(lower)
            self.add_header(name, value)
        self._headers_sent = True

    def compute_etag(self):
        return None  # never invent an ETag for a proxied response

    def rewrite_location(self, value):
        """Keep redirects inside '/<app_id>/' when the app is unaware of its prefix."""
        prefix = f"/{self.inst.app_id}"
        if value.startswith(self.inst.upstream):
            value = value[len(self.inst.upstream):] or "/"
        elif not value.startswith("/") or value.startswith("//"):
            return value  # relative or another host
        if self.inst.strip_prefix and value != prefix and not value.startswith(prefix + "/"):
            return prefix + value
        return value

    def _on_chunk(self, chunk):
        """Relay each body chunk as it arrives, so large or streamed responses are never buffered."""
        if self.request.connection.stream.closed():
            return  # the browser went away
        if not self._headers_sent:
            self._send_upstream_headers()
        self.write(chunk)
        self.flush()

    get = head = post = put = delete = patch = options = _proxy


class ProxyWSHandler(_ProxyMixin, tornado.websocket.WebSocketHandler):
    """Bridges a browser WebSocket to the app's WebSocket (Streamlit's /_stcore/stream)."""

    def initialize(self, hub):
        self.hub = hub
        self.upstream = None
        self.pending = []  # client messages received before the upstream connection opened
        self.closed_by_client = False

    def get_current_user(self):
        return self.hub.user_from_cookie(self)

    async def get(self, app_id, rest):
        if self.hub.draining:
            raise tornado.web.HTTPError(503, reason="Streamhub is stopping")
        # Check access before accepting the upgrade.
        self.current_user_obj = self.current_user
        self.upstream_target = self.prepare_proxy(app_id, rest)
        if self.upstream_target is None:
            return
        await super().get(app_id, rest)

    def select_subprotocol(self, subprotocols):
        # Streamlit sends ["streamlit", <xsrf token>, <session id>]: accept the first, forward them all.
        self.requested_subprotocols = list(subprotocols)
        return subprotocols[0] if subprotocols else None

    def get_compression_options(self):
        return None  # no compression on the browser side

    async def open(self, app_id, rest):
        """Connect upstream, then flush messages that arrived meanwhile."""
        self.inst.active_ws += 1
        self.inst.touch()
        url = "ws" + self.upstream_target[4:] if self.upstream_target.startswith("http") else self.upstream_target
        request = tornado.httpclient.HTTPRequest(
            url, headers=self.forward_headers(exclude=WS_HANDSHAKE),
            connect_timeout=10, request_timeout=self.hub.settings.proxy_timeout)
        try:
            self.upstream = await tornado.websocket.websocket_connect(
                request, on_message_callback=self._from_upstream,
                subprotocols=getattr(self, "requested_subprotocols", None) or None,
                max_message_size=self.hub.settings.max_ws_message_mb * 1024 * 1024)
        except Exception as exc:
            log.warning("WebSocket upstream %s failed: %s", url, exc)
            self.close(1011, "upstream unavailable")
            return
        if self.closed_by_client:  # the browser left while we were connecting
            self.upstream.close()
            return
        for message in self.pending:
            await self.upstream.write_message(message, binary=isinstance(message, bytes))
        self.pending = []

    def _from_upstream(self, message):
        if message is None:  # upstream closed
            if not self.closed_by_client:
                self.close()
            return
        try:
            self.write_message(message, binary=isinstance(message, bytes))
        except tornado.websocket.WebSocketClosedError:
            pass

    async def on_message(self, message):
        if self.upstream is None:
            self.pending.append(message)
            return
        try:
            await self.upstream.write_message(message, binary=isinstance(message, bytes))
        except tornado.websocket.WebSocketClosedError:
            self.close()

    def on_close(self):
        self.closed_by_client = True
        inst = getattr(self, "inst", None)
        if inst is not None and inst.active_ws > 0:
            inst.active_ws -= 1
            inst.touch(count=False)
        if self.upstream is not None:
            self.upstream.close()
            self.upstream = None

