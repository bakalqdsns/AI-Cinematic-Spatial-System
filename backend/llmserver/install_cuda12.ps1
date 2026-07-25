$ErrorActionPreference = "Stop"

$PROXY     = "socks5h://127.0.0.1:7890"
$LLMSERVER = "F:\AICinematicSpatialSystem\backend\llmserver"
$LOGS      = Join-Path $LLMSERVER "logs"
$BACKUP    = Join-Path $LLMSERVER ("_backup_cpu_{0}" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$TMP       = Join-Path $env:TEMP "llama-cuda124"

New-Item -ItemType Directory -Force -Path $LOGS   | Out-Null
New-Item -ItemType Directory -Force -Path $TMP   | Out-Null
New-Item -ItemType Directory -Force -Path $BACKUP | Out-Null

Write-Host "[step 1] stop existing llama-server"
Get-Process -Name "llama-server" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

Write-Host "[step 2] backup old binaries to $BACKUP"
Get-ChildItem -Path $LLMSERVER -Include "*.exe","*.dll" -File | Copy-Item -Destination $BACKUP -Force

$REL = "b10059"
$BASE    = "https://github.com/ggml-org/llama.cpp/releases/download/$REL"
$BIN_URL = "$BASE/llama-$REL-bin-win-cuda-12.4-x64.zip"
$DLL_URL = "$BASE/cudart-llama-bin-win-cuda-12.4-x64.zip"

function Download-With-Curl {
    param([string]$Url, [string]$Out, [string]$Label)
    Write-Host "  [$Label] downloading via proxy $PROXY"
    & curl.exe -L --fail --retry 5 --retry-delay 2 --connect-timeout 30 `
        -x $PROXY `
        -A "Mozilla/5.0" `
        --progress-bar `
        -o $Out $Url
    if ($LASTEXITCODE -ne 0) { throw "curl failed for $Url (exit $LASTEXITCODE)" }
    $size = (Get-Item $Out).Length
    Write-Host "  [$Label] downloaded $size bytes" -ForegroundColor Green
    if ($size -lt 1000000) { throw "$Label file too small ($size bytes), probably truncated" }
}

Write-Host "[step 3] download CUDA 12.4 build"
Download-With-Curl -Url $BIN_URL -Out (Join-Path $TMP "bin.zip") -Label "bin"
Download-With-Curl -Url $DLL_URL -Out (Join-Path $TMP "dll.zip") -Label "dll"

Write-Host "[step 4] extract"
Expand-Archive (Join-Path $TMP "bin.zip") -DestinationPath (Join-Path $TMP "bin") -Force
Expand-Archive (Join-Path $TMP "dll.zip") -DestinationPath (Join-Path $TMP "dll") -Force

Write-Host "[step 5] replace"
Get-ChildItem -Path $LLMSERVER -Filter "*.dll" | Remove-Item -Force
Get-ChildItem -Path (Join-Path $TMP "dll") -Filter "*.dll" | Copy-Item -Destination $LLMSERVER -Force
Copy-Item -Path (Join-Path $TMP "bin\llama-server.exe") -Destination (Join-Path $LLMSERVER "llama-server.exe") -Force
Write-Host "[install] OK (CUDA 12.4)" -ForegroundColor Green

Write-Host "[step 6] start llama-server"
& (Join-Path $LLMSERVER "start-llama-server.bat")
Write-Host "[start] waiting 15s for model load..." -ForegroundColor Cyan
Start-Sleep -Seconds 15

$log = Join-Path $LOGS "llama-server.log"
if (Test-Path $log) {
    Write-Host ""
    Write-Host "=== last 40 lines of llama-server.log ===" -ForegroundColor Cyan
    Get-Content $log -Tail 40
    Write-Host ""
    Write-Host "=== CUDA / GPU signals ===" -ForegroundColor Cyan
    Select-String -Path $log -Pattern "CUDA|ggml_cuda|offloading|n_gpu_layers|GPU device" |
        ForEach-Object { $_.Line }
} else {
    Write-Host "[warn] log not found at $log" -ForegroundColor Red
}
