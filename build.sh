#!/usr/bin/env bash
set -e

# WhisperProtocol — Unix Desktop Application Packager (macOS / Linux)
# Generates .dmg (macOS) or .AppImage (Linux)

echo "================================================================"
echo "  WhisperProtocol — Desktop Application Packager (macOS / Linux)"
echo "================================================================"

# Verify prerequisites
command -v node >/dev/null 2>&1 || { echo "[ERROR] Node.js is required. Please install Node.js 18+."; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "[ERROR] Python 3 is required. Please install Python 3.11+."; exit 1; }
command -v cargo >/dev/null 2>&1 || { echo "[ERROR] Rust / Cargo is required. Please install from https://rustup.rs."; exit 1; }

node scripts/build.mjs
