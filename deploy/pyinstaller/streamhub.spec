# PyInstaller spec: a single-file `streamhub` executable (streamhub.exe on Windows).
# Build from the repository root with `make exe` (or `make.bat exe`); see docs/operations.md, "Build".
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parents[1]

# A conda-based Python keeps DLLs such as libffi (needed by _ctypes) in Library\bin, which PyInstaller
# finds only on PATH: add it, so the build works without activating the environment.
conda_dlls = Path(sys.base_prefix) / "Library" / "bin"
if os.name == "nt" and (Path(sys.base_prefix) / "conda-meta").is_dir() and conda_dlls.is_dir():
    os.environ["PATH"] = f"{conda_dlls}{os.pathsep}{os.environ['PATH']}"

datas = collect_data_files("streamhub")                                       # templates, static, starter
datas += collect_data_files("streamhub", subdir="demo", include_py_files=True)  # `streamhub demo` apps
datas += [(str(ROOT / "streamhub" / "tools" / "help.py"), "streamhub/tools")]  # run by an external Python
datas += [(str(ROOT / "README.md"), ".")]                                      # the guide help.cmd renders

a = Analysis(
    [str(ROOT / "streamhub" / "__main__.py")],
    pathex=[str(ROOT)],
    datas=datas,
    # Every hub module, except the built-in tools and the demo apps: they run in another interpreter.
    hiddenimports=collect_submodules(
        "streamhub", filter=lambda name: not name.startswith(("streamhub.tools", "streamhub.demo"))),
    excludes=["streamlit", "pandas", "numpy", "pyarrow", "altair", "pydeck", "tkinter", "pytest", "IPython"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="streamhub", console=True, upx=False)
