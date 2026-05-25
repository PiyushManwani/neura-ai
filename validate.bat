@echo off
setlocal EnableDelayedExpansion
title Neura AI Setup
color 0B

cd /d "%~dp0"

echo.
echo ============================================================
echo    Neura AI - Complete Setup
echo ============================================================
echo.
echo Running from: %CD%
echo.
echo This script will:
echo   [1] Check Python 3.13
echo   [2] Check pip
echo   [3] Install Python packages
echo   [4] Check Ollama
echo   [5] Start Ollama service
echo   [6] Create your custom 'neura' AI model
echo   [7] Find ollama_code.py
echo   [8] Set up 'neura' terminal command
echo.
echo Nothing installs without your permission!
echo.
echo ============================================================
echo.
pause

set "PASS=0"
set "FAIL=0"
set "WARN=0"
set "FOUND_PY="

REM ============================================================
REM [1] Python 3.13
REM ============================================================
echo.
echo [1/8] Checking Python 3.13
echo ------------------------------------------------------------

python --version >nul 2>&1
if errorlevel 1 (
    echo       [FAIL] Python not found
    echo.
    set /p ACTION="       Install Python 3.13 from MS Store? (y/N): "
    if /i "!ACTION!"=="y" (
        echo       Opening Microsoft Store...
        start ms-windows-store://pdp/?productid=9PNRBTZXMB4Z
        echo       After installing, press any key here...
        pause >nul
        python --version >nul 2>&1
        if errorlevel 1 (
            echo       [FAIL] Python still not detected. Open a new terminal.
            set /a FAIL+=1
        ) else (
            echo       [OK] Python now detected
            set /a PASS+=1
        )
    ) else (
        echo       [FAIL] Cannot continue without Python
        set /a FAIL+=1
        goto :summary
    )
) else (
    for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PYVER=%%V"
    echo       Found: Python !PYVER!
    echo !PYVER! | findstr /B "3.13" >nul
    if errorlevel 1 (
        echo       [WARN] Not Python 3.13 ^(you have !PYVER!^)
        echo       [INFO] Continuing anyway - should still work
        set /a WARN+=1
    ) else (
        echo       [OK] Python 3.13 detected
        set /a PASS+=1
    )
)

REM ============================================================
REM [2] pip
REM ============================================================
echo.
echo [2/8] Checking pip
echo ------------------------------------------------------------

python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo       [WARN] pip not working - bootstrapping...
    python -m ensurepip --default-pip >nul 2>&1
    if errorlevel 1 (
        echo       [FAIL] Could not install pip
        set /a FAIL+=1
    ) else (
        echo       [OK] pip installed
        set /a PASS+=1
    )
) else (
    echo       [OK] pip is working
    set /a PASS+=1
)

REM ============================================================
REM [3] Python packages
REM ============================================================
echo.
echo [3/8] Installing Python packages
echo ------------------------------------------------------------
echo.
set /p ACTION="       Install/upgrade packages? (Y/n): "
if /i "!ACTION!"=="n" (
    echo       [SKIP] Skipping package install
    set /a WARN+=1
    goto :step4
)

echo.
echo       Installing required packages...
echo.

set "PKG_FAIL=0"
call :install_pkg textual
call :install_pkg httpx
call :install_pkg reportlab
call :install_pkg pypdf

echo.
if !PKG_FAIL! equ 0 (
    echo       [OK] All required packages installed
    set /a PASS+=1
) else (
    echo       [WARN] !PKG_FAIL! package^(s^) failed
    set /a WARN+=1
)

echo.
echo       Installing optional: pyperclip
python -m pip install --quiet pyperclip >nul 2>&1
if errorlevel 1 (
    echo       [INFO] pyperclip skipped ^(optional^)
) else (
    echo       [OK] pyperclip installed
)

goto :step4

:install_pkg
echo       Installing %~1...
python -m pip install --quiet --upgrade %~1
if errorlevel 1 (
    echo       [FAIL] %~1 failed
    set /a PKG_FAIL+=1
) else (
    echo       [OK] %~1 installed
)
goto :eof

REM ============================================================
REM [4] Ollama
REM ============================================================
:step4
echo.
echo [4/8] Checking Ollama
echo ------------------------------------------------------------

ollama --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%V in ('ollama --version 2^>^&1') do set "OLLVER=%%V"
    echo       [OK] !OLLVER!
    set /a PASS+=1
    goto :step5
)

echo       [WARN] Ollama not in PATH

if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo       [INFO] Ollama installed but PATH missing - fixing...
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
    powershell -NoProfile -Command "$op = \"$env:LOCALAPPDATA\Programs\Ollama\"; $cp = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($cp -notlike \"*$op*\") { [Environment]::SetEnvironmentVariable('Path', \"$cp;$op\", 'User'); Write-Host '       [OK] PATH updated' } else { Write-Host '       [OK] Already in PATH' }"
    set /a PASS+=1
    goto :step5
)

