@echo off
rem NextraAxisVM setup: double-click this file. It installs the Python environment (PyAxisVM) and the AxisVM add-on.
title NextraAxisVM setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\setup.ps1" %*
echo.
pause
