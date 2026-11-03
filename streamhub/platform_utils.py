"""Everything that differs between Linux and Windows lives here."""
import asyncio
import fnmatch
import functools
import ipaddress
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
from pathlib import Path

import psutil

log = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
IS_FROZEN = bool(getattr(sys, "frozen", False))  # running as a PyInstaller executable


def self_command():
    """Argv prefix that runs Streamhub itself: the executable when frozen, else `python -m streamhub`."""
    return [sys.executable] if IS_FROZEN else [sys.executable, "-m", "streamhub"]


def relaunch_env(env):
    """Environment for a new hub that outlives this one.

    A one-file executable unpacks itself into a temporary folder that is deleted when it exits; a child
    started from it reuses that folder unless PyInstaller is told to unpack the child separately.
    """
    if IS_FROZEN:
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def hub_python():
    """Interpreter for apps without their own environment, and for the built-in tools.

    The hub's own interpreter, or, in the frozen executable (which has none), `python` from PATH.
    """
    if not IS_FROZEN:
        return sys.executable
    # On Windows "python3" is often the Microsoft Store stub, so try "python" first there.
    names = ("python", "python3") if IS_WINDOWS else ("python3", "python")
    found = next(filter(None, map(shutil.which, names)), None)
    if not found:
        raise LookupError("The Streamhub executable has no Python: put python on PATH, "
                          "or set 'virtual-environment' or the app's 'python_executable'")
    return found


