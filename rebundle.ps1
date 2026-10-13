# Builds ina700-pi.tar.gz for the Raspberry Pi.
#
# Runs the tests FIRST and refuses to build if any fail. A bundle built from a
# failing tree looks identical to a good one, and you find out at the station.
#
#   .\rebundle.ps1
#
# Author: Suraj Karki
# Course: INA700 - AI-based pick and place

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "Running the tests..." -ForegroundColor Cyan
Push-Location pi
& python -m pytest -q
$testsFailed = $LASTEXITCODE
Pop-Location

if ($testsFailed -ne 0) {
    Write-Host ""
    Write-Host "TESTS FAILED - not building. Fix them first." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Building ina700-pi.tar.gz..." -ForegroundColor Cyan

tar -czf ina700-pi.tar.gz `
    --exclude=__pycache__ --exclude=.pytest_cache `
    --exclude=*.pyc --exclude=*.log `
    pi `
    model/best_ncnn_model `
    model/dataset/yolo/val/images `
    model/dataset/yolo/val/labels `
    model/dataset/yolo/data.yaml `
    LAB.md

if ($LASTEXITCODE -ne 0) { Write-Host "tar failed." -ForegroundColor Red; exit 1 }

$size = [math]::Round((Get-Item ina700-pi.tar.gz).Length / 1MB, 1)
$junk = (tar -tzf ina700-pi.tar.gz | Select-String -Pattern '__pycache__|pytest_cache|\.pyc$|\.log$').Count

Write-Host ""
Write-Host "  ina700-pi.tar.gz   $size MB   junk files: $junk" -ForegroundColor Green
Write-Host ""
Write-Host "  scp ina700-pi.tar.gz pi@<pi-address>:~/"
Write-Host "  ssh pi@<pi-address> `"tar -xzf ~/ina700-pi.tar.gz -C ~/INA700`""
