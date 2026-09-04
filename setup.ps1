# ==============================================================================
# YouTube Automation Pipeline — Automated Windows Setup (PowerShell 5.1 / 7+)
# ==============================================================================
[CmdletBinding()]
param(
    [switch]$SkipPlaywrightBrowser,
    [switch]$SkipDevDependencies
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ScriptDir

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "    YouTube Automation Pipeline - Setup & Environment Init      " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Check Python 3.10+
# ------------------------------------------------------------------------------
Write-Host "[1/6] Checking host Python installation..." -ForegroundColor Yellow

$PyCandidate = $null
if (Get-Command 'python' -ErrorAction SilentlyContinue) {
    $PyCandidate = 'python'
} elseif (Get-Command 'py' -ErrorAction SilentlyContinue) {
    $PyCandidate = 'py'
}

if (-not $PyCandidate) {
    Write-Host "[ERROR] Python was not found in your PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10 or higher from https://www.python.org/ or via:" -ForegroundColor Red
    Write-Host "    winget install Python.Python.3.11" -ForegroundColor White
    exit 1
}

try {
    $PyVerStr = (& $PyCandidate -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')").Trim()
    $PyVersion = [version]$PyVerStr
} catch {
    Write-Host "[ERROR] Failed to query Python version: $_" -ForegroundColor Red
    exit 1
}

Write-Host "  Detected Python: $PyCandidate ($PyVerStr)" -ForegroundColor Gray
if ($PyVersion.Major -lt 3 -or ($PyVersion.Major -eq 3 -and $PyVersion.Minor -lt 10)) {
    Write-Host "[ERROR] Python 3.10+ is required, but found $PyVerStr" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Python version $PyVerStr satisfies requirement (>= 3.10)." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 2. Virtual Environment Setup (.venv or venv)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[2/6] Configuring virtual environment..." -ForegroundColor Yellow

$VenvDir = $null
if (Test-Path -LiteralPath "$ScriptDir\venv\Scripts\python.exe") {
    $VenvDir = "$ScriptDir\venv"
    Write-Host "  Found existing virtual environment: .\venv" -ForegroundColor Gray
} elseif (Test-Path -LiteralPath "$ScriptDir\.venv\Scripts\python.exe") {
    $VenvDir = "$ScriptDir\.venv"
    Write-Host "  Found existing virtual environment: .\.venv" -ForegroundColor Gray
} else {
    Write-Host "  No virtual environment found. Creating .\venv..." -ForegroundColor Gray
    & $PyCandidate -m venv "$ScriptDir\venv"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        exit $LASTEXITCODE
    }
    $VenvDir = "$ScriptDir\venv"
}

$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "[ERROR] Virtual environment Python interpreter not found at $VenvPython" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Active virtual environment: $VenvDir" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 3. Upgrade Packaging Tools & Install Dependencies
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[3/6] Installing & updating Python dependencies..." -ForegroundColor Yellow

Write-Host "  Upgrading pip, setuptools, wheel..." -ForegroundColor Gray
& $VenvPython -m pip install --upgrade pip setuptools wheel --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARNING] Could not update pip/setuptools/wheel (continuing)." -ForegroundColor DarkYellow
}

$ReqFile = Join-Path $ScriptDir 'requirements.txt'
if (Test-Path -LiteralPath $ReqFile) {
    Write-Host "  Installing production dependencies from requirements.txt..." -ForegroundColor Gray
    & $VenvPython -m pip install -r $ReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install requirements.txt." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

$DevReqFile = Join-Path $ScriptDir 'requirements-dev.txt'
if (-not $SkipDevDependencies -and (Test-Path -LiteralPath $DevReqFile)) {
    Write-Host "  Installing development/test dependencies from requirements-dev.txt..." -ForegroundColor Gray
    & $VenvPython -m pip install -r $DevReqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to install requirements-dev.txt." -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "  Installing project in editable mode..." -ForegroundColor Gray
& $VenvPython -m pip install -e $ScriptDir --no-deps --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARNING] Editable project install returned non-zero exit code." -ForegroundColor DarkYellow
}

Write-Host "  [OK] Dependencies installed successfully." -ForegroundColor Green

# ------------------------------------------------------------------------------
# 4. Playwright Browser Provisioning
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[4/6] Provisioning Playwright Chromium..." -ForegroundColor Yellow
if ($SkipPlaywrightBrowser) {
    Write-Host "  Skipping Playwright browser installation (-SkipPlaywrightBrowser flag passed)." -ForegroundColor Gray
} else {
    try {
        & $VenvPython -m playwright install chromium
        Write-Host "  [OK] Playwright Chromium browser verified." -ForegroundColor Green
    } catch {
        Write-Host "  [WARNING] Playwright Chromium install had an issue: $_" -ForegroundColor DarkYellow
    }
}

