@echo off
setlocal
cd /d "%~dp0"
python tools\release.py publish
set "PUBLISH_EXIT=%ERRORLEVEL%"
echo.
if not "%PUBLISH_EXIT%"=="0" echo Upload stopped. Read the error above.
pause
exit /b %PUBLISH_EXIT%
