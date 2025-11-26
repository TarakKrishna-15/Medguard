# MediGuard AI - Automated Startup Script
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MediGuard AI - Starting Server" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip setuptools wheel --quiet

Write-Host "[2/3] Installing dependencies..." -ForegroundColor Yellow
python -m pip install --force-reinstall -r backend\requirements.txt --quiet

Write-Host "[3/3] Starting server..." -ForegroundColor Yellow
Write-Host ""
Write-Host "Server will be available at: http://127.0.0.1:8000/" -ForegroundColor Green
Write-Host "Press CTRL+C to stop the server" -ForegroundColor Yellow
Write-Host ""

Set-Location backend
python -m uvicorn main:APP --host 127.0.0.1 --port 8000 --reload

