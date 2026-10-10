# Start, stop, restart, or show Naratto on this PC.
# Wan 2.2 TI2V 5B is not a separate server. It loads inside the render worker
# (Wan-AI/Wan2.2-TI2V-5B-Diffusers). WAN_T2V_PRELOAD is never written to .env.
# Pass -PreloadWan to keep the weights in that worker only. That mode does not
# start ComfyUI or ACE-Step, because those three cannot share the GPU.
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "help", "logs", "preload", "all")]
    [string]$Action = "start",
    [switch]$PreloadWan
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$RunDir = Join-Path $Backend "data\run"
$PidFile = Join-Path $RunDir "processes.json"
$Storage = Join-Path $Backend "data"

function Write-Step([string]$Message) {
    Write-Host $Message
}

function Get-ListenerProcessId([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $conn) { return 0 }
    return [int]$conn.OwningProcess
}

function Get-CommandLine([int]$ProcessId) {
    if ($ProcessId -le 0) { return "" }
    $row = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $row) { return "" }
    return [string]$row.CommandLine
}

function Test-ProcessAlive([int]$ProcessId) {
    if ($ProcessId -le 0) { return $false }
    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Stop-ProcessTree([int]$ProcessId) {
    if ($ProcessId -le 0) { return }
    if (-not (Test-ProcessAlive $ProcessId)) { return }
    & taskkill.exe /PID $ProcessId /T /F | Out-Null
}

function Read-PidMap {
    if (-not (Test-Path $PidFile)) { return @{} }
    try {
        $raw = Get-Content -Path $PidFile -Raw -ErrorAction Stop
        $parsed = $raw | ConvertFrom-Json
    } catch {
        return @{}
    }
    $map = @{}
    foreach ($prop in $parsed.PSObject.Properties) {
        $map[$prop.Name] = [int]$prop.Value
    }
    return $map
}

function Write-PidMap($Map) {
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $obj = @{}
    foreach ($key in $Map.Keys) { $obj[$key] = $Map[$key] }
    ($obj | ConvertTo-Json) | Set-Content -Path $PidFile -Encoding UTF8
}

function Set-ProcessEnv([hashtable]$Values) {
    foreach ($key in $Values.Keys) {
        [Environment]::SetEnvironmentVariable($key, [string]$Values[$key], "Process")
    }
}

function Clear-ProcessEnv([string[]]$Names) {
    foreach ($name in $Names) {
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
    }
}

function Start-Logged([string]$Name, [string]$FilePath, [string[]]$ArgumentList, [string]$WorkingDirectory) {
    New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
    $outLog = Join-Path $RunDir "$Name.out.log"
    $errLog = Join-Path $RunDir "$Name.err.log"
    $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Hidden -PassThru
    return [int]$proc.Id
}

function Start-NarattoContainer([string]$Name) {
    $listed = & docker ps -a --filter "name=$Name" --format "{{.Names}}"
    $exact = @($listed | Where-Object { $_ -eq $Name })
    if ($exact.Count -eq 0) {
        throw "Docker container $Name is missing. It must publish Postgres on 5433 or Redis on 6380."
    }
    $running = & docker ps --filter "name=$Name" --format "{{.Names}}"
    if (@($running | Where-Object { $_ -eq $Name }).Count -eq 0) {
        Write-Step "Starting $Name"
        & docker start $Name
        if ($LASTEXITCODE -ne 0) { throw "docker start $Name failed." }
    }
}

function Wait-Port([int]$Port, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ListenerProcessId $Port) -gt 0) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) { return $true }
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    return $false
}

function Stop-Matching([string]$Pattern) {
    $rows = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern }
    foreach ($row in $rows) {
        Stop-ProcessTree ([int]$row.ProcessId)
    }
}

function Stop-NarattoApp {
    Write-Step "Stopping Naratto app processes"
    $map = Read-PidMap
    foreach ($name in @("render", "comfy", "ace", "tasks", "beat", "api", "frontend", "ollama")) {
        if ($map.ContainsKey($name)) { Stop-ProcessTree $map[$name] }
    }
    $py = [regex]::Escape($Python)
    Stop-Matching ($py + ".*uvicorn app\.main:app")
    Stop-Matching ($py + ".*app\.workers\.celery_app")
    Stop-Matching "ComfyUI\\main\.py"
    Stop-Matching "acestep\\api_server\.py"
    $front = [regex]::Escape($Frontend)
    Stop-Matching ($front + ".*vite")
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
    Start-Sleep -Seconds 1
}

function Get-ServiceLine([string]$Label, [int]$Port, [string]$Hint) {
    $procId = Get-ListenerProcessId $Port
    if ($procId -gt 0) {
        Write-Step ("{0,-18} up   port {1} pid {2}  {3}" -f $Label, $Port, $procId, $Hint)
    } else {
        Write-Step ("{0,-18} down port {1}" -f $Label, $Port)
    }
}

