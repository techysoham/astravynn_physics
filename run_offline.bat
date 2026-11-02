@echo off
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
%PY% server.py --offline
pause
