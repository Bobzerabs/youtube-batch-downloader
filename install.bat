@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title TubeBatch - Instalacao
color 0A

echo ========================================
echo        TubeBatch - Instalacao
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado.
    echo.
    echo Instale o Python 3.11 ou superior e marque:
    echo "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

echo [OK] Python encontrado:
python --version
echo.

REM ============================================================
REM FFmpeg portatil - instalado automaticamente dentro do projeto
REM ============================================================

set "FFMPEG_DIR=%CD%\ffmpeg"
set "FFMPEG_EXE=%FFMPEG_DIR%\ffmpeg.exe"
set "FFPROBE_EXE=%FFMPEG_DIR%\ffprobe.exe"
set "FFMPEG_URL=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
set "FFMPEG_ZIP=%TEMP%\tubebatch-ffmpeg.zip"
set "FFMPEG_TEMP=%TEMP%\tubebatch-ffmpeg-extract"

if exist "%FFMPEG_EXE%" if exist "%FFPROBE_EXE%" (
    echo [OK] FFmpeg portatil ja esta instalado.
    goto :ffmpeg_done
)

echo [1/4] FFmpeg nao encontrado. Baixando automaticamente...
echo Isso acontece apenas na primeira instalacao.
echo.

if exist "%FFMPEG_ZIP%" del /f /q "%FFMPEG_ZIP%" >nul 2>&1
if exist "%FFMPEG_TEMP%" rmdir /s /q "%FFMPEG_TEMP%" >nul 2>&1
if not exist "%FFMPEG_DIR%" mkdir "%FFMPEG_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference='SilentlyContinue';" ^
  "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;" ^
  "Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile '%FFMPEG_ZIP%' -UseBasicParsing"

if errorlevel 1 (
    echo.
    echo [ERRO] Nao foi possivel baixar o FFmpeg.
    echo Verifique sua conexao com a internet e execute install.bat novamente.
    echo.
    pause
    exit /b 1
)

echo [2/4] Extraindo FFmpeg...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "New-Item -ItemType Directory -Force -Path '%FFMPEG_TEMP%' | Out-Null;" ^
  "Expand-Archive -LiteralPath '%FFMPEG_ZIP%' -DestinationPath '%FFMPEG_TEMP%' -Force;" ^
  "$ffmpeg = Get-ChildItem -Path '%FFMPEG_TEMP%' -Filter 'ffmpeg.exe' -Recurse | Select-Object -First 1;" ^
  "$ffprobe = Get-ChildItem -Path '%FFMPEG_TEMP%' -Filter 'ffprobe.exe' -Recurse | Select-Object -First 1;" ^
  "if (-not $ffmpeg -or -not $ffprobe) { exit 2 };" ^
  "Copy-Item -LiteralPath $ffmpeg.FullName -Destination '%FFMPEG_EXE%' -Force;" ^
  "Copy-Item -LiteralPath $ffprobe.FullName -Destination '%FFPROBE_EXE%' -Force;"

if errorlevel 1 (
    echo.
    echo [ERRO] O FFmpeg foi baixado, mas nao foi possivel extrai-lo corretamente.
    echo.
    pause
    exit /b 1
)

del /f /q "%FFMPEG_ZIP%" >nul 2>&1
rmdir /s /q "%FFMPEG_TEMP%" >nul 2>&1

if not exist "%FFMPEG_EXE%" (
    echo [ERRO] ffmpeg.exe nao foi encontrado apos a instalacao.
    pause
    exit /b 1
)

if not exist "%FFPROBE_EXE%" (
    echo [ERRO] ffprobe.exe nao foi encontrado apos a instalacao.
    pause
    exit /b 1
)

echo [OK] FFmpeg instalado dentro de:
echo %FFMPEG_DIR%
echo.

:ffmpeg_done

if not exist ".venv" (
    echo [3/4] Criando ambiente virtual do Python...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel criar o ambiente virtual.
        pause
        exit /b 1
    )
) else (
    echo [3/4] Ambiente virtual ja existe.
)

echo [4/4] Instalando/atualizando dependencias...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERRO] Falha ao atualizar o pip.
    pause
    exit /b 1
)

call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Nao foi possivel instalar as dependencias.
    pause
    exit /b 1
)

echo.
echo ========================================
echo    Instalacao concluida com sucesso!
echo ========================================
echo.
echo FFmpeg: instalado automaticamente no projeto
echo Python: ambiente virtual configurado
echo.
echo Agora execute:
echo start.bat
echo.
pause
endlocal
