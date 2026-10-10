@echo off
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" -m unittest discover -s "%~dp0tests" -p "test_*.py"