echo       [INFO] Ollama is not installed
echo.
set /p ACTION="       Install Ollama via winget? (y/N): "
if /i not "!ACTION!"=="y" (
    echo       [SKIP] Get it from: https://ollama.com/download/windows
    set /a WARN+=1
    goto :step5
)

where winget >nul 2>&1
if errorlevel 1 (
    echo       [FAIL] winget not available - opening download page
    start https://ollama.com/download/windows
    set /a FAIL+=1
    goto :step5
)

echo.
echo       Installing Ollama ^(1-2 minutes^)...
winget install --id Ollama.Ollama --silent --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo       [FAIL] winget install failed
    start https://ollama.com/download/windows
    set /a FAIL+=1
) else (
    echo       [OK] Ollama installed
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
    set /a PASS+=1
    timeout /t 3 /nobreak >nul
)

REM ============================================================
REM [5] Ollama running
REM ============================================================
:step5
echo.
echo [5/8] Checking if Ollama service is running
echo ------------------------------------------------------------

python -c "import httpx; httpx.get('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if not errorlevel 1 (
    echo       [OK] Ollama is running
    set /a PASS+=1
    goto :step6
)

echo       [WARN] Ollama not responding - trying to start...

if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
    start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    echo       Waiting 5 seconds...
    timeout /t 5 /nobreak >nul
    
    python -c "import httpx; httpx.get('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
    if not errorlevel 1 (
        echo       [OK] Ollama is now running
        set /a PASS+=1
    ) else (
        echo       [WARN] Could not auto-start - open Ollama from Start Menu
        set /a WARN+=1
        goto :step7
    )
) else (
    echo       [WARN] Ollama executable not found
    set /a WARN+=1
    goto :step7
)

REM ============================================================
REM [6] Create Neura model
REM ============================================================
:step6
echo.
echo [6/8] Creating your custom 'neura' AI model
echo ------------------------------------------------------------

REM Check if neura model already exists
python -c "import httpx; r = httpx.get('http://localhost:11434/api/tags', timeout=3); ms = [m['name'] for m in r.json().get('models', [])]; exit(0 if any(n.startswith('neura') for n in ms) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo       [OK] 'neura' model already exists
    echo.
    set /p ACTION="       Recreate it? (y/N): "
    if /i not "!ACTION!"=="y" (
        set /a PASS+=1
        goto :step7
    )
)

echo.
echo       To create 'neura', we need a tiny base model.
echo       Base: qwen2.5:0.5b ^(only 397 MB^)
echo.
set /p ACTION="       Create 'neura' model now? (Y/n): "
if /i "!ACTION!"=="n" (
    echo       [SKIP] Skipping neura model creation
    set /a WARN+=1
    goto :step7
)

REM Check for base model
echo.
echo       Checking for base model qwen2.5:0.5b...
python -c "import httpx; r = httpx.get('http://localhost:11434/api/tags', timeout=3); ms = [m['name'] for m in r.json().get('models', [])]; exit(0 if any('qwen2.5:0.5b' in n for n in ms) else 1)" >nul 2>&1
if errorlevel 1 (
    echo       [INFO] Pulling qwen2.5:0.5b ^(397 MB^)...
    ollama pull qwen2.5:0.5b
    if errorlevel 1 (
        echo       [FAIL] Pull failed - check connection
        set /a FAIL+=1
        goto :step7
    )
    echo       [OK] Base model pulled
) else (
    echo       [OK] Base model already exists
)

REM Create Modelfile
echo.
echo       Writing Modelfile...
set "MODELFILE=%TEMP%\Neura.Modelfile"
if exist "%MODELFILE%" del "%MODELFILE%"

>"%MODELFILE%" echo FROM qwen2.5:0.5b
>>"%MODELFILE%" echo.
>>"%MODELFILE%" echo PARAMETER temperature 0.8
>>"%MODELFILE%" echo PARAMETER top_p 0.9
>>"%MODELFILE%" echo PARAMETER num_ctx 8192
>>"%MODELFILE%" echo PARAMETER repeat_penalty 1.1
>>"%MODELFILE%" echo.
>>"%MODELFILE%" echo SYSTEM You are Neura, a helpful and friendly AI assistant. You are warm, curious, and slightly playful. You explain things clearly with examples and use emojis occasionally. Keep responses focused. Always introduce yourself as Neura when asked.

if not exist "%MODELFILE%" (
    echo       [FAIL] Could not write Modelfile
    set /a FAIL+=1
    goto :step7
)
echo       [OK] Modelfile created

