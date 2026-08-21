@echo off
setlocal
cd /d "%~dp0"
title TubeBatch
color 0B

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] O TubeBatch ainda nao foi instalado.
    echo Execute primeiro:
    echo install.bat
    echo.
    pause
    exit /b 1
)

if not exist "ffmpeg\ffmpeg.exe" (
    echo [ERRO] O FFmpeg portatil nao foi encontrado.
    echo Execute install.bat para baixar e configurar automaticamente.
    echo.
    pause
    exit /b 1
)

if not exist "ffmpeg\ffprobe.exe" (
    echo [ERRO] O FFprobe portatil nao foi encontrado.
    echo Execute install.bat novamente.
    echo.
    pause
    exit /b 1
)

echo ========================================
echo          TubeBatch iniciado
echo ========================================
echo.
echo FFmpeg local: OK
echo Site:
echo http://127.0.0.1:8000
echo.
echo Para encerrar, pressione CTRL+C.
echo.

start "" http://127.0.0.1:8000
call ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

endlocal
