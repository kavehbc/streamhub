# HTTPS and reverse proxies

## HTTPS in the hub

The hub can serve HTTPS itself, next to HTTP:

```json
{ "port": 8500, "ssl_port": 8443, "ssl-cert": "cert/hub.pem", "ssl-key": "cert/hub-key.pem" }
```

Both listeners serve the same hub. The session cookie is marked `Secure` over HTTPS. For a test certificate, see `cert/openssl.txt` in the repository.

## Behind a reverse proxy

A reverse proxy (nginx, Caddy, IIS with ARR, Traefik, a cloud load balancer) usually terminates TLS. Then:

1. Set `"behind-proxy": true`, so the hub trusts `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host` and `X-Real-IP`. Without it, every client looks like the proxy, and the login throttle treats them as one.
2. Forward **WebSockets**: Streamlit needs them.
3. Allow large bodies, up to `max-upload-mb`.
4. Allow long requests and idle WebSockets (`proxy_read_timeout`).
5. Set `server-url` to the public address, for links in notifications; and with OpenID Connect, set `oidc.redirect-uri` if the proxy changes the host.

### nginx

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name apps.example.com;
    ssl_certificate     /etc/ssl/apps.example.com.pem;
    ssl_certificate_key /etc/ssl/apps.example.com.key;
    client_max_body_size 1g;

    location / {
        proxy_pass http://127.0.0.1:8500;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 1h;
        proxy_buffering off;
    }
}
```

### Caddy

```text
apps.example.com {
    reverse_proxy 127.0.0.1:8500
}
```

Caddy obtains a certificate and forwards WebSockets and the `X-Forwarded-*` headers by itself.

## Under a sub-path

The hub expects to own the root of its host: apps live at `/<app_id>/` and hub pages at `/admin/`, `/login/`, and so on. Give it its own host name (`apps.example.com`) rather than a sub-path (`example.com/apps/`).