function Show-Help {
    Write-Step "naratto start      Start Postgres, Redis, API, workers, Vite, ComfyUI, and ACE-Step"
    Write-Step "naratto all        Same as start"
    Write-Step "naratto stop       Stop the app, workers, ComfyUI, and ACE-Step"
    Write-Step "naratto restart    Stop, then start, so the render worker loads new Wan code"
    Write-Step "naratto status     Show what is listening"
    Write-Step "naratto logs       Show the latest lines from backend\data\run"
    Write-Step "naratto preload    Restart with Wan 2.2 loaded, and do not start ComfyUI or ACE-Step"
    Write-Step "naratto help       Show this list"
}

function Show-Logs {
    if (-not (Test-Path $RunDir)) {
        Write-Step "No logs yet. Run: naratto start"
        return
    }
    $files = @(Get-ChildItem -Path $RunDir -File -ErrorAction SilentlyContinue | Sort-Object Name)
    if ($files.Count -eq 0) {
        Write-Step "No logs yet in $RunDir"
        return
    }
    foreach ($file in $files) {
        Write-Step ""
        Write-Step ("---- {0} ----" -f $file.Name)
        Get-Content -Path $file.FullName -Tail 20 -ErrorAction SilentlyContinue
    }
}

function Show-Status {
    Get-ServiceLine "postgres" 5433 "naratto-postgres"
    Get-ServiceLine "redis" 6380 "naratto-redis"
    Get-ServiceLine "api" 8000 "http://127.0.0.1:8000/docs"
    Get-ServiceLine "frontend" 5173 "http://127.0.0.1:5173"
    Get-ServiceLine "ollama" 11434 "qwen2.5:7b"
    Get-ServiceLine "comfyui" 8188 "scene images"
    Get-ServiceLine "ace-step" 8001 "music"
    $map = Read-PidMap
    foreach ($name in @("tasks", "render", "beat")) {
        $procId = 0
        if ($map.ContainsKey($name)) { $procId = [int]$map[$name] }
        $alive = Test-ProcessAlive $procId
        if ($alive) {
            Write-Step ("{0,-18} up   pid {1}" -f $name, $procId)
        } else {
            Write-Step ("{0,-18} down" -f $name)
        }
    }
    $statePath = Join-Path $Storage "wan_t2v_worker.json"
    $wanLine = "wan2.2             not loaded (the render worker loads it on export)"
    if (Test-Path $statePath) {
        try {
            $wan = Get-Content -Path $statePath -Raw | ConvertFrom-Json
            $wanPid = [int]$wan.pid
            $wanState = [string]$wan.state
            if (($wanState -in @("loading", "loaded")) -and (Test-ProcessAlive $wanPid)) {
                $wanLine = "wan2.2             $wanState pid $wanPid"
            }
        } catch {
            $wanLine = "wan2.2             state file is unreadable"
        }
    }
    Write-Step $wanLine
    Write-Step "logs               $RunDir"
}

