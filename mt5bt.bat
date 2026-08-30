@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
rem 2026-08-30: Pin the Python interpreter path explicitly.
rem A bare "python" on PATH failed with "python is not recognized"
rem and aborted 664 backtest runs, so resolve the interpreter here.
set "MT5BT_PY=C:\Users\f\AppData\Local\Programs\Python\Python314\python.exe"
if not exist "%MT5BT_PY%" set "MT5BT_PY=python"
"%MT5BT_PY%" "%~dp0main.py" %*
