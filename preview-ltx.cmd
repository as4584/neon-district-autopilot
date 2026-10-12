@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-ltx\Scripts\python.exe" (
  echo LTX runtime missing. See LTX_SETUP.md.
  exit /b 2
)
".venv-ltx\Scripts\python.exe" "scripts\preview_ltx.py" %*
exit /b %errorlevel%
