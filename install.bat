@echo off
setlocal EnableDelayedExpansion
title Neura AI - Installer
color 0B

cd /d "%~dp0"
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

cls
echo.
echo  ============================================================
echo.
echo            _   _ ______ _    _ _____            
echo           ^| \ ^| ^|  ____^| ^|  ^| ^|  __ \     /\    
echo           ^|  \^| ^| ^|__  ^| ^|  ^| ^| ^|__) ^|   /  \   
echo           ^| . ` ^|  __^| ^| ^|  ^| ^|  _  /   / /\ \  
echo           ^| ^|\  ^| ^|____^| ^|__^| ^| ^| \ \  / ____ \ 
echo           ^|_^| \_^|______^|\____/^|_^|  \_\/_/    \_\
echo.
echo                    Personal AI Assistant
echo                   Powered by Ollama + Python
echo.
echo  ============================================================
echo.
echo  Installing from: %SCRIPT_DIR%
echo.
echo  This installer will set up:
echo    [1] Python 3.13 (via Microsoft Store if missing)
echo    [2] Python packages (textual, httpx, reportlab, pypdf)
echo    [3] Ollama (via winget if missing)
echo    [4] Ollama service (auto-started)
echo    [5] qwen2.5:0.5b base model (397MB)
echo    [6] 'neura' custom AI model
echo    [7] 'neura' command in your PATH
echo.
echo  Total download: ~500MB ^| Time: ~5 minutes
echo  Nothing installs without your permission.
echo.
echo  ============================================================
echo.
set /p START="  Ready to install? (Y/n): "
if /i "!START!"=="n" (
    echo.
    echo  Installation cancelled.
    pause
    exit /b 0
)

REM Pre-flight checks
if not exist "%SCRIPT_DIR%\ollama_code.py" (
    color 0C
    echo.
    echo  [ERROR] ollama_code.py not found in this folder!
    echo.
    echo  Make sure you cloned/downloaded the full repo and are
    echo  running install.bat from the repo's root folder.
    echo.
    pause
    exit /b 1
)

set "PASS=0"
set "FAIL=0"
set "WARN=0"

REM ============================================================
REM [1] Python 3.13
REM ============================================================
echo.
echo  [1/7] Checking Python...
echo  ------------------------------------------------------------

python --version >nul 2>&1
if errorlevel 1 (
    echo        [INFO] Python not found
    echo.
    set /p ACTION="        Install Python 3.13 from MS Store? (Y/n): "
    if /i "!ACTION!"=="n" (
        echo        [FAIL] Cannot continue without Python
        set /a FAIL+=1
        goto :summary
    )
    
    echo        Opening Microsoft Store...
    start ms-windows-store://pdp/?productid=9PNRBTZXMB4Z
    echo.
    echo        Please click "Get" or "Install" in the Store window.
    echo        After installation completes, return here.
    echo.
    pause
    
    python --version >nul 2>&1
    if errorlevel 1 (
        echo        [FAIL] Python still not detected
        echo        Try closing this window and running install.bat again
        set /a FAIL+=1
        goto :summary
    )
    echo        [OK] Python detected
    set /a PASS+=1
) else (
    for /f "tokens=2" %%V in ('python --version 2^>^&1') do set "PYVER=%%V"
    echo        [OK] Python !PYVER! found
    set /a PASS+=1
)

REM ============================================================
REM [2] Python packages
REM ============================================================
echo.
echo  [2/7] Installing Python packages...
echo  ------------------------------------------------------------
echo.

REM Use requirements.txt if it exists, otherwise install individually
if exist "%SCRIPT_DIR%\requirements.txt" (
    echo        Installing from requirements.txt...
    python -m pip install --quiet --upgrade -r "%SCRIPT_DIR%\requirements.txt"
    if errorlevel 1 (
        echo        [WARN] Some packages failed
        set /a WARN+=1
    ) else (
        echo        [OK] All packages installed
        set /a PASS+=1
    )
) else (
    set "PKG_FAIL=0"
    for %%P in (textual httpx reportlab pypdf) do (
        echo        Installing %%P...
        python -m pip install --quiet --upgrade %%P
        if errorlevel 1 (
            echo        [FAIL] %%P failed
            set /a PKG_FAIL+=1
        ) else (
            echo        [OK] %%P
        )
    )
    if !PKG_FAIL! equ 0 (
        set /a PASS+=1
    ) else (
        set /a WARN+=1
    )
)

REM Optional pyperclip
python -m pip install --quiet pyperclip >nul 2>&1

REM ============================================================
REM [3] Ollama
REM ============================================================
echo.
echo  [3/7] Checking Ollama...
echo  ------------------------------------------------------------

ollama --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%V in ('ollama --version 2^>^&1') do set "OLLVER=%%V"
    echo        [OK] !OLLVER!
    set /a PASS+=1
    goto :step4
)

if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
    echo        [INFO] Ollama installed but not in PATH - fixing...
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
    powershell -NoProfile -Command "$op = \"$env:LOCALAPPDATA\Programs\Ollama\"; $cp = [Environment]::GetEnvironmentVariable('Path', 'User'); if ($cp -notlike \"*$op*\") { [Environment]::SetEnvironmentVariable('Path', \"$cp;$op\", 'User') }" >nul
    echo        [OK] PATH fixed
    set /a PASS+=1
    goto :step4
)

echo        [INFO] Ollama not installed
echo.
set /p ACTION="        Install Ollama via winget? (Y/n): "
if /i "!ACTION!"=="n" (
    echo        [SKIP] Get it from: https://ollama.com/download/windows
    start https://ollama.com/download/windows
    set /a WARN+=1
    goto :step4
)

where winget >nul 2>&1
if errorlevel 1 (
    echo        [FAIL] winget not available - opening download page
    start https://ollama.com/download/windows
    set /a FAIL+=1
    goto :step4
)

echo.
echo        Installing Ollama ^(1-2 minutes^)...
winget install --id Ollama.Ollama --silent --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo        [FAIL] Install failed - try manual download
    start https://ollama.com/download/windows
    set /a FAIL+=1
) else (
    echo        [OK] Ollama installed
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
    set /a PASS+=1
    timeout /t 3 /nobreak >nul
)

REM ============================================================
REM [4] Start Ollama
REM ============================================================
:step4
echo.
echo  [4/7] Starting Ollama service...
echo  ------------------------------------------------------------

python -c "import httpx; httpx.get('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
if not errorlevel 1 (
    echo        [OK] Ollama is running
    set /a PASS+=1
    goto :step5
)

if exist "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe" (
    start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    echo        Waiting for Ollama to start...
    timeout /t 5 /nobreak >nul
    
    python -c "import httpx; httpx.get('http://localhost:11434/api/tags', timeout=3)" >nul 2>&1
    if not errorlevel 1 (
        echo        [OK] Ollama started
        set /a PASS+=1
    ) else (
        echo        [WARN] Could not auto-start - open Ollama from Start Menu
        set /a WARN+=1
        goto :step6
    )
) else (
    echo        [WARN] Ollama executable not found
    set /a WARN+=1
    goto :step6
)

REM ============================================================
REM [5] Pull base model
REM ============================================================
:step5
echo.
echo  [5/7] Setting up base model...
echo  ------------------------------------------------------------

python -c "import httpx; r = httpx.get('http://localhost:11434/api/tags', timeout=3); ms = [m['name'] for m in r.json().get('models', [])]; exit(0 if any('qwen2.5:0.5b' in n for n in ms) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo        [OK] qwen2.5:0.5b already installed
    set /a PASS+=1
    goto :step6
)

echo        [INFO] Pulling qwen2.5:0.5b ^(397 MB^)...
echo.
ollama pull qwen2.5:0.5b
if errorlevel 1 (
    echo        [FAIL] Pull failed - check connection
    set /a FAIL+=1
) else (
    echo        [OK] Base model installed
    set /a PASS+=1
)

REM ============================================================
REM [6] Build neura model
REM ============================================================
:step6
echo.
echo  [6/7] Building 'neura' AI model...
echo  ------------------------------------------------------------

python -c "import httpx; r = httpx.get('http://localhost:11434/api/tags', timeout=3); ms = [m['name'] for m in r.json().get('models', [])]; exit(0 if any(n.startswith('neura') for n in ms) else 1)" >nul 2>&1
if not errorlevel 1 (
    echo        [OK] 'neura' model already exists
    set /a PASS+=1
    goto :step7
)

set "MODELFILE=%SCRIPT_DIR%\Neura.Modelfile"

REM Create default Modelfile if not bundled
if not exist "%MODELFILE%" (
    echo        [INFO] Creating default Neura.Modelfile...
    >"%MODELFILE%" echo FROM qwen2.5:0.5b
    >>"%MODELFILE%" echo.
    >>"%MODELFILE%" echo PARAMETER temperature 0.8
    >>"%MODELFILE%" echo PARAMETER top_p 0.9
    >>"%MODELFILE%" echo PARAMETER num_ctx 8192
    >>"%MODELFILE%" echo PARAMETER repeat_penalty 1.1
    >>"%MODELFILE%" echo.
    >>"%MODELFILE%" echo SYSTEM You are Neura, a helpful and friendly AI assistant. You are warm, curious, and slightly playful. You explain things clearly with examples and use emojis occasionally. Keep responses focused. Always introduce yourself as Neura when asked.
)

echo        Building from: %MODELFILE%
echo.
ollama create neura -f "%MODELFILE%"
if errorlevel 1 (
    echo        [FAIL] Model creation failed
    set /a FAIL+=1
) else (
    echo        [OK] 'neura' model created!
    set /a PASS+=1
)

REM ============================================================
REM [7] Add to PATH
REM ============================================================
:step7
echo.
echo  [7/7] Installing 'neura' command...
echo  ------------------------------------------------------------

set "BIN_DIR=%USERPROFILE%\bin"
set "FOUND_PY=%SCRIPT_DIR%\ollama_code.py"

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

>"%BIN_DIR%\neura.bat" echo @echo off
>>"%BIN_DIR%\neura.bat" echo python "!FOUND_PY!" %%*

if exist "%BIN_DIR%\neura.bat" (
    echo        [OK] Created: %BIN_DIR%\neura.bat
) else (
    echo        [FAIL] Could not create launcher
    set /a FAIL+=1
    goto :summary
)

REM Add to PATH (permanent)
powershell -NoProfile -Command "$bd = \"$env:USERPROFILE\bin\"; $cp = [Environment]::GetEnvironmentVariable('Path', 'User'); if (-not $cp) { $cp = '' }; if ($cp -notlike \"*$bd*\") { $np = if ($cp) { \"$cp;$bd\" } else { $bd }; [Environment]::SetEnvironmentVariable('Path', $np, 'User'); Write-Host '        [OK] Added to PATH (permanent)' } else { Write-Host '        [OK] Already in PATH' }"

REM Update current session
set "PATH=%PATH%;%BIN_DIR%"

REM Test
where neura >nul 2>&1
if not errorlevel 1 (
    echo        [OK] 'neura' command works!
    set /a PASS+=1
) else (
    echo        [WARN] Command may need a new terminal
    set /a WARN+=1
)

REM ============================================================
REM SUMMARY
REM ============================================================
:summary
echo.
echo  ============================================================
echo.

if !FAIL! gtr 0 (
    color 0C
    echo            [X] INSTALLATION INCOMPLETE
    echo.
    echo            !FAIL! critical issue^(s^) need fixing.
    echo            See errors above and try again.
    goto :end
)

if !WARN! gtr 0 (
    color 0E
    echo            [!] INSTALLED WITH WARNINGS
    echo.
    echo            Most things work! Check warnings above.
) else (
    color 0A
    echo            [OK] INSTALLATION COMPLETE!
    echo.
    echo            Everything is ready to go!
)

echo.
echo  ============================================================
echo.
echo    QUICK START:
echo.
echo      1. Open a new terminal ^(or use this one^)
echo      2. Type:  neura
echo      3. Inside the app, type:  /model neura
echo      4. Start chatting with YOUR own AI!
echo.
echo    CUSTOMIZE:
echo.
echo      Edit Neura.Modelfile to change personality:
echo        %SCRIPT_DIR%\Neura.Modelfile
echo.
echo      Then re-run install.bat to rebuild.
echo.
echo    UNINSTALL:
echo.
echo      Run uninstall.bat in this folder.
echo.
echo  ============================================================
echo.

:end
pause
endlocal