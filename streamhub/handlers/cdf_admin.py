"""The admin page's Static files tab: list, upload, rename and delete files in the `cdf` folder (admins only).

Every path is relative to the folder the hub serves at /cdf/ and must resolve inside it. Uploads are refused
over an existing file unless `overwrite` is set; renames never overwrite.
"""
import os
import re
from datetime import datetime
from pathlib import Path

import tornado.web

from streamhub import auth
from streamhub.config import PACKAGE_DIR
from streamhub.handlers.admin_page import _json_body, _ManagerHandler

MAX_ENTRIES = 5000
# Characters no file name may hold, on any OS the hub runs on.
BAD_NAME = re.compile(r'[\x00-\x1f<>:"|?*\\]')


class _CdfHandler(_ManagerHandler):
    admin_only = True

    @property
    def root(self):
        return Path(self.hub.settings.cdf_path).resolve()

    def target(self, relative, what="path"):
        """The absolute path of `relative` inside the cdf folder, or HTTP 400."""
        if not isinstance(relative, str) or not relative.strip("/ "):
            raise tornado.web.HTTPError(400, reason=f"Give a {what}")
        parts = [p for p in relative.replace("\\", "/").split("/") if p]
        if any(p in (".", "..") or BAD_NAME.search(p) or p != p.strip() for p in parts):
            raise tornado.web.HTTPError(400, reason=f"Invalid {what}: {relative[:100]}")
        path = self.root.joinpath(*parts).resolve()
        if path == self.root or not path.is_relative_to(self.root):
            raise tornado.web.HTTPError(400, reason=f"The {what} is outside the cdf folder")
        return path

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def fail(self, error, status=400):
        self.set_status(status)
        self.write({"ok": False, "error": error})

    def done(self, message, **extra):
        auth.audit.info("cdf: %s by %s", message, self.current_user.name)
        self.write({"ok": True, "message": message, **extra})


class CdfListHandler(_CdfHandler):
    """GET: every file and folder under the cdf folder."""

    def get(self):
        root, entries, truncated = self.root, [], False
        if root.is_dir():
            for folder, dirs, names in os.walk(root):
                dirs.sort()
                base = Path(folder)
                for name in dirs + sorted(names):
                    if len(entries) >= MAX_ENTRIES:
                        truncated = True
                        break
                    path = base / name
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    entries.append({"path": self.relative(path), "dir": name in dirs, "size": stat.st_size,
                                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")})
                if truncated:
                    break
        self.set_header("Cache-Control", "no-store")
        self.write({"root": str(root), "exists": root.is_dir(), "writable": os.access(root, os.W_OK),
                    "bundled": root == (PACKAGE_DIR / "cdf").resolve(), "entries": entries, "truncated": truncated})


class CdfUploadHandler(_CdfHandler):
    """POST multipart `files` into `folder` ("" is the cdf folder itself); `overwrite=1` replaces files."""

    def post(self):
        folder = self.get_argument("folder", "").strip("/ ")
        target = self.target(folder, "folder") if folder else self.root
        uploads = self.request.files.get("files", [])
        if not uploads:
            self.fail("Choose one or more files")
            return
        overwrite = self.get_argument("overwrite", "0") == "1"
        paths = [self.target(f"{folder}/{Path(u['filename'].replace(chr(92), '/')).name}", "file name") for u in uploads]
        existing = [self.relative(p) for p in paths if p.exists()]
        if existing and not overwrite:
            self.fail("Already there: " + ", ".join(existing), status=409)
            return
        if any(p.is_dir() for p in paths):
            self.fail("A folder has that name")
            return
        try:
            target.mkdir(parents=True, exist_ok=True)
            for upload, path in zip(uploads, paths):
                path.write_bytes(upload["body"])
        except OSError as exc:
            self.fail(f"Not saved: {exc.strerror or exc}", status=500)
            return
        self.done("uploaded " + ", ".join(self.relative(p) for p in paths))


class CdfActionHandler(_CdfHandler):
    """POST rename {"from", "to"}, delete {"path"} (a file or an empty folder), or folder {"path"} (create)."""

    def post(self, action):
        body = _json_body(self)
        try:
            getattr(self, action)(body)
        except OSError as exc:
            self.fail(f"Not done: {exc.strerror or exc}", status=500)

    def rename(self, body):
        source, dest = self.target(body.get("from"), "file"), self.target(body.get("to"), "new name")
        if not source.exists():
            self.fail("Not found", status=404)
        elif dest.exists():
            self.fail(f"{self.relative(dest)} already exists", status=409)
        elif source.is_dir() and dest.is_relative_to(source):
            self.fail("A folder can't move into itself")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            source.rename(dest)
            self.done(f"renamed {self.relative(source)} to {self.relative(dest)}")

    def delete(self, body):
        path = self.target(body.get("path"))
        if not path.exists():
            self.fail("Not found", status=404)
        elif path.is_dir():
            if any(path.iterdir()):
                self.fail("The folder is not empty")
                return
            path.rmdir()
            self.done(f"deleted folder {self.relative(path)}")
        else:
            path.unlink()
            self.done(f"deleted {self.relative(path)}")

    def folder(self, body):
        path = self.target(body.get("path"), "folder")
        if path.exists():
            self.fail(f"{self.relative(path)} already exists", status=409)
            return
        path.mkdir(parents=True)
        self.done(f"created folder {self.relative(path)}")
