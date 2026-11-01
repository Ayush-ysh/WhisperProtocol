@echo off
setlocal enabledelayedexpansion

echo ==========================================================
echo   WhisperProtocol — Windows Desktop Application Builder
echo ==========================================================
echo.

:: 1. Verify Prerequisites
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Node.js is not installed or not in PATH. Please install Node.js 18+.
    exit /b 1
)

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH. Please install Python 3.11+.
    exit /b 1
)

where cargo >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Rust / Cargo is not installed. Please install from https://rustup.rs
    exit /b 1
)

:: 2. Setup Python Virtual Environment & Sidecar Engine
echo [1/4] Setting up Python virtual environment...
if not exist "backend\venv" (
    python -m venv backend\venv
)

call backend\venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -e backend
pip install pyinstaller cryptography reedsolo

echo.
echo [2/4] Compiling standalone whisper-engine.exe sidecar binary...
cd backend
venv\Scripts\pyinstaller.exe --clean -y whisper.spec
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    exit /b 1
)
cd ..

if not exist "src-tauri\binaries" mkdir "src-tauri\binaries"
copy /Y "backend\dist\whisper-engine.exe" "src-tauri\binaries\whisper-engine-x86_64-pc-windows-msvc.exe"

:: 3. Install Frontend Dependencies
echo.
echo [3/4] Installing frontend dependencies...
call npm install

:: 4. Build Windows Desktop Application (.exe / .msi)
echo.
echo [4/4] Compiling WhisperProtocol Native Windows Application (.exe)...
call npm run tauri build

if %errorlevel% neq 0 (
    echo [ERROR] Tauri build failed.
    exit /b 1
)

echo.
echo ==========================================================
echo   BUILD SUCCESSFUL!
echo ==========================================================
echo   Stand-alone Executable: src-tauri\target\release\WhisperProtocol.exe
echo   Installers (NSIS / MSI): src-tauri\target\release\bundle\
echo ==========================================================
echo.
pause