function Start-NarattoApp {
    if (-not (Test-Path $Python)) {
        throw "Missing $Python. Create the backend venv first."
    }
    Start-NarattoContainer "naratto-postgres"
    Start-NarattoContainer "naratto-redis"
    if (-not (Wait-Port 5433 30)) { throw "Postgres did not listen on port 5433." }
    if (-not (Wait-Port 6380 30)) { throw "Redis did not listen on port 6380." }

    $gpuBusy = ((Get-ListenerProcessId 8188) -gt 0) -or ((Get-ListenerProcessId 8001) -gt 0)
    if ($PreloadWan -and $gpuBusy) {
        Write-Step "Stopping ComfyUI and ACE-Step so Wan 2.2 can preload"
        Stop-Matching "ComfyUI\\main\.py"
        Stop-Matching "acestep\\api_server\.py"
        Start-Sleep -Seconds 2
    }

    Clear-ProcessEnv @("WAN_T2V_PRELOAD")
    $appEnv = @{
        DATABASE_URL = "postgresql+psycopg://video:video@localhost:5433/video_creator"
        REDIS_URL    = "redis://localhost:6380/0"
        STORAGE_ROOT = $Storage
        PYTHONPATH   = $Backend
    }
    Set-ProcessEnv $appEnv
    $started = @{}

    if ((Get-ListenerProcessId 8000) -eq 0) {
        Write-Step "Starting API on http://127.0.0.1:8000"
        $started["api"] = Start-Logged "api" $Python @(
            "-m", "uvicorn", "app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8000"
        ) $Root
    } else {
        Write-Step "API already listening on 8000"
    }

    $pyPattern = [regex]::Escape($Python) + ".*app\.workers\.celery_app"
    $workers = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $pyPattern })
    $hasTasks = $false
    $hasRender = $false
    $hasBeat = $false
    foreach ($row in $workers) {
        $line = [string]$row.CommandLine
        if ($line -match "story-generation") { $hasTasks = $true; $started["tasks"] = [int]$row.ProcessId }
        elseif ($line -match "-Q render" -or $line -match "-Q render ") { $hasRender = $true; $started["render"] = [int]$row.ProcessId }
        elseif ($line -match "\bbeat\b") { $hasBeat = $true; $started["beat"] = [int]$row.ProcessId }
    }

    if (-not $hasTasks) {
        Write-Step "Starting task worker (story, music, images, TTS)"
        $started["tasks"] = Start-Logged "tasks" $Python @(
            "-m", "celery", "-A", "app.workers.celery_app.celery_app", "worker",
            "-Q", "tts,default,story-generation,music-generation,image-generation",
            "-n", "tasks@localhost", "--pool=solo", "-l", "info"
        ) $Root
    }
    if (-not $hasBeat) {
        Write-Step "Starting Celery beat"
        $started["beat"] = Start-Logged "beat" $Python @(
            "-m", "celery", "-A", "app.workers.celery_app.celery_app", "beat",
            "-s", (Join-Path $RunDir "celerybeat-schedule"), "-l", "info"
        ) $Root
    }

    if ((Get-ListenerProcessId 5173) -eq 0) {
        $npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
        if (-not $npm) { throw "npm.cmd was not found. Install Node and run npm install in frontend." }
        Write-Step "Starting frontend on http://127.0.0.1:5173"
        Clear-ProcessEnv @("PYTHONPATH", "WAN_T2V_PRELOAD")
        $started["frontend"] = Start-Logged "frontend" $npm @("run", "dev", "--", "--host", "127.0.0.1") $Frontend
        Set-ProcessEnv $appEnv
    } else {
        Write-Step "Frontend already listening on 5173"
    }

    if (-not $PreloadWan) {
        Write-Step "ComfyUI stays stopped until Generate images"
        Write-Step "ACE-Step stays stopped until Generate music"
    }

    if (-not $hasRender) {
        Clear-ProcessEnv @("WAN_T2V_PRELOAD")
        Set-ProcessEnv @{ HSA_OVERRIDE_GFX_VERSION = "11.0.0" }
        if ($PreloadWan) {
            Set-ProcessEnv @{ WAN_T2V_PRELOAD = "1" }
            Write-Step "Starting render worker with Wan 2.2 TI2V 5B preloaded"
        } else {
            Write-Step "Starting render worker (Wan 2.2 loads on the next export, then unloads)"
        }
        $started["render"] = Start-Logged "render" $Python @(
            "-m", "celery", "-A", "app.workers.celery_app.celery_app", "worker",
            "-Q", "render", "-n", "render@localhost", "--pool=solo", "-l", "info"
        ) $Root
        Clear-ProcessEnv @("WAN_T2V_PRELOAD", "HSA_OVERRIDE_GFX_VERSION")
    } elseif ($PreloadWan) {
        Write-Step "Render worker is already running. Use restart -PreloadWan to load Wan at startup."
    }

    Write-Step "Ollama stays stopped until a local story. Qwen unloads when the story ends."

    $existing = Read-PidMap
    foreach ($key in $started.Keys) { $existing[$key] = $started[$key] }
    Write-PidMap $existing

    $apiUp = Wait-Http "http://127.0.0.1:8000/health" 40
    if (-not $apiUp) { throw "API did not answer http://127.0.0.1:8000/health. See $RunDir\api.err.log" }
    Write-Step ""
    Write-Step "Naratto is up."
    Write-Step "  App     http://127.0.0.1:5173"
    Write-Step "  API     http://127.0.0.1:8000/docs"
    if ($PreloadWan) {
        Write-Step "  Wan 2.2 preloaded in the render worker only. ComfyUI and ACE-Step were not started."
    } else {
        Write-Step "  Wan 2.2 TI2V 5B stays unloaded until an export. ACE-Step stays stopped until Generate music."
    }
    Write-Step "  Logs    $RunDir"
}

if ($Action -eq "all") { $Action = "start" }
if ($Action -eq "preload") {
    $PreloadWan = $true
    $Action = "restart"
}

switch ($Action) {
    "help" { Show-Help }
    "logs" { Show-Logs }
    "status" { Show-Status }
    "stop" {
        Stop-NarattoApp
        Write-Step "Stopped. Postgres, Redis, and an already-running Ollama were left up."
        Show-Status
    }
    "restart" {
        Stop-NarattoApp
        Start-NarattoApp
    }
    "start" { Start-NarattoApp }
}
