@echo off
echo Checking if server is running...
netstat -ano | findstr :8000
if %errorlevel% == 0 (
    echo Server IS running on port 8000
) else (
    echo Server is NOT running on port 8000
)
echo.
echo Testing Python import...
cd backend
python -c "import main; print('Import successful')"
if %errorlevel% neq 0 (
    echo ERROR: Cannot import main.py
    echo Check for syntax errors in backend/main.py
)
pause

