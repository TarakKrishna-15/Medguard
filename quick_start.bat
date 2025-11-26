@echo off
title MediGuard AI Server
echo Starting server...
cd backend
start "MediGuard Server" cmd /k "python -m uvicorn main:APP --host 127.0.0.1 --port 8000 --reload"
timeout /t 3 /nobreak >nul
echo.
echo Server starting... Opening browser in 5 seconds...
timeout /t 5 /nobreak >nul
start http://127.0.0.1:8000/
echo.
echo Server is running! Check the other window.
echo Press any key to exit this window (server will keep running)...
pause >nul

