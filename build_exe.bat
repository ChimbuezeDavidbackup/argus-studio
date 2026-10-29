@echo off
setlocal enabledelayedexpansion
title Building Argus Studio Universal Suite
echo =======================================================
echo   Argus Studio - Universal Build & Packaging Suite
echo =======================================================
echo.

cd /d "%~dp0"

echo [1/3] Packaging Executable via ArgusStudio.spec...
python -m PyInstaller ArgusStudio.spec --noconfirm --clean

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PyInstaller build failed! Check errors above.
    pause
    exit /b %ERRORLEVEL%
)

if exist "dist\ArgusStudio.exe" (
    copy /Y "dist\ArgusStudio.exe" "dist\ArgusStudio-Portable.exe" >nul
    copy /Y "dist\ArgusStudio.exe" "dist\Argus Studio.exe" >nul
    echo [OK] Standalone executables ready in dist\
) else (
    echo [ERROR] dist\ArgusStudio.exe not found!
    pause
    exit /b 1
)

echo.
echo [2/3] Checking Inno Setup Compiler...
set "ISCC_PATH=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "!ISCC_PATH!" (
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    ) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
        set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
    )
)

if exist "!ISCC_PATH!" (
    echo [3/3] Compiling Windows Setup Wizard (.exe)...
    "!ISCC_PATH!" "%~dp0installer.iss"
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo =======================================================
        echo [SUCCESS] Windows Installer Ready:
        echo   dist\ArgusStudio-Setup.exe
        echo =======================================================
    ) else (
        echo [WARNING] Inno Setup compilation encountered an issue.
    )
) else (
    echo [NOTE] Inno Setup compiler not found. Standalone EXE is ready in dist\
)

echo.
echo Build process finished!
pause
