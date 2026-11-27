# ==============================================================================
# SSTRIX MARINE-AI / SIH25041 — Platform Safe Startup & Verification Script
# ==============================================================================
# Safely starts infrastructure containers (PostgreSQL + PostGIS & SeaweedFS S3)
# and launches the FastAPI backend without altering or deleting existing data.
# ==============================================================================

param(
    [switch]$SkipContainers = $false,
    [switch]$NoReload = $false,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\SSTRIX_MARINE_PLATFORM"
$BackendRoot = Join-Path $ProjectRoot "backend"
$PythonExe = Join-Path $BackendRoot ".venv\Scripts\python.exe"
$UvicornExe = Join-Path $BackendRoot ".venv\Scripts\uvicorn.exe"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  SSTRIX MARINE-AI / SIH25041 — PLATFORM INITIALIZATION" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Verify Docker Daemon
Write-Host "`n[1/4] Checking Docker daemon status..." -ForegroundColor Yellow
$DockerRunning = $false
try {
    $null = docker version --format '{{.Server.Version}}' 2>$null
    $DockerRunning = $true
    Write-Host "  [+] Docker Engine is active and responding." -ForegroundColor Green
} catch {
    Write-Host "  [!] Docker daemon is not responding directly via CLI." -ForegroundColor Yellow
    Write-Host "      Checking whether local service ports (5432, 8333) are already active..." -ForegroundColor Yellow
}

# 2. Check / Start Infrastructure Containers
if (-not $SkipContainers) {
    Write-Host "`n[2/4] Verifying database and storage infrastructure..." -ForegroundColor Yellow
    $PgListening = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
    $S3Listening = Get-NetTCPConnection -LocalPort 8333 -State Listen -ErrorAction SilentlyContinue

    if ($PgListening -and $S3Listening) {
        Write-Host "  [+] PostgreSQL (5432) and SeaweedFS (8333) are already running and listening." -ForegroundColor Green
    } elseif ($DockerRunning) {
        Write-Host "  [*] Launching containers via docker compose (preserving existing data)..." -ForegroundColor Yellow
        Set-Location $ProjectRoot
        docker compose up -d
        Start-Sleep -Seconds 3
        Write-Host "  [+] Infrastructure containers started." -ForegroundColor Green
    } else {
        Write-Host "  [!] Containers are not running and Docker daemon is unavailable." -ForegroundColor Red
        Write-Host "      Please ensure Docker Desktop is open or start containers." -ForegroundColor Red
    }
} else {
    Write-Host "`n[2/4] Skipping container startup (--SkipContainers specified)." -ForegroundColor Gray
}

# 3. Verify Database and SeaweedFS Storage
Write-Host "`n[3/4] Verifying database connectivity and buckets..." -ForegroundColor Yellow
$env:PYTHONPATH = $BackendRoot
try {
    & $PythonExe -c "
from app.database.connection import engine
from sqlalchemy import text
from app.storage.s3_client import test_storage_connection

with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
print('  [+] PostgreSQL connection: OK')

buckets = test_storage_connection()
print(f'  [+] SeaweedFS S3 buckets verified: {len(buckets)} buckets ({buckets[:3]}...)')
"
} catch {
    Write-Host "  [!] Service check returned a warning: $_" -ForegroundColor Yellow
}

# 4. Launch FastAPI Uvicorn Server
Write-Host "`n[4/4] Starting FastAPI backend on http://127.0.0.1:$Port..." -ForegroundColor Yellow
Write-Host "  Swagger UI: http://localhost:$Port/docs" -ForegroundColor Cyan
Write-Host "  ReDoc UI:   http://localhost:$Port/redoc" -ForegroundColor Cyan
Write-Host "  OpenAPI:    http://localhost:$Port/openapi.json" -ForegroundColor Cyan
Write-Host "`nPress CTRL+C to terminate.`n" -ForegroundColor Gray

Set-Location $BackendRoot
if ($NoReload) {
    & $UvicornExe app.main:app --host 127.0.0.1 --port $Port
} else {
    & $UvicornExe app.main:app --host 127.0.0.1 --port $Port --reload
}
