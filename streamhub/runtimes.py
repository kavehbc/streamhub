"""How an app runs: a local process, a Docker container or a Kubernetes pod.

Each runtime gives the AppManager one local child process to watch: the app itself, the `docker run`
client, or a pod log follower. Logging, exit detection and restart policies work the same for all three.
"""
import asyncio
import hashlib
import json
import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from streamhub import platform_utils

log = logging.getLogger(__name__)

SERVICE_ACCOUNT_NAMESPACE = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")


class LaunchError(Exception):
    """An app could not be started; the message is shown on its error page."""


@dataclass
class Launch:
    """What a runtime prepared: the local command to spawn and where the app will answer."""
    argv: list
    upstream: str
    probe: str                       # readiness without a health path: "bind" (port taken) or "connect"
    env: dict = field(default_factory=dict)   # environment of the local child process
    handle: object = None            # what release() needs: a container name, (namespace, pod)


# st.user keys filled from the identity headers the proxy sends (`streamlit_user_headers`).
STREAMLIT_USER_HEADERS = {"X-Streamhub-User": "name", "X-Streamhub-Role": "role"}


def streamlit_flags(app_id, port, address, max_message_mb, user_headers=False):
    """`streamlit run` flags: serve under /<app_id>/ on `address:port`. CORS and XSRF are off (see COMPAT-5).

    `user_headers` maps the hub's identity into st.user (server.trustedUserHeaders, newer Streamlit only).
    """
    flags = [f"--server.port={port}", f"--server.address={address}", "--server.headless=true",
             f"--server.baseUrlPath={app_id}", "--server.runOnSave=true",
             "--server.enableCORS=false", "--server.enableXsrfProtection=false",
             "--browser.gatherUsageStats=false", f"--server.maxMessageSize={max_message_mb}"]
    if user_headers:
        flags.append(f"--server.trustedUserHeaders={json.dumps(STREAMLIT_USER_HEADERS)}")
    return flags


def wants_user_headers(app, settings):
    """`streamlit_user_headers` of the app, else the hub's `streamlit-user-headers`; never for built-in tools."""
    if app.kind != "sl":
        return False
    return settings.streamlit_user_headers if app.streamlit_user_headers is None else app.streamlit_user_headers


def container_argv(app, port, max_message_mb, user_headers=False):
    """Command run inside the image. `file` is relative to the image's working directory; a web server with
    neither `file` nor `command` runs the image's own command."""
    if app.command:
        values = {"python": "python", "port": port, "app_id": app.app_id, "base_path": f"/{app.app_id}"}
        return [str(arg).format(**values) for arg in app.command] + app.args
    if not app.file:
        if not app.is_streamlit:
            return list(app.args)  # the image's own command (args, if any, replace it)
        raise LaunchError(f"{app.app_id} has no 'file' or 'command'")
    if app.is_streamlit:
        flags = streamlit_flags(app.app_id, port, "0.0.0.0", max_message_mb, user_headers)
        return ["streamlit", "run", app.file] + flags + app.args
    return ["python", app.file, f"--port={port}", f"--app_id={app.app_id}"] + app.args


def resource_name(app_id, instance_id, limit=63):
    """DNS-1123 label, also a valid Docker name, for an app's container, pod and service."""
    base = re.sub(r"[^a-z0-9-]+", "-", f"streamhub-{instance_id or 'hub'}-{app_id}".lower()).strip("-")
    if len(base) <= limit:
        return base
    digest = hashlib.sha1(base.encode()).hexdigest()[:8]
    return f"{base[:limit - 9].rstrip('-')}-{digest}"


def label_value(value):
    """A valid Kubernetes label value (63 characters, alphanumeric ends)."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value)[:63].strip("-_.") or "none"


def docker_host(settings):
    """The `docker -H` value of `docker-socket`: a socket path becomes unix://<path>; "" means Docker's default."""
    value = settings.docker_socket
    return value if not value or "://" in value else f"unix://{value}"


def docker_cli(settings):
    """The docker client and the daemon it talks to: [docker] or [docker, -H, <host>]."""
    exe = platform_utils.docker_exe()
    if not exe:
        raise LaunchError("docker was not found on PATH (or set STREAMHUB_DOCKER)")
    host = docker_host(settings)
    return [exe, "-H", host] if host else [exe]


