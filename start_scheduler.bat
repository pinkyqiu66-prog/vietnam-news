@echo off
:: 检查 scheduler 是否已在运行
tasklist /fi "imagename eq pythonw.exe" /fi "windowtitle eq VietnamNewsScheduler" 2>nul | find /i "pythonw.exe" >nul
if not errorlevel 1 (
    echo Scheduler is already running.
    pause
    exit /b 0
)

:: 用 pythonw（无黑窗口）后台运行
start "VietnamNewsScheduler" /min "C:\Program Files\Python38\pythonw.exe" "D:\AI\vietnam_news\scheduler.py" --no-init
echo Scheduler started in background.
echo Log: D:\AI\vietnam_news\scheduler.log
timeout /t 3 >nul
