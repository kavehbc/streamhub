@echo off
rem Common Streamhub tasks on Windows (cmd or PowerShell). Same targets as the Makefile.
rem   make.bat <target> [extra streamhub options]
rem Override with environment variables, for example: set CONFIG=C:\streamhub-config & make.bat start
setlocal EnableExtensions
set "SELF=%~f0"
cd /d "%~dp0"

if "%PYTHON%"=="" set "PYTHON=python"
if "%CONFIG%"=="" set "CONFIG=config"
for /f "usebackq delims=" %%v in (`%PYTHON% -c "import streamhub; print(streamhub.__version__)"`) do set "VERSION=%%v"
if "%IMAGE_NAME%"=="" set "IMAGE_NAME=kavehbc/streamhub"
if "%IMAGE%"=="" set "IMAGE=%IMAGE_NAME%:%VERSION%"
if "%LATEST%"=="" set "LATEST=%IMAGE_NAME%:latest"

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=help"
shift
set "ARGS="
:collect
if "%~1"=="" goto run
set "ARGS=%ARGS% %1"
shift
goto collect

:run
findstr /r /i /c:"^:%TARGET%$" "%SELF%" >nul || (echo Unknown target "%TARGET%". & call :help & exit /b 1)
goto %TARGET%

:help
echo Usage: make.bat ^<target^> [extra streamhub options]
echo   install        Install Streamhub for development (tools, examples, tests)
echo   install-ldap   Also install LDAP login support
echo   install-build  Also install the build tools (wheel, PyInstaller)
echo   test           Run the test suite (unit, handlers, integration, doc links)
echo   demo           Run the bundled demo in the foreground (streamhub demo; admin password: admin)
echo   start          Run the hub on %%CONFIG%% (default: config), appending output to logs\streamhub.log
echo   check          Validate CONFIG without starting the hub
echo   passwd         Print a password hash for the users file
echo   dist           Build the wheel and sdist into dist\ (needs install-build)
echo   exe            Build the single-file executable dist\streamhub.exe (needs install-build)
echo   docker-build   Build the Docker image, tagged %IMAGE% and %LATEST%
echo   docker-up      Start with Docker Compose on .\config (the first start prints a setup link: make.bat docker-logs)
echo   docker-down    Stop the Compose stack
echo   docker-logs    Follow the Compose logs
echo   k8s-image      Build the hub image with kubectl, for "runtime": "kubernetes"
echo   docs           Build the documentation site into readthedocs\_build\html (pip install -r readthedocs\requirements.txt)
echo   clean          Remove caches and build output
exit /b 0

:install
%PYTHON% -m pip install -e ".[tools,examples,dev]"
exit /b %ERRORLEVEL%

:install-ldap
%PYTHON% -m pip install -e ".[tools,examples,dev,ldap]"
exit /b %ERRORLEVEL%

:install-build
%PYTHON% -m pip install -e ".[tools,examples,dev,build]"
exit /b %ERRORLEVEL%

:test
%PYTHON% -m pytest -q
exit /b %ERRORLEVEL%

:demo
%PYTHON% -m streamhub demo --debug %ARGS%
exit /b %ERRORLEVEL%

:start
if not exist logs mkdir logs
%PYTHON% -m streamhub run %ARGS% %CONFIG% >> logs\streamhub.log 2>&1
exit /b %ERRORLEVEL%

:check
%PYTHON% -m streamhub check %CONFIG%
exit /b %ERRORLEVEL%

:passwd
%PYTHON% -m streamhub passwd %ARGS%
exit /b %ERRORLEVEL%

:dist
%PYTHON% -m build
exit /b %ERRORLEVEL%

:exe
%PYTHON% -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller deploy\pyinstaller\streamhub.spec
exit /b %ERRORLEVEL%

:docker-build
docker build -t %IMAGE% -t %LATEST% .
exit /b %ERRORLEVEL%

:docker-up
docker compose up -d --build
exit /b %ERRORLEVEL%

:docker-down
docker compose down
exit /b %ERRORLEVEL%

:docker-logs
docker compose logs -f
exit /b %ERRORLEVEL%

:k8s-image
call :docker-build || exit /b 1
docker build --build-arg BASE=%IMAGE% -t streamhub-kubectl:%VERSION% deploy\kubernetes
exit /b %ERRORLEVEL%

:docs
%PYTHON% -m sphinx -b html -W --keep-going readthedocs readthedocs\_build\html
exit /b %ERRORLEVEL%

:clean
%PYTHON% -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for pattern in ('**/__pycache__', '.pytest_cache', '*.egg-info', 'build', 'dist', 'readthedocs/_build') for p in pathlib.Path('.').glob(pattern)]"
exit /b %ERRORLEVEL%
