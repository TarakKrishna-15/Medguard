@echo off
echo ========================================
echo MediGuard AI - Starting Server
echo ========================================
echo.

echo [1/3] Upgrading pip...
python -m pip install --upgrade pip setuptools wheel
if %errorlevel% neq 0 (
    echo ERROR: Failed to upgrade pip
    pause
    exit /b 1
)

echo.
echo [2/3] Installing dependencies...
python -m pip install --force-reinstall -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [3/3] Testing import...
cd backend
python -c "import main; print('Import successful')"
if %errorlevel% neq 0 (
    echo ERROR: Cannot import main.py - check for errors
    pause
    exit /b 1
)

echo.
echo ========================================
echo Starting server...
echo ========================================
echo Server will be available at: http://127.0.0.1:8000/
echo Press CTRL+C to stop the server
echo.

python -m uvicorn main:APP --host 127.0.0.1 --port 8000 --reload

