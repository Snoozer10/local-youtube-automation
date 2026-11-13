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

# ------------------------------------------------------------------------------
# Helper: Safe native command execution for Windows PowerShell 5.1 & 7+
# In PowerShell 5.1, native stderr output redirected via 2>&1 produces
# ErrorRecord objects that trigger a terminating error when
# $ErrorActionPreference = 'Stop'. Temporarily setting $ErrorActionPreference to
# 'Continue' preserves stderr diagnostics and native exit codes without aborting.
# ------------------------------------------------------------------------------
function Invoke-NativeCommand {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )
    $prevEap = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $lines = @(& $Command 2>&1 | ForEach-Object { "$_" })
        return [PSCustomObject]@{
            Output   = $lines
            ExitCode = $LASTEXITCODE
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

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
$PyLauncherArgs = @()

# On Windows, prefer py -3.11 if available (tested project standard)
if (Get-Command 'py' -ErrorAction SilentlyContinue) {
    try {
        $Py311Check = (& py -3.11 -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null).Trim()
        if ($LASTEXITCODE -eq 0 -and $Py311Check -eq "3.11") {
            $PyCandidate = 'py'
            $PyLauncherArgs = @('-3.11')
        }
    } catch {
        # py -3.11 check failed; fall through to general detection
    }
}

if (-not $PyCandidate) {
    if (Get-Command 'python' -ErrorAction SilentlyContinue) {
        $PyCandidate = 'python'
    } elseif (Get-Command 'py' -ErrorAction SilentlyContinue) {
        $PyCandidate = 'py'
    }
}

if (-not $PyCandidate) {
    Write-Host "[ERROR] Python was not found in your PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.10 or higher from https://www.python.org/ or via:" -ForegroundColor Red
    Write-Host "    winget install Python.Python.3.11" -ForegroundColor White
    exit 1
}

try {
    $PyVerStr = (& $PyCandidate @PyLauncherArgs -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')").Trim()
    $PyVersion = [version]$PyVerStr
} catch {
    Write-Host "[ERROR] Failed to query Python version: $_" -ForegroundColor Red
    exit 1
}

$PyCandidateDisplay = if ($PyLauncherArgs.Count -gt 0) { "$PyCandidate $($PyLauncherArgs -join ' ')" } else { $PyCandidate }
Write-Host "  Detected Python: $PyCandidateDisplay ($PyVerStr)" -ForegroundColor Gray
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
    & $PyCandidate @PyLauncherArgs -m venv "$ScriptDir\venv"
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

# Validate that the venv Python interpreter runs, satisfies >= 3.10, and can execute pip
try {
    $VenvVerStr = (& $VenvPython -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}')").Trim()
    $VenvVersion = [version]$VenvVerStr
} catch {
    Write-Host "[ERROR] Virtual environment interpreter at $VenvPython failed to execute: $_" -ForegroundColor Red
    exit 1
}

if ($VenvVersion.Major -lt 3 -or ($VenvVersion.Major -eq 3 -and $VenvVersion.Minor -lt 10)) {
    Write-Host "[ERROR] Virtual environment interpreter must be Python 3.10+, but found $VenvVerStr at $VenvPython" -ForegroundColor Red
    exit 1
}

$PipProbe = Invoke-NativeCommand { & $VenvPython -m pip --version }
if ($PipProbe.ExitCode -ne 0) {
    Write-Host "[ERROR] Virtual environment pip module is not functional (exit code $($PipProbe.ExitCode)): $($PipProbe.Output -join ' ')" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Active virtual environment: $VenvDir ($VenvVerStr)" -ForegroundColor Green

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
    Write-Host "[ERROR] Editable project install failed with exit code $LASTEXITCODE." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "  Verifying dependency consistency (pip check)..." -ForegroundColor Gray
$PipCheckResult = Invoke-NativeCommand { & $VenvPython -m pip check }
$PipCheckExit = $PipCheckResult.ExitCode
$PipCheckOutput = $PipCheckResult.Output
if ($PipCheckExit -eq 0) {
    Write-Host "  [OK] pip check reported no broken requirements." -ForegroundColor Green
} else {
    Write-Host "[ERROR] pip check reported dependency issues:" -ForegroundColor Red
    $PipCheckOutput | ForEach-Object { Write-Host "       $_" -ForegroundColor Red }
    exit $PipCheckExit
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
    $PwResult = Invoke-NativeCommand { & $VenvPython -m playwright install chromium }
    if ($PwResult.ExitCode -eq 0) {
        Write-Host "  [OK] Playwright Chromium browser verified." -ForegroundColor Green
    } else {
        Write-Host "  [WARNING] Playwright Chromium install exited with code $($PwResult.ExitCode)." -ForegroundColor DarkYellow
        if ($PwResult.Output.Count -gt 0) {
            $PwResult.Output | ForEach-Object { Write-Host "            $_" -ForegroundColor DarkYellow }
        }
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
    Write-Host "  [OK] FFmpeg executable found on PATH: $($FfmpegCmd.Source)" -ForegroundColor Green
    $FfmpegProbe = Invoke-NativeCommand { & ffmpeg -version }
    if ($FfmpegProbe.ExitCode -eq 0) {
        $VerLine = ($FfmpegProbe.Output | Where-Object { $_ -match '\d+\.\d+' } | Select-Object -First 1)
        if (-not $VerLine -and $FfmpegProbe.Output.Count -gt 0) { $VerLine = $FfmpegProbe.Output[0] }
        if (-not $VerLine) { $VerLine = 'Unknown version' }
        Write-Host "       Version check succeeded: $VerLine" -ForegroundColor Gray

        # Probe hardware encoders
        $EncoderProbe = Invoke-NativeCommand { & ffmpeg -hide_banner -encoders }
        $HwEncoders = @()
        if ($EncoderProbe.Output | Select-String 'h264_qsv') { $HwEncoders += 'Intel QSV (h264_qsv)' }
        if ($EncoderProbe.Output | Select-String 'h264_nvenc') { $HwEncoders += 'NVIDIA NVENC (h264_nvenc)' }
        if ($EncoderProbe.Output | Select-String 'h264_amf') { $HwEncoders += 'AMD AMF (h264_amf)' }

        if ($HwEncoders.Count -gt 0) {
            Write-Host "       Hardware acceleration detected: $($HwEncoders -join ', ')" -ForegroundColor Green
        } else {
            Write-Host "       No dedicated GPU h264 hardware encoders detected (will use libx264 software)." -ForegroundColor DarkYellow
        }
    } else {
        Write-Host "  [WARNING] FFmpeg executable was found on PATH but version check failed with exit code $($FfmpegProbe.ExitCode)." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  [WARNING] FFmpeg not found in system PATH." -ForegroundColor DarkYellow
    Write-Host "            Video rendering requires FFmpeg. Install with:" -ForegroundColor DarkYellow
    Write-Host "            winget install Gyan.FFmpeg" -ForegroundColor White
}

$FfprobeCmd = Get-Command 'ffprobe' -ErrorAction SilentlyContinue
if ($FfprobeCmd) {
    Write-Host "  [OK] FFprobe executable found on PATH: $($FfprobeCmd.Source)" -ForegroundColor Green
    $FfprobeProbe = Invoke-NativeCommand { & ffprobe -version }
    if ($FfprobeProbe.ExitCode -eq 0) {
        $VerLine = ($FfprobeProbe.Output | Where-Object { $_ -match '\d+\.\d+' } | Select-Object -First 1)
        if (-not $VerLine -and $FfprobeProbe.Output.Count -gt 0) { $VerLine = $FfprobeProbe.Output[0] }
        if (-not $VerLine) { $VerLine = 'Unknown version' }
        Write-Host "       Version check succeeded: $VerLine" -ForegroundColor Gray
    } else {
        Write-Host "  [WARNING] FFprobe executable was found on PATH but version check failed with exit code $($FfprobeProbe.ExitCode)." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  [WARNING] FFprobe not found in system PATH (required for audio/video media analysis)." -ForegroundColor DarkYellow
}

# B. Audacity mod-script-pipe
$PipePath = '\\.\pipe\ToSrvPipe'
$PipeActive = Test-Path -LiteralPath $PipePath
if ($PipeActive) {
    Write-Host "  [OK] Audacity mod-script-pipe is active (\\.\pipe\ToSrvPipe detected)." -ForegroundColor Green
} else {
    Write-Host "  [INFO] Audacity pipe not currently open." -ForegroundColor Gray
    Write-Host "         (When running optional audio mastering, launch Audacity with mod-script-pipe enabled)." -ForegroundColor Gray
}

# C. Chrome CDP Loopback Port Check (127.0.0.1:9222)
Write-Host "  Checking Chrome CDP loopback port (127.0.0.1:9222)..." -ForegroundColor Gray
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
    Write-Host "  [OK] Chrome CDP loopback port 9222 is active and accepting connections." -ForegroundColor Green
} else {
    Write-Host "  [INFO] Chrome CDP port 9222 is not currently listening." -ForegroundColor Gray
    Write-Host "         (Before running browser automation stages, launch Chrome with a dedicated profile:" -ForegroundColor Gray
    Write-Host "          see CONTRIBUTING.md#configuring-local-debugging-profiles for dedicated-profile startup commands)." -ForegroundColor Gray
}

# D. Tesseract OCR (Adaptive image verification gate)
$TessCmd = Get-Command 'tesseract' -ErrorAction SilentlyContinue
if ($TessCmd) {
    Write-Host "  [OK] Tesseract OCR executable found on PATH: $($TessCmd.Source)" -ForegroundColor Green
    $TessProbe = Invoke-NativeCommand { & tesseract --version }
    if ($TessProbe.ExitCode -eq 0) {
        $VerLine = ($TessProbe.Output | Where-Object { $_ -match '\d+\.\d+' } | Select-Object -First 1)
        if (-not $VerLine -and $TessProbe.Output.Count -gt 0) { $VerLine = $TessProbe.Output[0] }
        if (-not $VerLine) { $VerLine = 'Unknown version' }
        Write-Host "       Version check succeeded: $VerLine" -ForegroundColor Gray
    } else {
        Write-Host "  [WARNING] Tesseract executable was found on PATH but version check failed with exit code $($TessProbe.ExitCode)." -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  [INFO] Tesseract OCR not found in system PATH." -ForegroundColor Gray
    Write-Host "         (Required for full-frame adaptive image validation gates." -ForegroundColor Gray
    Write-Host "          Install with: winget install UB-Mannheim.TesseractOCR)" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "    Setup complete! Available execution paths:                  " -ForegroundColor Cyan
Write-Host "    - Pedagogy scaffold linter (exit status preserved):          " -ForegroundColor Cyan
Write-Host "        & `"$VenvPython`" tools\lint_exercises.py               " -ForegroundColor White
Write-Host "        (or via batch launcher: .\run.bat lint-exercises)       " -ForegroundColor Gray
Write-Host "    - Diagnostic pre-flight drills:                              " -ForegroundColor Cyan
Write-Host "        & `"$VenvPython`" -m pytest exercises/ -v -m drill       " -ForegroundColor White
Write-Host "        (or via batch launcher: .\run.bat test-drills)          " -ForegroundColor Gray
Write-Host "    - Full batch production run (starts run_agency.py batch pipeline):" -ForegroundColor Cyan
Write-Host "        .\run.bat                                               " -ForegroundColor Gray
Write-Host "    - Optional stage features (require separate grants/readiness):" -ForegroundColor Cyan
Write-Host "        * Audacity mastering: launch Audacity (mod-script-pipe)  " -ForegroundColor Gray
Write-Host "        * Browser automation: launch Chrome (--remote-debugging-port=9222;" -ForegroundColor Gray
Write-Host "          see CONTRIBUTING.md#configuring-local-debugging-profiles)" -ForegroundColor Gray
Write-Host "        * Adaptive image gates: install Tesseract OCR            " -ForegroundColor Gray
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""
