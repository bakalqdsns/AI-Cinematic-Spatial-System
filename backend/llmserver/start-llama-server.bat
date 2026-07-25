@echo off
REM ============================================================
REM LlamaServer Startup Script for AICSS Backend
REM Launches llama-server in background and exits IMMEDIATELY.
REM Usage: start-llama-server.bat
REM ============================================================

set "SCRIPT_DIR=%~dp0"
set "MODEL_DIR=%SCRIPT_DIR%models\models\Qwen--Qwen2.5-7B-Instruct-GGUF\snapshots\master"
set "SERVER_EXE=%SCRIPT_DIR%llama-server.exe"
set "MODEL_PATH=%MODEL_DIR%\qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"

REM Launch server with 'start /B' which returns immediately
start "LlamaServer" /B "%SERVER_EXE%" -m "%MODEL_PATH%" -c 8192 -ngl 99 --host 0.0.0.0 --port 8080 --log-disable

REM Exit immediately - don't wait for anything
exit /b 0
