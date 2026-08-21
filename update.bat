@echo off
title TubeBatch - Atualizar dependencias
color 0E

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Execute primeiro install.bat
    pause
    exit /b 1
)

echo Atualizando yt-dlp e dependencias...
call .venv\Scripts\python.exe -m pip install -U yt-dlp fastapi uvicorn python-multipart
echo.
echo Atualizacao concluida.
pause
