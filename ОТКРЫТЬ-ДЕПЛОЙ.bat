@echo off
chcp 65001 >nul
set "SRC=%~dp0DEPLOY-NOW.txt"
if not exist "%SRC%" (
    echo Fayl ne nayden: %SRC%
    pause
    exit /b 1
)
set "TMP=%TEMP%\SongForge-DEPLOY-%RANDOM%.txt"
copy /Y "%SRC%" "%TMP%" >nul
start "" notepad.exe "%TMP%"