REM Build the model
echo.
echo       Building 'neura' model ^(about 10 seconds^)...
ollama create neura -f "%MODELFILE%"
if errorlevel 1 (
    echo       [FAIL] Model creation failed
    set /a FAIL+=1
) else (
    echo.
    echo       [OK] 'neura' model created!
    echo       It now appears in 'ollama list' as 'neura:latest'
    set /a PASS+=1
)

if exist "%MODELFILE%" del "%MODELFILE%" >nul 2>&1

REM ============================================================
REM [7] Find ollama_code.py
REM ============================================================
:step7
echo.
echo [7/8] Finding ollama_code.py
echo ------------------------------------------------------------

if exist "%CD%\ollama_code.py" (
    set "FOUND_PY=%CD%\ollama_code.py"
    goto :found_py
)

for %%P in (
    "%USERPROFILE%\OneDrive\Documents\ollama_code.py"
    "%USERPROFILE%\OneDrive\Documents\neura ai\ollama_code.py"
    "%USERPROFILE%\Documents\ollama_code.py"
    "%USERPROFILE%\Documents\neura ai\ollama_code.py"
    "%USERPROFILE%\Desktop\ollama_code.py"
    "%USERPROFILE%\Downloads\ollama_code.py"
) do (
    if exist %%P (
        if not defined FOUND_PY set "FOUND_PY=%%~P"
    )
)

if defined FOUND_PY (
    :found_py
    echo       [OK] Found: !FOUND_PY!
    set /a PASS+=1
) else (
    echo       [WARN] ollama_code.py not found
    echo       Save it somewhere ^(e.g., Documents folder^)
    set /a WARN+=1
    goto :summary
)

REM ============================================================
REM [8] Setup neura command
REM ============================================================
echo.
echo [8/8] Setting up 'neura' terminal command
echo ------------------------------------------------------------

set "BIN_DIR=%USERPROFILE%\bin"

if exist "%BIN_DIR%\neura.bat" (
    echo       [INFO] neura.bat already exists
    echo.
    set /p ACTION="       Update to point to current script? (y/N): "
    if /i "!ACTION!"=="y" (
        goto :write_bat
    )
    echo       [OK] Keeping existing launcher
    set /a PASS+=1
    goto :summary
)

echo.
echo       This lets you type 'neura' in any terminal to launch!
echo.
set /p ACTION="       Set up 'neura' command? (Y/n): "
if /i "!ACTION!"=="n" (
    echo       [SKIP] Launch with: python "!FOUND_PY!"
    set /a WARN+=1
    goto :summary
)

:write_bat
if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

>"%BIN_DIR%\neura.bat" echo @echo off
>>"%BIN_DIR%\neura.bat" echo python "!FOUND_PY!" %%*

if exist "%BIN_DIR%\neura.bat" (
    echo       [OK] Created: %BIN_DIR%\neura.bat
    echo       [OK] Points to: !FOUND_PY!
) else (
    echo       [FAIL] Could not create launcher
    set /a FAIL+=1
    goto :summary
)

REM Add to PATH safely
echo.
echo       Adding %BIN_DIR% to PATH...
powershell -NoProfile -Command "$bd = \"$env:USERPROFILE\bin\"; $cp = [Environment]::GetEnvironmentVariable('Path', 'User'); if (-not $cp) { $cp = '' }; if ($cp -notlike \"*$bd*\") { $np = if ($cp) { \"$cp;$bd\" } else { $bd }; [Environment]::SetEnvironmentVariable('Path', $np, 'User'); Write-Host '       [OK] Added to PATH' } else { Write-Host '       [OK] Already in PATH' }"

set /a PASS+=1

REM ============================================================
REM SUMMARY
REM ============================================================
:summary
echo.
echo ============================================================
echo                       SUMMARY
echo ============================================================
echo.
echo   [PASS]    !PASS! checks passed
echo   [WARN]    !WARN! warnings
echo   [FAIL]    !FAIL! checks failed
echo.

if !FAIL! gtr 0 (
    color 0C
    echo   ============================================
    echo    INCOMPLETE - Fix critical issues above
    echo   ============================================
    goto :end
)

if !WARN! gtr 0 (
    color 0E
    echo   ============================================
    echo    READY with warnings
    echo   ============================================
    echo.
    echo   Most things work! Check warnings above.
) else (
    color 0A
    echo   ============================================
    echo    PERFECT! Everything is ready!
    echo   ============================================
)

echo.
if exist "%USERPROFILE%\bin\neura.bat" (
    echo   IMPORTANT: Close this terminal and open a new one
    echo   for the 'neura' command to work!
    echo.
    echo   Then type:    neura
) else if defined FOUND_PY (
    echo   Launch with:
    echo     python "!FOUND_PY!"
)
echo.
echo   Inside the app, select your custom model:
echo     /model neura
echo.
echo   You're now chatting with YOUR own AI! :^)
echo.

:end
echo ============================================================
echo.
pause
endlocal