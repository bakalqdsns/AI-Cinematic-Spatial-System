@echo off
REM ============================================================
REM LlamaServer Stop Script for AICSS Backend
REM Kills llama-server process and exits immediately.
REM ============================================================

REM Kill by executable name (fast and reliable)
taskkill /F /IM llama-server.exe >nul 2>&1
exit /b 0
