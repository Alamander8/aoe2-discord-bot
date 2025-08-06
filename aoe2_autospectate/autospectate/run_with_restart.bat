@echo off
cd /d "C:\Users\Alex Hogancamp\Desktop\repos\aoe2-discord-bot\aoe2_autospectate\autospectate"



:restart_loop
echo Starting AoE2 AutoSpectate...

REM Check if CaptureAge is running, start it if not
tasklist /FI "IMAGENAME eq CaptureAge.exe" 2>NUL | find /I /N "CaptureAge.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo CaptureAge not running - starting it...
    start "" "C:\Users\Alex Hogancamp\AppData\Local\Programs\CaptureAge\CaptureAge.exe"
    echo Waiting 15 seconds for CaptureAge to load...
    timeout /t 15
)

REM Make sure OBS is running (just a check, don't start it)
tasklist /FI "IMAGENAME eq obs64.exe" 2>NUL | find /I /N "obs64.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo WARNING: OBS not detected - make sure OBS is running!
    echo Press any key to continue anyway, or Ctrl+C to abort...
    pause
)

echo Starting Python script...
python main_flow.py

if %ERRORLEVEL% == 42 (
    echo Nuclear restart requested - restarting in 10 seconds...
    timeout /t 10
    goto restart_loop
) else (
    echo Script exited with code %ERRORLEVEL%
    if %ERRORLEVEL% == 0 (
        echo Normal exit
    ) else (
        echo Error exit - restarting in 30 seconds...
        timeout /t 30
        goto restart_loop
    )
)

pause