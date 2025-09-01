@echo off

REM Check if we're already running minimized, if not, restart minimized
if not "%1"=="minimized" (
    start /min cmd /c "%~f0" minimized
    exit
)

REM Activate the 'convertleica' conda environment
call conda activate convertleica

REM Change drive and directory to where this .cmd file is located
cd /d "%~dp0"

REM Run the ConvertLeicaQT.py GUI using pythonw to avoid console window
pythonw ConvertLeicaQT.py
if errorlevel 1 (
    REM If pythonw fails, show a message box instead of console
    echo Set objShell = CreateObject("WScript.Shell") > %temp%\error_msg.vbs
    echo objShell.Popup "Failed to launch ConvertLeicaQT.py. Please check the installation.", 0, "Error", 48 >> %temp%\error_msg.vbs
    cscript //nologo %temp%\error_msg.vbs
    del %temp%\error_msg.vbs
)
