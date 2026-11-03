"""The admin page's Docker tab: the daemon in use, containers and images (admins only).

Everything goes through the docker client (`runtimes.docker_cli`, which adds `-H` for `docker-socket`), with
argument lists, never a shell. Names and image references are checked before they reach the command line.
"""
import asyncio
import json
import re
import socket

import tornado.web

from streamhub import auth, platform_utils
from streamhub.handlers.admin_page import _json_body, _ManagerHandler
from streamhub.runtimes import LaunchError, docker_cli, docker_host

PULL_TIMEOUT = 900
LOG_BYTES = 256 * 1024
# A container ID or name, and an image reference (name[:tag][@digest]); never starting with "-".
CONTAINER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
IMAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,254}")
DEFAULT_HOST = "npipe:////./pipe/docker_engine" if platform_utils.IS_WINDOWS else "unix:///var/run/docker.sock"


def json_lines(text):
    """`docker … --format '{{json .}}'` output: one object per line; anything else is skipped."""
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def labels(text):
    """`docker ps` Labels ("a=1,b=2") as a dict."""
    return dict(part.split("=", 1) for part in (text or "").split(",") if "=" in part)


class _DockerHandler(_ManagerHandler):
    admin_only = True

    def cli(self):
        try:
            return docker_cli(self.hub.settings)
        except LaunchError as exc:
            raise tornado.web.HTTPError(503, reason=str(exc)) from exc

    async def docker(self, *args, timeout=30):
        """(exit code, output) of `docker <args>`."""
        return await platform_utils.run_command([*self.cli(), *args], timeout=timeout)

    def checked(self, value, pattern, what):
        if not isinstance(value, str) or not pattern.fullmatch(value):
            raise tornado.web.HTTPError(400, reason=f"Invalid {what}")
        return value

    def done(self, action, target, code, output):
        auth.audit.info("docker %s %s by %s (exit %s)", action, target, self.current_user.name, code)
        self.write({"ok": code == 0, "output": output.strip()[-4000:]})


class DockerStateHandler(_DockerHandler):
    """The client, the daemon (version or error), the app network, containers and images."""

    async def get(self):
        settings = self.hub.settings
        self.set_header("Cache-Control", "no-store")
        state = {"cli": platform_utils.docker_exe(), "host": docker_host(settings), "default_host": DEFAULT_HOST,
                 "network": settings.docker_network, "network_exists": None, "server": None, "error": "",
                 "containers": [], "images": []}
        if not state["cli"]:
            state["error"] = "The docker client is not installed (or set STREAMHUB_DOCKER)."
            self.write(state)
            return
        version, containers, images, networks = await asyncio.gather(
            self.docker("version", "--format", "{{json .Server}}", timeout=20),
            self.docker("ps", "-a", "--no-trunc", "--format", "{{json .}}", timeout=30),
            self.docker("images", "--format", "{{json .}}", timeout=30),
            self.docker("network", "ls", "--format", "{{.Name}}", timeout=20))
        code, out = version
        server = json_lines(out)
        if code or not server:
            state["error"] = out.strip()[-1000:] or "The Docker daemon did not answer."
            self.write(state)
            return
        state["server"] = {key: server[0].get(key) for key in ("Version", "Os", "Arch", "ApiVersion")}
        if settings.docker_network and networks[0] == 0:
            state["network_exists"] = settings.docker_network in networks[1].split()
        # In a container, the hostname is the container's short ID: that container is the hub itself.
        host = socket.gethostname().lower()
        own = host if re.fullmatch(r"[0-9a-f]{12,64}", host) else None
        for row in json_lines(containers[1]):
            tags = labels(row.get("Labels"))
            state["containers"].append({
                "id": row.get("ID", "")[:12], "name": row.get("Names", ""), "image": row.get("Image", ""),
                "state": row.get("State", ""), "status": row.get("Status", ""), "ports": row.get("Ports", ""),
                "created": row.get("CreatedAt", ""), "app": tags.get("streamhub.app", ""),
                "instance": tags.get("streamhub.instance", ""),
                "hub": bool(own) and row.get("ID", "").startswith(own)})
        for row in json_lines(images[1]):
            repository, tag = row.get("Repository", ""), row.get("Tag", "")
            state["images"].append({
                "id": row.get("ID", ""), "repository": repository, "tag": tag,
                "reference": f"{repository}:{tag}" if repository != "<none>" and tag != "<none>" else row.get("ID", ""),
                "size": row.get("Size", ""), "created": row.get("CreatedSince", ""),
                "containers": row.get("Containers", "")})
        self.write(state)


class DockerContainerHandler(_DockerHandler):
    """POST start, stop, restart or remove a container."""
    COMMANDS = {"start": ["start"], "stop": ["stop"], "restart": ["restart"], "remove": ["rm", "-f"]}

    async def post(self, container, action):
        self.checked(container, CONTAINER, "container")
        timeout = self.hub.settings.stop_timeout + 30
        code, out = await self.docker(*self.COMMANDS[action], container, timeout=timeout)
        self.done(action, container, code, out)


class DockerLogsHandler(_DockerHandler):
    async def get(self, container):
        self.checked(container, CONTAINER, "container")
        code, out = await self.docker("logs", "--tail", "500", container, timeout=30)
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.set_header("Cache-Control", "no-store")
        self.write(out[-LOG_BYTES:] if code == 0 else f"docker logs failed:\n{out}")


class DockerImageHandler(_DockerHandler):
    """POST {"image"}: pull or remove an image."""

    async def post(self, action):
        image = self.checked(_json_body(self).get("image"), IMAGE, "image reference")
        if action == "pull":
            code, out = await self.docker("pull", image, timeout=PULL_TIMEOUT)
        else:
            code, out = await self.docker("rmi", image, timeout=120)
        self.done(action, image, code, out)
