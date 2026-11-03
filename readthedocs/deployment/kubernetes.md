# Kubernetes

Streamhub can run **in** a Kubernetes cluster and start each app as its own **pod** (`"type": "kubernetes"`).

## Requirements

- The hub must run **inside the cluster**, because it proxies to `http://<service>.<namespace>.svc:<container_port>`.
- It needs `kubectl` (or `STREAMHUB_KUBECTL`) and a ServiceAccount allowed to manage pods and services.

The repository's `deploy/kubernetes/` folder has both:

| File | What |
|---|---|
| `Dockerfile` | The hub image plus `kubectl`. Build it with `make k8s-image` (tag `streamhub-kubectl:<version>`). |
| `streamhub.yaml` | A ServiceAccount, a Role (pods and services: get, list, watch, create, patch, delete; pods/log: get), its RoleBinding, and the hub's Deployment and Service |

## Install

```bash
make k8s-image          # then push streamhub-kubectl:<version> to your registry
kubectl create namespace streamhub
kubectl -n streamhub create secret generic streamhub \
  --from-literal=admin-password='…' --from-literal=cookie-secret='…'
kubectl -n streamhub create configmap streamhub-config --from-file=config/streamhub.json \
  --from-file=config/streamhub-apps.json --from-file=config/streamhub-news.json
kubectl -n streamhub apply -f deploy/kubernetes/streamhub.yaml
```

The ConfigMap is read-only, so an init container copies it into a writable `/config`. Admin-page saves last until the pod is replaced: put them back into the ConfigMap, or mount a PersistentVolumeClaim at `/config` instead of the `emptyDir`.

## Kubernetes apps

```json
{
  "board": ["ops.brd"],
  "app_id": "factory-kpis",
  "type": "kubernetes",
  "image": "registry.example.com/factory-kpis:2.0",
  "serves": "streamlit",
  "file": "/app/main.py",
  "kubernetes": {
    "namespace": "apps",
    "resources": {"requests": {"cpu": "250m", "memory": "512Mi"}, "limits": {"memory": "2Gi"}},
    "node_selector": {"pool": "apps"},
    "service_account": "factory-kpis",
    "image_pull_policy": "IfNotPresent",
    "image_pull_secrets": ["registry"],
    "env_from": [{"secretRef": {"name": "factory-db"}}]
  }
}
```

For each launch, the hub applies a Pod (`restartPolicy: Never`) and a ClusterIP Service with `kubectl apply`. It follows the pod's log into the app's log file, and treats the container's exit as the app's exit. Stopping the app deletes both.

- Apps run in `kubernetes.namespace`, else the `kubernetes-namespace` setting, else the hub's own namespace. The hub's Role must cover that namespace.
- `env_passthrough` values are written into the Pod spec; prefer `env_from` with a Secret for credentials.
- While a pod is pending, `/out/<app_id>/` shows its waiting reason, for example `ImagePullBackOff`. The hub gives up after `startup-timeout`.
- Leftover pods and services of the same instance are removed when the hub starts.

## Ingress

Expose the hub's Service through your ingress controller, with WebSocket support, and set `"behind-proxy": true`. For several replicas, see [Multiple instances](multiple-instances.md): ingress-nginx needs `nginx.ingress.kubernetes.io/affinity: cookie`.
