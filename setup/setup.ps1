<#
NextraAxisVM setup: everything the AI tools need on this computer, no terminal knowledge required.
Run it by double-clicking Setup.bat. The AI plugin can also start it in the background on first use (-Quiet).

  1. uv (Astral's Python manager), installed per user if missing
  2. Python 3.10 + PyAxisVM in %LOCALAPPDATA%\NextraAxisVM\venv (pinned versions, requirements.lock.txt)
  3. comtypes wrapper for the installed AxisVM type library (so the first AI call is fast)
  4. the NextraAxisVM add-on (NextraAxisVM.dll) into every AxisVM AddOns folder found
  5. checks: Node.js (runs the plugin bridge), AxisVM COM registration

Re-running is safe: finished steps are skipped or refreshed. Progress: %LOCALAPPDATA%\NextraAxisVM\setup-status.json
#>
param(
    [switch]$Quiet,          # no prompts, no pause (background run from the plugin)
    [switch]$SkipAddon,      # do not copy the add-on
    [string]$AxisVMDir = ""  # copy the add-on only into this AxisVM folder
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$env:UV_LINK_MODE = "copy"   # hardlinks fail on cloud-synced folders (OneDrive) and across drives

$Root      = Split-Path -Parent $MyInvocation.MyCommand.Path          # ...\setup
$Base      = Join-Path $env:LOCALAPPDATA "NextraAxisVM"
$Venv      = Join-Path $Base "venv"
$Py        = Join-Path $Venv "Scripts\python.exe"
$StatusF   = Join-Path $Base "setup-status.json"
$LogF      = Join-Path $Base "setup.log"
New-Item -ItemType Directory -Force -Path $Base | Out-Null

function Status($state, $step, $msg) {
    $o = [ordered]@{ state = $state; step = $step; message = $msg; time = (Get-Date).ToString("s"); python = $Py }
    [IO.File]::WriteAllText($StatusF, ($o | ConvertTo-Json -Compress))   # UTF-8 without BOM
}
# Runs a native program, appends its output to the log, returns its exit code. Windows PowerShell 5.1 would turn
# any stderr line into a terminating error under $ErrorActionPreference = "Stop", hence the local "Continue".
function Native([string]$exe, [string[]]$argv) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $exe @argv 2>&1 | ForEach-Object { "$_" } | Add-Content -Path $LogF; return $LASTEXITCODE }
    finally { $ErrorActionPreference = $old }
}
function Say($msg, $color = "Gray") {
    Add-Content -Path $LogF -Value ("{0}  {1}" -f (Get-Date).ToString("s"), $msg)
    if (-not $Quiet) { Write-Host $msg -ForegroundColor $color }
}
function Step($n, $msg) { Say ""; Say "[$n/5] $msg" "Cyan"; Status "running" $n $msg }
function Fail($n, $msg) {
    Say "FAILED: $msg" "Red"; Status "failed" $n $msg
    if (-not $Quiet) { Write-Host ""; Write-Host "Setup stopped. Log: $LogF" -ForegroundColor Yellow }
    exit 1
}

Say "NextraAxisVM setup  ($((Get-Date).ToString('s')))" "Green"

