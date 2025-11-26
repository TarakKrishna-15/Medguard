@echo off
cls
echo ========================================
echo   MediGuard AI - Quick Start
echo ========================================
echo.
echo Starting server on http://127.0.0.1:8000
echo.
cd backend
python -m uvicorn main:APP --host 127.0.0.1 --port 8000 --reload