# What a child process needs from the hub's environment to run normally (globs). Anything else, secrets
# included, reaches an app only through `env-passthrough` / `env_passthrough` or the app's own `env`.
_CHILD_ENV = ("PATH", "PYTHONPATH", "PYTHONHOME", "LANG", "LANGUAGE", "LC_*", "TZ", "TMPDIR", "TEMP", "TMP",
              "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
              "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "CONDA_*")
_CHILD_ENV_OS = (("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "OS", "USERPROFILE", "USERNAME",
                  "USERDOMAIN", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA",
                  "PROGRAMFILES*", "PROGRAMW6432", "COMMONPROGRAMFILES*", "ALLUSERSPROFILE", "PUBLIC",
                  "COMPUTERNAME", "NUMBER_OF_PROCESSORS", "PROCESSOR_*", "PSMODULEPATH")
                 if IS_WINDOWS else
                 ("HOME", "USER", "LOGNAME", "SHELL", "TERM", "LD_LIBRARY_PATH", "XDG_*"))
DOCKER_ENV = ("DOCKER_*",)
KUBECTL_ENV = ("KUBECONFIG", "KUBERNETES_SERVICE_*")


def child_env(patterns=(), base=True, environ=None):
    """The hub's variables whose names match `patterns` (globs), plus, with `base`, what the OS and
    interpreters need. Names compare case-insensitively on Windows, like the environment itself."""
    environ = os.environ if environ is None else environ
    fold = str.upper if IS_WINDOWS else str
    wanted = [fold(p) for p in ((_CHILD_ENV + _CHILD_ENV_OS) if base else ()) + tuple(patterns)]
    return {name: value for name, value in environ.items()
            if any(fnmatch.fnmatchcase(fold(name), pattern) for pattern in wanted)}


def container_name():
    """The container ID the hub runs in (Docker sets it as the host name), or "" outside a container."""
    if IS_WINDOWS or not (Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()):
        return ""
    return socket.gethostname()


def user_data_dir():
    """A per-user folder for Streamhub's own files (the demo copy): %LOCALAPPDATA%\\streamhub on Windows,
    $XDG_DATA_HOME/streamhub (default ~/.local/share/streamhub) elsewhere."""
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "streamhub"


def conda_exe():
    return os.environ.get("CONDA_EXE") or shutil.which("conda")


def docker_exe():
    return os.environ.get("STREAMHUB_DOCKER") or shutil.which("docker")


def kubectl_exe():
    return os.environ.get("STREAMHUB_KUBECTL") or shutil.which("kubectl")


async def run_command(argv, input=None, timeout=60):
    """Run a tool to completion without a shell. Returns (exit code, combined output)."""
    process = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(process.communicate(input), timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return -1, f"{argv[0]} timed out after {timeout}s"
    return process.returncode, out.decode("utf-8", errors="replace")


@functools.lru_cache(maxsize=1)
def _conda_envs():
    exe = conda_exe()
    if not exe:
        return {}
    try:
        out = subprocess.run([exe, "env", "list", "--json"], capture_output=True, text=True,
                             check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Could not list conda environments: %s", exc)
        return {}
    envs = {}
    for prefix in map(Path, json.loads(out).get("envs", [])):
        envs.setdefault(prefix.name, prefix)
    root = os.environ.get("CONDA_ROOT") or (Path(exe).resolve().parents[1] if exe else None)
    if root:
        envs.setdefault("base", Path(root))
    return envs


def conda_envs():
    """{name: prefix} of the conda environments on this machine ({} without conda); listed once, then cached."""
    return dict(_conda_envs())


def prefix_python(prefix):
    prefix = Path(prefix)
    return prefix / "python.exe" if IS_WINDOWS else prefix / "bin" / "python"


def env_python(env):
    """Resolve the interpreter for a conda env name or an environment/venv path.

    An empty value, or the env the hub itself runs in, resolves to the hub's interpreter.
    """
    if not env:
        return hub_python()
    as_path = Path(env)
    if as_path.is_dir():
        candidates = [prefix_python(as_path), as_path / "Scripts" / "python.exe"]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        raise LookupError(f"No Python interpreter found in environment folder: {env}")
    if not IS_FROZEN and (env == os.environ.get("CONDA_DEFAULT_ENV") or env == Path(sys.prefix).name):
        return sys.executable
    prefix = _conda_envs().get(env)
    if prefix is None:
        raise LookupError(f"Conda environment not found: {env}")
    return str(prefix_python(prefix))


def new_group_kwargs():
    """Start a child in its own process group so its whole tree can be stopped."""
    if IS_WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def process_tree(pid):
    """[root, *descendants] as psutil processes; empty when `pid` is gone."""
    try:
        root = psutil.Process(pid)
        return [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return []


def signal_tree(procs, kill=False):
    """SIGTERM (or SIGKILL) every process. On Windows both are TerminateProcess: CTRL_BREAK_EVENT is not
    used because, aimed at a stale group id, Windows delivers it to every process on the console."""
    for proc in procs:
        try:
            (proc.kill if kill else proc.terminate)()
        except psutil.NoSuchProcess:
            pass


_JOB = None  # Windows Job Object holding the hub and its children


def _job_limits(kernel32, job, flags):
    """SetInformationJobObject(JobObjectExtendedLimitInformation) with `flags` as the only limits."""
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    info = Extended()
    info.BasicLimitInformation.LimitFlags = flags
    extended_limit_information = 9
    return kernel32.SetInformationJobObject(job, extended_limit_information, ctypes.byref(info), ctypes.sizeof(info))


def kill_children_with_hub():
    """Make the OS kill every app when the hub dies, even by a crash or a hard kill.

    Windows: the hub joins a Job Object with KILL_ON_JOB_CLOSE; children started afterwards join it too, and
    the job (with all of them) is killed when the hub's handle closes. Returns False where this is not
    available (Linux, or a job that cannot be created); the startup sweep then removes leftovers instead.
    """
    global _JOB
    if not IS_WINDOWS or _JOB is not None:
        return _JOB is not None
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kill_on_job_close = 0x2000
    job = kernel32.CreateJobObjectW(None, None)
    if not job or not _job_limits(kernel32, job, kill_on_job_close) \
            or not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        log.warning("Could not create a job object for app processes (error %s); leftovers are removed at "
                    "the next start instead", ctypes.get_last_error())
        return False
    _JOB = (kernel32, job)
    return True


def release_children():
    """Before the hub relaunches itself: let processes started from now on outlive this hub."""
    if _JOB is not None:
        _job_limits(*_JOB, 0)


def kill_leftover(pid, created):
    """Kill what remains of an app process tree started by a previous hub. Returns the number killed.

    `created` is the root's start time (psutil): a live process with that PID but another start time is
    an unrelated process that reused the PID, and is left alone. On POSIX the rest of the root's process
    group goes too, since its children are re-parented when it dies (a PID still used as a process group
    ID is never reused).
    """
    procs = []
    try:
        root = psutil.Process(pid)
        if abs(root.create_time() - created) > 1:
            return 0
        procs = [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        pass
    except psutil.Error:
        return 0
    if not IS_WINDOWS:
        known = {p.pid for p in procs}
        for proc in psutil.process_iter():
            try:
                if proc.pid not in known and os.getpgid(proc.pid) == pid and proc.create_time() >= created - 1:
                    procs.append(proc)
            except (psutil.Error, OSError):
                continue
    signal_tree(procs, kill=True)
    return len(procs)


def process_started(pid):
    """Start time of `pid` as psutil reports it (for kill_leftover), or 0.0 when it is gone."""
    try:
        return psutil.Process(pid).create_time()
    except psutil.Error:
        return 0.0


def wait_gone(procs, timeout):
    """Wait for processes that are *not* our children (the asyncio watcher reaps the root). Blocking."""
    _, alive = psutil.wait_procs(procs, timeout=timeout)
    return alive


def port_is_free(port):
    """True when nothing listens on `port`. A bind test is instant on every OS."""
    for host in ("127.0.0.1", "0.0.0.0"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if IS_WINDOWS:
                # SO_REUSEADDR on Windows would let us bind next to a live listener.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                # Like the app servers themselves: ignore TIME_WAIT leftovers, still fail on a listener.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                return False
    return True


def port_accepts(host, port, timeout=1.0):
    """True when a TCP connection to host:port succeeds (for listeners the hub does not own)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def exposed_listeners(pid):
    """'ip:port' of every non-loopback listening socket of `pid` and its descendants. Blocking."""
    found = set()
    for proc in process_tree(pid):
        try:
            # psutil 6 renamed connections() to net_connections()
            connections = getattr(proc, "net_connections", None) or proc.connections
            for conn in connections(kind="inet"):
                if conn.status == psutil.CONN_LISTEN and not ipaddress.ip_address(conn.laddr.ip).is_loopback:
                    found.add(f"{conn.laddr.ip}:{conn.laddr.port}")
        except (psutil.Error, ValueError):
            continue
    return sorted(found)


def tree_stats(pid):
    """(RSS in KB, CPU %) of a process and all its descendants; (None, None) when it is gone."""
    procs = process_tree(pid)
    if not procs:
        return None, None
    memory, cpu = 0, 0.0
    for proc in procs:
        try:
            memory += proc.memory_info().rss
            cpu += proc.cpu_percent(interval=0.05)
        except psutil.Error:
            pass
    return memory // 1024, round(cpu, 1)


def server_stats():
    memory = psutil.virtual_memory()
    count = psutil.cpu_count() or 1
    try:
        load = [round(x / count * 100) for x in psutil.getloadavg()]
    except (AttributeError, OSError):
        load = None
    return {"cpu_percent": psutil.cpu_percent(interval=0.2), "cpu_count": count,
            "per_cpu": psutil.cpu_percent(percpu=True), "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / 2**30, 1), "memory_total_gb": round(memory.total / 2**30, 1),
            "load_percent": load}


def folder_size(path):
    """(bytes, file count) under `path`, not following symlinks."""
    total, count = 0, 0
    for root, _, files in os.walk(path):
        for name in files:
            file = Path(root, name)
            if not file.is_symlink():
                try:
                    total += file.stat().st_size
                    count += 1
                except OSError:
                    pass
    return total, count


def listening_ports():
    """[{address, pid, process}] for every listening TCP socket. Raises psutil.AccessDenied without rights."""
    rows = []
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN:
            continue
        try:
            name = psutil.Process(conn.pid).name() if conn.pid else ""
        except psutil.Error:
            name = ""
        rows.append({"address": f"{conn.laddr.ip}:{conn.laddr.port}", "pid": conn.pid, "process": name})
    return sorted(rows, key=lambda r: r["address"])


def cpu_affinity(pid, cpus=None):
    """Read, or set when `cpus` is given, a process's CPU affinity. None where the OS has no affinity API."""
    if not hasattr(psutil.Process, "cpu_affinity"):
        return None
    process = psutil.Process(pid)
    if cpus is not None:
        count = psutil.cpu_count() or 1
        if not cpus or min(cpus) < 0 or max(cpus) >= count:
            raise ValueError(f"CPU numbers must be between 0 and {count - 1}")
        process.cpu_affinity(sorted(set(cpus)))
    return process.cpu_affinity()


def script_argv(script):
    """Interpreter prefix for a launcher script, chosen by extension."""
    suffix = Path(script).suffix.lower()
    if suffix in (".bat", ".cmd"):
        return ["cmd", "/c", str(script)]
    if suffix == ".ps1":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    bash = shutil.which("bash")
    if not bash:
        raise LookupError(f"bash is required to run {script}")
    return [bash, str(script)]


def install_signal_handlers(callback):
    """Route every available termination signal to `callback(signum)` on the running event loop.

    signal.signal (not loop.add_signal_handler) because the latter does not exist on Windows.
    """
    loop = asyncio.get_running_loop()
    for name in ("SIGINT", "SIGTERM", "SIGQUIT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            signal.signal(sig, lambda signum, frame: loop.call_soon_threadsafe(callback, signum))
