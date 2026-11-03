@echo off
rem Build the documentation site on Windows: readthedocs\make.bat [html|linkcheck|clean]
setlocal
cd /d "%~dp0"
if "%SPHINXBUILD%"=="" set SPHINXBUILD=sphinx-build
set TARGET=%1
if "%TARGET%"=="" set TARGET=html

if "%TARGET%"=="html" (
	%SPHINXBUILD% -b html -W --keep-going . _build\html
) else if "%TARGET%"=="linkcheck" (
	%SPHINXBUILD% -b linkcheck . _build\linkcheck
) else if "%TARGET%"=="clean" (
	%SPHINXBUILD% -M clean . _build
) else (
	echo Unknown target %TARGET%: use html, linkcheck or clean
	exit /b 1
)
