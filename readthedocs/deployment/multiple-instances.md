# Multiple instances

Several hubs can serve the same catalog to more users. Each instance runs **its own copies** of the apps it is asked for, so a browser must keep reaching the same instance: the load balancer has to be **sticky**.

## Set up

1. Give every instance its own `STREAMHUB_INSTANCE_ID` (or `instance-id`): 1–32 lowercase letters, digits and `-`. Set `"behind-proxy": true`.
2. Share the config folder (a network share, a ConfigMap, or a git checkout), and set the **same `STREAMHUB_COOKIE_SECRET`** on every instance, so sessions are valid on all of them. Logs and temp files go to per-instance subfolders (`logs/<instance-id>`, `temp/<instance-id>`).
3. Make the load balancer sticky. Each hub sets the `streamhub_instance` cookie to its instance ID on its pages and proxied responses.

| Load balancer | Stickiness | Example |
|---|---|---|
| nginx (open source) | Route on the `streamhub_instance` cookie | `deploy/multi-instance/nginx.conf` |
| HAProxy | Insert its own cookie | `deploy/multi-instance/haproxy.cfg` |
| Kubernetes ingress-nginx | `nginx.ingress.kubernetes.io/affinity: cookie`. Use a StatefulSet, or set `STREAMHUB_INSTANCE_ID` from `metadata.name`. | – |

The nginx example maps the cookie to a backend:

```nginx
map $cookie_streamhub_instance $streamhub_backend {
    hub-a   10.0.0.11:8500;
    hub-b   10.0.0.12:8500;
    default streamhub_new;   # no cookie yet: pick one
}

upstream streamhub_new {
    hash $remote_addr consistent;
    server 10.0.0.11:8500;
    server 10.0.0.12:8500;
}
```

## What is shared

| Shared | Per instance |
|---|---|
| The catalog (apps, users, news) and settings | Running apps, their ports and logs |
| Sessions and revocations (`sessions-db`): a revoked session is refused everywhere within 5 seconds | Usage counters and metrics |
| | Idle timers, health checks, the login throttle |
| | The temp folder |

Put `sessions-db` on a disk that supports SQLite locking (not NFS).

## Symptoms of a missing piece

Apps restart, or sessions drop, as users move between instances: the load balancer isn't sticky, or the instances have different cookie secrets.