def kubernetes_manifest(app, name, instance_id, port, env, max_message_mb, user_headers=False):
    """A v1 List with the app's Pod and its ClusterIP Service."""
    options = app.kubernetes
    labels = {"app.kubernetes.io/managed-by": "streamhub", "streamhub/app": label_value(app.app_id),
              "streamhub/instance": instance_id or "hub", "streamhub/name": name}
    container = {"name": "app", "image": app.image, "args": container_argv(app, port, max_message_mb, user_headers),
                 "ports": [{"containerPort": port}],
                 "env": [{"name": key, "value": value} for key, value in env.items()]}
    for key, target in (("resources", "resources"), ("image_pull_policy", "imagePullPolicy"),
                        ("env_from", "envFrom")):
        if options.get(key):
            container[target] = options[key]
    spec = {"restartPolicy": "Never", "containers": [container]}
    for key, target in (("node_selector", "nodeSelector"), ("service_account", "serviceAccountName")):
        if options.get(key):
            spec[target] = options[key]
    if options.get("image_pull_secrets"):
        spec["imagePullSecrets"] = [s if isinstance(s, dict) else {"name": s} for s in options["image_pull_secrets"]]
    pod = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "labels": labels}, "spec": spec}
    service = {"apiVersion": "v1", "kind": "Service", "metadata": {"name": name, "labels": labels},
               "spec": {"selector": {"streamhub/name": name}, "ports": [{"port": port, "targetPort": port}]}}
    return {"apiVersion": "v1", "kind": "List", "items": [pod, service]}


class ProcessRuntime:
    """The app is a child process of the hub, listening on an allocated local port."""
    name = "process"
    uses_local_port = True

    def __init__(self, manager):
        self.manager = manager

    @property
    def settings(self):
        return self.manager.settings

    async def prepare(self, app, port):
        argv = await asyncio.get_running_loop().run_in_executor(None, self.manager.build_argv, app, port)
        env = {**platform_utils.child_env(), **self.manager.app_env(app, port, "127.0.0.1")}
        return Launch(argv=argv, upstream=f"http://127.0.0.1:{port}", probe="bind", env=env)

    async def release(self, inst):
        """Stop what the local child process does not own. The process tree is stopped afterwards."""

    async def sweep(self, apps):
        """Remove what a previous, crashed hub left behind."""


class DockerRuntime(ProcessRuntime):
    """`docker run` in the foreground. The container is published on 127.0.0.1:<allocated port>, or, with
    `docker-network` (the hub itself in a container), joins that network and is reached by its name."""
    name = "docker"

    @property
    def uses_local_port(self):
        return not self.settings.docker_network

    def cli(self):
        return docker_cli(self.settings)

    async def prepare(self, app, port):
        docker = self.cli()
        name = resource_name(app.app_id, self.settings.instance_id)
        await platform_utils.run_command([*docker, "rm", "-f", name])  # a leftover with the same name
        inner = app.port_in_container
        app_env = self.manager.app_env(app, inner, "0.0.0.0")
        network = self.settings.docker_network
        argv = [*docker, "run", "--rm", "--name", name,
                "--label", f"streamhub.app={label_value(app.app_id)}",
                "--label", f"streamhub.instance={self.settings.instance_id or 'hub'}"]
        argv += ["--network", network] if network else ["-p", f"127.0.0.1:{port}:{inner}"]
        for volume in app.volumes:
            argv += ["-v", volume]
        for key in app_env:
            argv += ["-e", key]  # docker reads the value from its own environment: no secrets in argv
        argv += app.runtime_args + [app.image] + container_argv(app, inner, self.settings.max_ws_message_mb,
                                                                wants_user_headers(app, self.settings))
        # The docker client gets what it needs; the container only the names passed with -e.
        upstream = f"http://{name}:{inner}" if network else f"http://127.0.0.1:{port}"
        return Launch(argv=argv, upstream=upstream, probe="connect",
                      env={**platform_utils.child_env(platform_utils.DOCKER_ENV), **app_env}, handle=name)

    async def release(self, inst):
        code, out = await platform_utils.run_command(
            [*self.cli(), "stop", "-t", str(self.settings.stop_timeout), inst.runtime_handle],
            timeout=self.settings.stop_timeout + 30)
        if code and "No such container" not in out:
            log.warning("docker stop %s: %s", inst.runtime_handle, out.strip())

    async def sweep(self, apps):
        if not any(app.runtime == self.name for app in apps) or not platform_utils.docker_exe():
            return
        label = f"label=streamhub.instance={self.settings.instance_id or 'hub'}"
        code, out = await platform_utils.run_command([*self.cli(), "ps", "-aq", "--filter", label])
        ids = out.split() if code == 0 else []
        if ids:
            log.warning("Removing %d container(s) left by a previous run", len(ids))
            await platform_utils.run_command([*self.cli(), "rm", "-f", *ids], timeout=120)


