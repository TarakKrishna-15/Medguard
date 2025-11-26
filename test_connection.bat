@echo off
echo Testing Frontend-Backend Connection...
echo.

echo [1] Checking if server is running...
netstat -ano | findstr :8000 >nul
if %errorlevel% == 0 (
    echo     Server is running on port 8000
) else (
    echo     ERROR: Server is NOT running
    echo     Please run start.bat first
    pause
    exit /b 1
)

echo.
echo [2] Testing backend health endpoint...
curl -s http://127.0.0.1:8000/health
if %errorlevel% == 0 (
    echo     Backend health check: OK
) else (
    echo     ERROR: Cannot reach backend
)

echo.
echo [3] Testing frontend access...
curl -s -o nul -w "HTTP Status: %%{http_code}\n" http://127.0.0.1:8000/
if %errorlevel% == 0 (
    echo     Frontend is accessible
) else (
    echo     ERROR: Cannot access frontend
)

echo.
echo ========================================
echo Connection Test Complete
echo ========================================
echo.
echo Open your browser and go to:
echo   http://127.0.0.1:8000/
echo.
echo The frontend should automatically connect to the backend.
echo.
pause