# ------------------------------------------------------------------------------
# 5. Environment Configuration (.env)
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[5/6] Checking environment secrets and configuration (.env)..." -ForegroundColor Yellow
$EnvFile = Join-Path $ScriptDir '.env'
$EnvExample = Join-Path $ScriptDir '.env.example'

if (-not (Test-Path -LiteralPath $EnvFile)) {
    if (Test-Path -LiteralPath $EnvExample) {
        Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
        Write-Host "  [OK] Initialized .env from .env.example template." -ForegroundColor Green
        Write-Host "  [ACTION REQUIRED] Open .env to configure your TELEGRAM_BOT_TOKEN and browser paths." -ForegroundColor Magenta
    } else {
        Write-Host "  [WARNING] Neither .env nor .env.example exists." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  [OK] Existing .env file detected." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# 6. System Diagnostics & Hardware Probing
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "[6/6] Running system diagnostics..." -ForegroundColor Yellow

# A. FFmpeg & Hardware Encoders
$FfmpegCmd = Get-Command 'ffmpeg' -ErrorAction SilentlyContinue
if ($FfmpegCmd) {
    $FfmpegVer = (& ffmpeg -version 2>&1)[0]
    Write-Host "  [OK] FFmpeg found: $($FfmpegCmd.Source)" -ForegroundColor Green
    Write-Host "       Version: $FfmpegVer" -ForegroundColor Gray
    
    # Probe hardware encoders
    $Encoders = & ffmpeg -hide_banner -encoders 2>&1
    $HwEncoders = @()
    if ($Encoders | Select-String 'h264_qsv') { $HwEncoders += 'Intel QSV (h264_qsv)' }
    if ($Encoders | Select-String 'h264_nvenc') { $HwEncoders += 'NVIDIA NVENC (h264_nvenc)' }
    if ($Encoders | Select-String 'h264_amf') { $HwEncoders += 'AMD AMF (h264_amf)' }
    
    if ($HwEncoders.Count -gt 0) {
        Write-Host "       Hardware acceleration detected: $($HwEncoders -join ', ')" -ForegroundColor Green
    } else {
        Write-Host "       No dedicated GPU h264 hardware encoders detected (will use libx264 software)." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  [WARNING] FFmpeg not found in system PATH." -ForegroundColor DarkYellow
    Write-Host "            Video rendering requires FFmpeg. Install with:" -ForegroundColor DarkYellow
    Write-Host "            winget install Gyan.FFmpeg" -ForegroundColor White
}

# B. Audacity mod-script-pipe
$PipePath = '\\.\pipe\ToSrvPipe'
$PipeActive = Test-Path -LiteralPath $PipePath
if ($PipeActive) {
    Write-Host "  [OK] Audacity mod-script-pipe is active (\\.\pipe\ToSrvPipe detected)." -ForegroundColor Green
} else {
    Write-Host "  [INFO] Audacity pipe not currently open." -ForegroundColor Gray
    Write-Host "         (When running audio mastering, launch Audacity with mod-script-pipe enabled)." -ForegroundColor Gray
}

# C. Chrome CDP Loopback (127.0.0.1:9222)
$CdpActive = $false
try {
    $Tcp = New-Object System.Net.Sockets.TcpClient
    $AsyncResult = $Tcp.BeginConnect('127.0.0.1', 9222, $null, $null)
    if ($AsyncResult.AsyncWaitHandle.WaitOne(800)) {
        $Tcp.EndConnect($AsyncResult)
        $CdpActive = $true
    }
    $Tcp.Close()
} catch {
    $CdpActive = $false
}

if ($CdpActive) {
    Write-Host "  [OK] Chrome CDP loopback is reachable on 127.0.0.1:9222." -ForegroundColor Green
} else {
    Write-Host "  [INFO] Chrome CDP not currently listening on 127.0.0.1:9222." -ForegroundColor Gray
    Write-Host "         (Before running browser stages, start Chrome with --remote-debugging-port=9222)." -ForegroundColor Gray
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "    Setup complete! You can now run the pipeline via:            " -ForegroundColor Cyan
Write-Host "        .\run.bat                                               " -ForegroundColor White
Write-Host "    Or directly in PowerShell:                                   " -ForegroundColor Cyan
Write-Host "        .\venv\Scripts\python.exe run_agency.py                 " -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""
