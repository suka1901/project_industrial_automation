# Builds the bundle, puts it on the Pi, and asks the Pi whether it agrees.
#
#   .\deploy.ps1 192.168.1.42      # the address is remembered after the first time
#   .\deploy.ps1                   # uses the remembered one
#   .\deploy.ps1 -WithCamera       # also runs the camera and marker checks there
#   .\deploy.ps1 -SkipBuild        # push the bundle already built
#
# Everything is fixed on this PC and shipped; the Pi only runs what arrives.
# The verification matters more than the copying: an unpack that did not
# overwrite leaves the Pi running last week's calibration, and nothing about it
# looks wrong until the robot moves.
#
# Author: Suraj Karki
# Course: INA700 - AI-based pick and place

param(
    [string]$PiAddress,
    [switch]$SkipBuild,
    [switch]$WithCamera,
    [string]$User = "pi",
    [string]$Destination = "~/INA700"
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# --- who to talk to ---------------------------------------------------------
$remembered = Join-Path $PSScriptRoot ".pi-address"
if (-not $PiAddress -and (Test-Path $remembered)) {
    $PiAddress = (Get-Content $remembered -Raw).Trim()
    Write-Host "Pi at $PiAddress (remembered)" -ForegroundColor DarkGray
}
if (-not $PiAddress) {
    Write-Host "No Pi address. Pass it once and it is remembered:" -ForegroundColor Red
    Write-Host "    .\deploy.ps1 192.168.1.42"
    exit 1
}
Set-Content -Path $remembered -Value $PiAddress -NoNewline
$target = "$User@$PiAddress"

# --- build ------------------------------------------------------------------
if (-not $SkipBuild) {
    & "$PSScriptRoot\rebundle.ps1"
    if ($LASTEXITCODE -ne 0) { exit 1 }
}
if (-not (Test-Path "ina700-pi.tar.gz")) {
    Write-Host "No ina700-pi.tar.gz to send." -ForegroundColor Red
    exit 1
}

# --- copy and unpack --------------------------------------------------------
Write-Host ""
Write-Host "Copying to $target ..." -ForegroundColor Cyan
& scp ina700-pi.tar.gz "${target}:~/"
if ($LASTEXITCODE -ne 0) {
    Write-Host "Copy failed. Is the Pi on this network, and SSH enabled?" -ForegroundColor Red
    exit 1
}

Write-Host "Unpacking..." -ForegroundColor Cyan
& ssh $target "mkdir -p $Destination && tar -xzf ~/ina700-pi.tar.gz -C $Destination"
if ($LASTEXITCODE -ne 0) { Write-Host "Unpack failed." -ForegroundColor Red; exit 1 }

# --- did it actually overwrite? ---------------------------------------------
# The config carries every measured value, so it is the file worth checking:
# if this hash differs, the Pi is running a different calibration from the one
# on screen here, which is the failure that looks like a vision fault.
$localHash = (Get-FileHash "pi\config\config.yaml" -Algorithm SHA256).Hash.ToLower()
$remoteHash = (& ssh $target "sha256sum $Destination/pi/config/config.yaml").Split(" ")[0]

if ($localHash -ne $remoteHash) {
    Write-Host ""
    Write-Host "THE PI HAS A DIFFERENT config.yaml." -ForegroundColor Red
    Write-Host "  here $localHash"
    Write-Host "  pi   $remoteHash"
    Write-Host "The unpack did not overwrite. Everything after this inherits it."
    exit 1
}
Write-Host "config.yaml matches - the Pi has this calibration." -ForegroundColor Green

# --- ask the Pi -------------------------------------------------------------
# run.sh already passes --length 100; argparse takes the last value.
$cameraFlag = if ($WithCamera) { "" } else { "--no-camera --length 0" }
Write-Host ""
Write-Host "Pre-flight on the Pi..." -ForegroundColor Cyan
& ssh $target "cd $Destination/pi && ./run.sh preflight $cameraFlag"
$preflight = $LASTEXITCODE

Write-Host ""
if ($preflight -eq 0) {
    Write-Host "  The Pi is ready." -ForegroundColor Green
} else {
    Write-Host "  Pre-flight failed on the Pi - see the rows above." -ForegroundColor Yellow
}
if (-not $WithCamera) {
    Write-Host "  Camera and marker not checked. Re-run with -WithCamera once the"
    Write-Host "  camera is on the Pi." -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "  ssh $target"
Write-Host "  cd $Destination/pi && ./run.sh"
exit $preflight
