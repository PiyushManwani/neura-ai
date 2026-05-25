@echo off
setlocal enabledelayedexpansion
title Neura AI - Uninstaller
color 0C

REM Change to the folder where this .bat file lives
cd /d "%~dp0"

echo.
echo ============================================================
echo    Neura AI - Complete Uninstaller
echo ============================================================
echo.
echo Running from: %CD%
echo.
echo This will remove:
echo   [1] neura command from PATH
echo   [2] All launchers in %%USERPROFILE%%\bin
echo   [3] Config folder (~/.config/neura-ai)
echo   [4] Old ollama-code config folder
echo   [5] Python packages (optional)
echo   [6] Files in current folder (optional)
echo.
echo ----- KEEPS by default: -----
echo   - Documents\history (your PDFs)
echo   - Ollama and downloaded models
echo.
echo ============================================================
echo.
set /p CONFIRM="Type YES to continue, anything else to cancel: "
if /i not "%CONFIRM%"=="YES" (
    echo.
    echo Cancelled. Nothing was removed.
    pause
    exit /b 0
)

echo.
echo Starting uninstall...
echo.

REM ============================================================
REM [1] Remove neura.bat and other launchers from bin folder
REM ============================================================
echo [1/6] Removing launchers from %USERPROFILE%\bin...
set "BIN_DIR=%USERPROFILE%\bin"
set "REMOVED=0"

if exist "%BIN_DIR%" (
    for %%F in ("%BIN_DIR%\*.bat") do (
        del /F /Q "%%F" >nul 2>&1
        if not exist "%%F" (
            echo       [OK] Removed: %%~nxF
            set /a REMOVED+=1
        )
    )
    if !REMOVED!==0 (
        echo       [INFO] No launchers found
    )
) else (
    echo       [INFO] Bin folder doesn't exist
)
echo.

REM ============================================================
REM [2] Remove bin folder from PATH (safely via PowerShell)
REM ============================================================
echo [2/6] Removing bin folder from PATH...
powershell -NoProfile -Command "$binDir = \"$env:USERPROFILE\bin\"; $currentPath = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($currentPath -like \"*$binDir*\") { $newPath = ($currentPath -split ';' | Where-Object { $_ -ne $binDir -and $_ -ne '' }) -join ';'; [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); Write-Host '      [OK] Removed from PATH' -ForegroundColor Green } else { Write-Host '      [INFO] Not in PATH' -ForegroundColor Yellow }"
echo.

REM ============================================================
REM [3] Remove Neura AI config folder
REM ============================================================
echo [3/6] Removing Neura AI config folder...
set "NEURA_CONFIG=%USERPROFILE%\.config\neura-ai"
if exist "%NEURA_CONFIG%" (
    rmdir /S /Q "%NEURA_CONFIG%"
    if not exist "%NEURA_CONFIG%" (
        echo       [OK] Removed: %NEURA_CONFIG%
    ) else (
        echo       [FAIL] Could not remove ^(in use?^)
    )
) else (
    echo       [INFO] Folder doesn't exist
)
echo.

REM ============================================================
REM [4] Remove old ollama-code config folder
REM ============================================================
echo [4/6] Removing old ollama-code config folder...
set "OLD_CONFIG=%USERPROFILE%\.config\ollama-code"
if exist "%OLD_CONFIG%" (
    rmdir /S /Q "%OLD_CONFIG%"
    if not exist "%OLD_CONFIG%" (
        echo       [OK] Removed: %OLD_CONFIG%
    ) else (
        echo       [FAIL] Could not remove ^(in use?^)
    )
) else (
    echo       [INFO] Folder doesn't exist
)
echo.

REM ============================================================
REM [5] Optional: Remove Python packages
REM ============================================================
echo [5/6] Python packages
echo.
echo Would you like to remove the Python packages too?
echo   - textual, httpx, reportlab, pypdf, customtkinter
echo.
echo WARNING: Other apps might use these. Only remove if you don't need them.
echo.
set /p REMOVE_PKG="Remove Python packages? (y/N): "
if /i "%REMOVE_PKG%"=="y" (
    echo.
    echo Uninstalling Python packages...
    python -m pip uninstall -y textual httpx reportlab pypdf customtkinter
    echo.
    echo       [OK] Packages removed
) else (
    echo       [SKIP] Keeping Python packages
)
echo.

REM ============================================================
REM [6] Optional: Delete files in current folder
REM ============================================================
echo [6/6] Files in this folder (%CD%)
echo.
echo Files currently in this folder:
dir /B "%CD%" 2>nul
echo.
echo Would you like to delete the Python files in THIS folder?
echo   (ollama_code.py, neura_installer.py, validate-*.bat, etc.)
echo.
set /p DELETE_FILES="Delete Python files in current folder? (y/N): "
if /i "%DELETE_FILES%"=="y" (
    echo.
    set "FILES_DELETED=0"
    for %%F in (
        "ollama_code.py"
        "neura_installer.py"
        "add-to-path.py"
        "validate-ollama-python-installation.bat"
        "auto-fix-installation.bat"
        "install-ollama.bat"
        "build_exe.bat"
        "setup_neura.bat"
        "setup_neura.ps1"
        "Neura Installer.exe"
    ) do (
        if exist "%CD%\%%~F" (
            del /F /Q "%CD%\%%~F" >nul 2>&1
            if not exist "%CD%\%%~F" (
                echo       [OK] Deleted: %%~F
                set /a FILES_DELETED+=1
            )
        )
    )
    if !FILES_DELETED!==0 (
        echo       [INFO] No matching files found
    ) else (
        echo.
        echo       [OK] !FILES_DELETED! file(s) deleted
    )
) else (
    echo       [SKIP] Keeping files in this folder
)
echo.

REM ============================================================
REM Done!
REM ============================================================
color 0A
echo ============================================================
echo    UNINSTALL COMPLETE!
echo ============================================================
echo.
echo To finish:
echo   1. Close ALL terminal windows
echo   2. The 'neura' command will no longer work
echo.
echo Still on your system:
echo   - Documents\history folder ^(your PDFs^) - KEPT
echo   - Ollama and your downloaded models - KEPT
echo.
echo To remove those too:
echo   - Delete: %USERPROFILE%\OneDrive\Documents\history
echo   - Settings ^> Apps ^> Ollama ^> Uninstall
echo.
echo ============================================================
echo.
pause
endlocal