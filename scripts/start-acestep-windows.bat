@echo off
setlocal EnableExtensions
REM Start the ACE-Step 1.5 API for Naratto on an AMD RX 9060 XT.
REM Listens on http://127.0.0.1:8001. Naratto stays on port 8000.
REM Run scripts\setup-acestep-windows.bat once before this.

set "ACE_DIR=%USERPROFILE%\ACE-Step-1.5"
set "PY=%ACE_DIR%\venv_rocm\Scripts\python.exe"

if not exist "%PY%" (
  echo ACE-Step is not installed. Run scripts\setup-acestep-windows.bat first.
  pause
  exit /b 1
)
if not exist "%ACE_DIR%\acestep\api_server.py" (
  echo Missing %ACE_DIR%\acestep\api_server.py
  pause
  exit /b 1
)

REM RX 9000 series, including the 9060 XT, uses the same override ACE-Step
REM documents for the RX 9070 XT. Do not start the vLLM backend on AMD.
set ACESTEP_LM_BACKEND=pt
set ACESTEP_OFFLOAD_TO_CPU=true
set ACESTEP_CONFIG_PATH=acestep-v15-turbo
set ACESTEP_LM_MODEL_PATH=acestep-5Hz-lm-0.6B
set ACESTEP_INIT_LLM=false
set HSA_OVERRIDE_GFX_VERSION=11.0.0
set MIOPEN_FIND_MODE=FAST
set TORCH_COMPILE_BACKEND=eager
set TOKENIZERS_PARALLELISM=false

echo.
echo ACE-Step API: http://127.0.0.1:8001
echo Health:      http://127.0.0.1:8001/health
echo Leave this window open. Close it to stop the server.
echo After each song the model leaves the GPU until the next song.
echo.

cd /d "%ACE_DIR%"
"%PY%" -c "import torch; assert torch.cuda.is_available(), 'GPU not visible'; print(torch.cuda.get_device_name(0)); print('HIP', getattr(torch.version, 'hip', None))"
if errorlevel 1 (
  echo.
  echo PyTorch cannot see the RX 9060 XT.
  echo Confirm Windows 11 and AMD Software 26.1.1 or newer, then run this again.
  pause
  exit /b 1
)

"%PY%" -u acestep\api_server.py --host 127.0.0.1 --port 8001
echo.
echo ACE-Step stopped.
pause
exit /b 0
