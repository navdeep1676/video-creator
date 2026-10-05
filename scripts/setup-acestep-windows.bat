@echo off
setlocal EnableExtensions
REM One-time ACE-Step 1.5 setup for Windows 11 + AMD RX 9060 XT.
REM Installs into %USERPROFILE%\ACE-Step-1.5. Does not use uv sync:
REM that command installs CUDA PyTorch and hides the AMD GPU.
REM Requires: Windows 11, AMD driver 26.1.1 or newer, about 15 GB free disk.

set "ACE_DIR=%USERPROFILE%\ACE-Step-1.5"
set "VENV=%ACE_DIR%\venv_rocm"
set "ROCM=https://repo.radeon.com/rocm/windows/rocm-rel-7.2"

echo.
echo ACE-Step 1.5 setup for the RX 9060 XT
echo Install folder: %ACE_DIR%
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo Git was not found. Installing Git with winget...
  winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto :fail
  echo Close this window, open a new one, and run this script again so Git is on PATH.
  pause
  exit /b 1
)

call :find_python
if not defined PY (
  echo Python 3.12 was not found. Installing it with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  call :find_python
)
if not defined PY (
  echo Install Python 3.12 from https://www.python.org/downloads/windows/
  echo Tick "Add python.exe to PATH", then run this script again.
  goto :fail
)
echo Using %PY%
"%PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)"
if errorlevel 1 (
  echo ACE-Step ROCm on Windows needs Python 3.12. Found:
  "%PY%" -c "import sys; print(sys.version)"
  goto :fail
)

if not exist "%ACE_DIR%\acestep\api_server.py" (
  echo Cloning ACE-Step 1.5...
  git clone --depth 1 https://github.com/ace-step/ACE-Step-1.5.git "%ACE_DIR%"
  if errorlevel 1 goto :fail
)

if not exist "%VENV%\Scripts\python.exe" (
  echo Creating venv_rocm...
  "%PY%" -m venv "%VENV%"
  if errorlevel 1 goto :fail
)

set "PYV=%VENV%\Scripts\python.exe"
"%PYV%" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo Installing AMD ROCm 7.2 and PyTorch. This download is large.
"%PYV%" -m pip install --no-cache-dir ^
  "%ROCM%/rocm_sdk_core-7.2.0.dev0-py3-none-win_amd64.whl" ^
  "%ROCM%/rocm_sdk_devel-7.2.0.dev0-py3-none-win_amd64.whl" ^
  "%ROCM%/rocm_sdk_libraries_custom-7.2.0.dev0-py3-none-win_amd64.whl" ^
  "%ROCM%/rocm-7.2.0.dev0.tar.gz"
if errorlevel 1 goto :wheels_failed

"%PYV%" -m pip install --no-cache-dir ^
  "%ROCM%/torch-2.9.1+rocmsdk20260116-cp312-cp312-win_amd64.whl" ^
  "%ROCM%/torchaudio-2.9.1+rocmsdk20260116-cp312-cp312-win_amd64.whl" ^
  "%ROCM%/torchvision-0.24.1+rocmsdk20260116-cp312-cp312-win_amd64.whl"
if errorlevel 1 goto :wheels_failed

echo Installing ACE-Step Python packages...
"%PYV%" -m pip install --no-cache-dir -r "%ACE_DIR%\requirements-rocm.txt"
if errorlevel 1 goto :fail

if not exist "%ACE_DIR%\.env" (
  > "%ACE_DIR%\.env" echo ACESTEP_LM_BACKEND=pt
  >> "%ACE_DIR%\.env" echo ACESTEP_OFFLOAD_TO_CPU=true
  >> "%ACE_DIR%\.env" echo ACESTEP_CONFIG_PATH=acestep-v15-turbo
  >> "%ACE_DIR%\.env" echo ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B
  >> "%ACE_DIR%\.env" echo ACESTEP_INIT_LLM=false
  >> "%ACE_DIR%\.env" echo ACESTEP_API_HOST=127.0.0.1
  >> "%ACE_DIR%\.env" echo ACESTEP_API_PORT=8001
)

echo.
echo Setup finished.
echo Next: double-click scripts\start-acestep-windows.bat
echo The first music request downloads about 10 GB of weights.
echo.
pause
exit /b 0

:find_python
set "PY="
py -3.12 -c "import sys; print(sys.executable)" > "%TEMP%\acestep-py.txt" 2>nul
if not errorlevel 1 set /p PY=<"%TEMP%\acestep-py.txt"
if defined PY exit /b 0
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY exit /b 0
if exist "%ProgramFiles%\Python312\python.exe" set "PY=%ProgramFiles%\Python312\python.exe"
exit /b 0

:wheels_failed
echo.
echo The ROCm wheel download failed.
echo Open %ACE_DIR%\requirements-rocm.txt and use the wheel URLs listed there.
echo AMD publishes new builds, so a pinned file name can change.
goto :fail

:fail
echo.
echo Setup stopped.
pause
exit /b 1