class KubernetesRuntime(ProcessRuntime):
    """A Pod and a Service per app. The hub runs in the cluster and proxies to the Service name."""
    name = "kubernetes"
    uses_local_port = False

    def exe(self):
        exe = platform_utils.kubectl_exe()
        if not exe:
            raise LaunchError("kubectl was not found on PATH (or set STREAMHUB_KUBECTL)")
        return exe

    def namespace(self, app):
        configured = app.kubernetes.get("namespace") or self.settings.kubernetes_namespace
        if configured:
            return configured
        try:
            return SERVICE_ACCOUNT_NAMESPACE.read_text(encoding="utf-8").strip() or "default"
        except OSError:
            return "default"

    async def prepare(self, app, port):
        kubectl = self.exe()
        namespace = self.namespace(app)
        name = resource_name(app.app_id, self.settings.instance_id)
        inner = app.port_in_container
        manifest = kubernetes_manifest(app, name, self.settings.instance_id, inner,
                                       self.manager.app_env(app, inner, "0.0.0.0"), self.settings.max_ws_message_mb,
                                       wants_user_headers(app, self.settings))
        # Pod specs are immutable: remove a leftover with the same name first.
        await platform_utils.run_command([kubectl, "-n", namespace, "delete", f"pod/{name}", f"service/{name}",
                                          "--ignore-not-found", "--wait=true"], timeout=120)
        code, out = await platform_utils.run_command([kubectl, "-n", namespace, "apply", "-f", "-"],
                                                     input=json.dumps(manifest).encode())
        if code:
            raise LaunchError(f"kubectl apply failed: {out.strip()[-500:]}")
        argv = platform_utils.self_command() + ["follow-pod", kubectl, namespace, name,
                                                str(self.settings.startup_timeout)]
        return Launch(argv=argv, upstream=f"http://{name}.{namespace}.svc:{inner}", probe="connect",
                      env=platform_utils.child_env(platform_utils.KUBECTL_ENV), handle=(namespace, name))

    async def release(self, inst):
        namespace, name = inst.runtime_handle
        code, out = await platform_utils.run_command(
            [self.exe(), "-n", namespace, "delete", f"pod/{name}", f"service/{name}", "--ignore-not-found",
             "--wait=false"])
        if code:
            log.warning("kubectl delete %s: %s", name, out.strip())

    async def sweep(self, apps):
        namespaces = {self.namespace(app) for app in apps if app.runtime == self.name}
        if not namespaces or not platform_utils.kubectl_exe():
            return
        selector = f"app.kubernetes.io/managed-by=streamhub,streamhub/instance={self.settings.instance_id or 'hub'}"
        for namespace in namespaces:
            await platform_utils.run_command([self.exe(), "-n", namespace, "delete", "pod,service", "-l", selector,
                                              "--ignore-not-found", "--wait=false"], timeout=120)


def _pod_status(kubectl, namespace, pod):
    """(phase, exit code, waiting reason). Phase "Gone" when the pod no longer exists."""
    result = subprocess.run([kubectl, "-n", namespace, "get", "pod", pod, "-o", "json"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if result.returncode:
        return "Gone", 1, result.stderr.strip()
    status = json.loads(result.stdout).get("status", {})
    container = (status.get("containerStatuses") or [{}])[0].get("state", {})
    code = container.get("terminated", {}).get("exitCode", 0)
    return status.get("phase", "Unknown"), code, container.get("waiting", {}).get("reason", "")


def follow_pod(kubectl, namespace, pod, startup_timeout):
    """Stream a pod's log to stdout until the pod ends, then exit with its container's exit code.

    Run by the hub as the app's local child process (`streamhub follow-pod ...`, see cli.py).
    """
    deadline = time.monotonic() + startup_timeout
    since = None
    while True:
        phase, code, reason = _pod_status(kubectl, namespace, pod)
        if phase in ("Succeeded", "Failed", "Gone"):
            print(f"[streamhub] pod {pod}: {phase} {reason}".rstrip(), flush=True)
            return code or (0 if phase == "Succeeded" else 1)
        if phase == "Pending":
            if time.monotonic() > deadline:
                print(f"[streamhub] pod {pod} did not start within {startup_timeout}s: {reason}", flush=True)
                return 1
            time.sleep(2)
            continue
        argv = [kubectl, "-n", namespace, "logs", "-f", f"pod/{pod}"]
        if since:
            argv.append(f"--since-time={since}")
        subprocess.run(argv, check=False)  # returns when the pod ends or the stream breaks
        since = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        time.sleep(1)