# ---------------------------------------------------------------- 1. uv
Step 1 "Python manager (uv)"
function Find-Uv {
    $c = Get-Command uv -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($p in @("$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe", "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}
$Uv = Find-Uv
if (-not $Uv) {
    Say "  installing uv (per user, from astral.sh) ..."
    try {
        $env:UV_NO_MODIFY_PATH = "1"
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression *>&1 | ForEach-Object { "$_" } | Add-Content -Path $LogF
    } catch { Fail 1 "could not install uv: $($_.Exception.Message). Check the internet connection, or install uv from https://docs.astral.sh/uv/ and run Setup again." }
    $Uv = Find-Uv
    if (-not $Uv) { Fail 1 "uv was installed but not found. Run Setup again." }
}
Say "  uv: $Uv"

# ---------------------------------------------------------------- 2. Python + PyAxisVM
Step 2 "Python 3.10 + PyAxisVM (first time: a few minutes, ~400 MB)"
$Lock = Join-Path $Root "requirements.lock.txt"
$Stamp = Join-Path $Base "venv.lock.sha"
$want = (Get-FileHash $Lock -Algorithm SHA256).Hash
$have = if ((Test-Path $Stamp) -and (Test-Path $Py)) { (Get-Content $Stamp -Raw).Trim() } else { "" }
if ($have -eq $want) {
    Say "  already installed: $Venv"
} else {
    if (-not (Test-Path $Py)) {
        if ((Native $Uv @("venv", "--python", "3.10", $Venv)) -ne 0) { Fail 2 "could not create the Python 3.10 environment (see $LogF)" }
    }
    if ((Native $Uv @("pip", "install", "--python", $Py, "-r", $Lock)) -ne 0) { Fail 2 "package installation failed (see $LogF)" }
    Set-Content -Path $Stamp -Value $want
    Say "  installed into $Venv"
}

# ---------------------------------------------------------------- 3. AxisVM type library wrapper
Step 3 "AxisVM COM type library"
if ((Native $Py @("-c", "import axisvm.com.tlb")) -ne 0) {
    Say "  WARNING: the AxisVM type library could not be loaded (see $LogF)" "Yellow"
    Say "  Install AxisVM (or run its !REGISTER_AXISVM_X64.BAT as administrator), then run Setup again." "Yellow"
    $tlbOk = $false
} else { Say "  ok"; $tlbOk = $true }

# ---------------------------------------------------------------- 4. add-on
Step 4 "NextraAxisVM add-on for AxisVM"
$dll = @((Join-Path $Root "..\addon\bin\NextraAxisVM.dll"), (Join-Path $Root "..\addon\NextraAxisVM.dll")) | Where-Object { Test-Path $_ } | Select-Object -First 1
$targets = @()
if ($AxisVMDir) { $targets += $AxisVMDir }
else {
    # registered COM server = the AxisVM the tools will talk to; plus any C:\AxisVM* folder
    try {
        $clsid = (Get-ItemProperty 'Registry::HKEY_CLASSES_ROOT\AxisVM.AxisVMApplication\CLSID' -ErrorAction Stop).'(default)'
        $exe = (Get-ItemProperty "Registry::HKEY_CLASSES_ROOT\CLSID\$clsid\LocalServer32" -ErrorAction Stop).'(default)'
        $exe = $exe.Trim('"').Split('"')[0] -replace '\s+/.*$', ''
        if (Test-Path $exe) { $targets += (Get-Item (Split-Path -Parent $exe)).FullName }
    } catch { }
    Get-ChildItem -Path "C:\" -Directory -Filter "AxisVM*" -ErrorAction SilentlyContinue | ForEach-Object {
        if (Test-Path (Join-Path $_.FullName "AxisVMDotNetAddonPluginInterface_v1.0.FW4.dll")) { $targets += $_.FullName }
    }
}
$targets = $targets | Sort-Object -Unique
$addonOk = $true; $needRestart = $false
if ($SkipAddon) { Say "  skipped (-SkipAddon)" }
elseif (-not $dll) { Say "  WARNING: NextraAxisVM.dll not found next to this setup" "Yellow"; $addonOk = $false }
elseif ($targets.Count -eq 0) { Say "  WARNING: no AxisVM installation found. Install AxisVM, then run Setup again." "Yellow"; $addonOk = $false }
else {
    foreach ($t in $targets) {
        $addons = Join-Path $t "AddOns"
        $dst = Join-Path $addons "NextraAxisVM.dll"
        if ((Test-Path $dst) -and ((Get-FileHash $dst).Hash -eq (Get-FileHash $dll).Hash)) { Say "  up to date: $dst"; continue }
        try {
            New-Item -ItemType Directory -Force -Path $addons | Out-Null
            Copy-Item $dll $dst -Force
            Say "  installed: $dst" "Green"; $needRestart = $true
        } catch [System.UnauthorizedAccessException] {
            if ($Quiet) { Say "  WARNING: no write access to $addons. Run Setup.bat once (it asks for administrator rights)." "Yellow"; $addonOk = $false; continue }
            Say "  asking for administrator rights to write $addons ..."
            $p = Start-Process powershell -Verb RunAs -Wait -PassThru -ArgumentList "-NoProfile -Command Copy-Item -LiteralPath '$dll' -Destination '$dst' -Force"
            if ($p.ExitCode -eq 0 -and (Test-Path $dst)) { Say "  installed: $dst" "Green"; $needRestart = $true } else { Say "  WARNING: copy failed" "Yellow"; $addonOk = $false }
        } catch {
            # a running AxisVM locks the old DLL during updates
            Say "  WARNING: $dst is in use. Close AxisVM and run Setup again to update the add-on." "Yellow"; $addonOk = $false
        }
    }
}

# ---------------------------------------------------------------- 5. checks
Step 5 "Checks"
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) { Say "  Node.js: $(& node --version)" }
else {
    Say "  Node.js not found. The AI apps start the NextraAxisVM bridge with Node.js 18+." "Yellow"
    if (-not $Quiet) {
        $w = Get-Command winget -ErrorAction SilentlyContinue
        if ($w) {
            $ans = Read-Host "  Install Node.js LTS now with winget? [Y/n]"
            if ($ans -eq "" -or $ans -match '^[yY]') { & winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements }
        } else { Say "  Install it from https://nodejs.org (LTS), then restart your AI app." "Yellow" }
    }
}
$cfgDir = Join-Path $env:APPDATA "NextraAxisVM"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null

$summary = "Python environment ready."
if (-not $tlbOk) { $summary += " AxisVM type library missing (install/register AxisVM)." }
if ($needRestart) { $summary += " Add-on installed: restart AxisVM once." }
elseif ($addonOk -and -not $SkipAddon) { $summary += " Add-on up to date." }
else { $summary += " Add-on not installed (see log)." }
Status "ok" 5 $summary
Say ""
Say "Done. $summary" "Green"
if (-not $Quiet) {
    Write-Host ""
    Write-Host "Next: install the NextraAxisVM plugin in your AI app (see README), open AxisVM, and ask away." -ForegroundColor Green
}
exit 0
