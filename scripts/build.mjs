#!/usr/bin/env node

import { execSync, spawnSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');
const BACKEND_DIR = path.join(ROOT_DIR, 'backend');
const TAURI_DIR = path.join(ROOT_DIR, 'src-tauri');
const BINARIES_DIR = path.join(TAURI_DIR, 'binaries');
const INSTALLERS_DIR = path.join(ROOT_DIR, 'installers');

console.log('================================================================');
console.log('  WhisperProtocol — Universal Desktop Application Packager');
console.log('================================================================\n');

// 1. Determine Host Platform & Target Triple
const platform = process.platform;
const arch = process.arch;

let targetTriple = '';
let executableExt = '';
let installerExpected = '';

if (platform === 'darwin') {
  targetTriple = arch === 'arm64' ? 'aarch64-apple-darwin' : 'x86_64-apple-darwin';
  installerExpected = 'DMG (.dmg)';
} else if (platform === 'win32') {
  targetTriple = 'x86_64-pc-windows-msvc';
  executableExt = '.exe';
  installerExpected = 'Windows Installer (.exe / .msi)';
} else if (platform === 'linux') {
  targetTriple = arch === 'arm64' ? 'aarch64-unknown-linux-gnu' : 'x86_64-unknown-linux-gnu';
  installerExpected = 'Linux AppImage (.AppImage) / Debian (.deb)';
} else {
  console.error(`[ERROR] Unsupported OS: ${platform}`);
  process.exit(1);
}

console.log(`[INFO] Detected Platform: ${platform} (${arch})`);
console.log(`[INFO] Target Triple:     ${targetTriple}`);
console.log(`[INFO] Target Installer:  ${installerExpected}\n`);

// 2. Ensure Python Virtual Environment and Sidecar Binary
const sidecarBinaryName = `whisper-engine-${targetTriple}${executableExt}`;
const sidecarTargetPath = path.join(BINARIES_DIR, sidecarBinaryName);

if (!fs.existsSync(BINARIES_DIR)) {
  fs.mkdirSync(BINARIES_DIR, { recursive: true });
}

function findPythonInterpreter() {
  const venvDir = path.join(BACKEND_DIR, 'venv');
  const candidates = [
    path.join(venvDir, 'bin', 'python3'),
    path.join(venvDir, 'bin', 'python'),
    path.join(venvDir, 'Scripts', 'python.exe'),
    path.join(venvDir, 'python.exe'),
  ];
  for (const cand of candidates) {
    if (fs.existsSync(cand)) return cand;
  }
  return null;
}

function findPyInstaller() {
  const venvDir = path.join(BACKEND_DIR, 'venv');
  const candidates = [
    path.join(venvDir, 'bin', 'pyinstaller'),
    path.join(venvDir, 'Scripts', 'pyinstaller.exe'),
  ];
  for (const cand of candidates) {
    if (fs.existsSync(cand)) return cand;
  }
  return null;
}

let sidecarReady = false;
if (fs.existsSync(sidecarTargetPath)) {
  const stat = fs.statSync(sidecarTargetPath);
  if (stat.size > 1000000) {
    console.log(`[1/4] Sidecar binary verified: ${sidecarBinaryName} (${(stat.size / 1024 / 1024).toFixed(1)} MB)`);
    sidecarReady = true;
  }
}

if (!sidecarReady) {
  console.log('[1/4] Compiling standalone whisper-engine sidecar binary via PyInstaller...');
  
  let pythonBin = findPythonInterpreter();
  let pyinstallerBin = findPyInstaller();

  if (!pythonBin || !pyinstallerBin) {
    console.log('[INFO] Python venv or PyInstaller not detected. Initializing virtualenv...');
    const sysPython = platform === 'win32' ? 'python' : 'python3';
    try {
      execSync(`${sysPython} -m venv "${path.join(BACKEND_DIR, 'venv')}"`, { stdio: 'inherit' });
      pythonBin = findPythonInterpreter();
    } catch (e) {
      console.error('[ERROR] Failed to create Python virtual environment:', e.message);
      process.exit(1);
    }

    console.log('[INFO] Installing backend dependencies...');
    const pipCmd = platform === 'win32'
      ? `"${path.join(BACKEND_DIR, 'venv', 'Scripts', 'pip.exe')}"`
      : `"${path.join(BACKEND_DIR, 'venv', 'bin', 'pip')}"`;

    execSync(`${pipCmd} install --upgrade pip`, { stdio: 'inherit' });
    execSync(`${pipCmd} install -e "${BACKEND_DIR}"`, { stdio: 'inherit' });
    execSync(`${pipCmd} install pyinstaller cryptography reedsolo`, { stdio: 'inherit' });
    pyinstallerBin = findPyInstaller();
  }

  console.log('[INFO] Executing PyInstaller build...');
  execSync(`"${pyinstallerBin}" --clean -y whisper.spec`, {
    cwd: BACKEND_DIR,
    stdio: 'inherit',
  });

  const distBuiltEngine = path.join(BACKEND_DIR, 'dist', `whisper-engine${executableExt}`);
  if (!fs.existsSync(distBuiltEngine)) {
    console.error(`[ERROR] PyInstaller failed to produce ${distBuiltEngine}`);
    process.exit(1);
  }

  fs.copyFileSync(distBuiltEngine, sidecarTargetPath);
  if (platform !== 'win32') {
    fs.chmodSync(sidecarTargetPath, 0o755);
  }
  if (platform === 'darwin') {
    const entPath = path.join(TAURI_DIR, 'Entitlements.plist');
    try {
      console.log(`[INFO] Code-signing sidecar binary with entitlements: ${sidecarTargetPath}`);
      execSync(`codesign --force --options runtime --sign - --entitlements "${entPath}" "${sidecarTargetPath}"`, { stdio: 'inherit' });
    } catch (e) {
      console.warn('[WARN] Codesigning sidecar failed:', e.message);
    }
  }
  console.log(`[INFO] Staged sidecar binary to: ${sidecarTargetPath}`);
}

// 3. Compile Frontend Bundle
console.log('\n[2/4] Compiling frontend bundle (tsc && vite build)...');
execSync('npm run build', { cwd: ROOT_DIR, stdio: 'inherit' });

// 4. Compile Desktop Application with Tauri
console.log('\n[3/4] Building Tauri desktop application & native installers...');
const tauriArgs = ['tauri', 'build'];
const tauriRes = spawnSync('npx', tauriArgs, { cwd: ROOT_DIR, stdio: 'inherit' });

if (tauriRes.status !== 0) {
  console.error('\n[ERROR] Tauri build failed.');
  process.exit(tauriRes.status || 1);
}

// 5. Discover Generated Installers and Move to /installers/
console.log('\n[4/4] Locating generated installation packages...');
if (!fs.existsSync(INSTALLERS_DIR)) {
  fs.mkdirSync(INSTALLERS_DIR, { recursive: true });
}

const bundleDir = path.join(TAURI_DIR, 'target', 'release', 'bundle');
const collectedInstallers = [];

function searchFiles(dir, extensions) {
  if (!fs.existsSync(dir)) return [];
  const results = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...searchFiles(fullPath, extensions));
    } else if (extensions.some((ext) => entry.name.toLowerCase().endsWith(ext.toLowerCase()))) {
      results.push(fullPath);
    }
  }
  return results;
}

// Search for installers based on platform
if (platform === 'darwin') {
  const appPath = path.join(bundleDir, 'macos', 'WhisperProtocol.app');
  const entPath = path.join(TAURI_DIR, 'Entitlements.plist');

  if (fs.existsSync(appPath)) {
    console.log('\n[INFO] Deep-signing macOS application bundle with audio entitlements...');
    try {
      const engineInBundle = path.join(appPath, 'Contents', 'MacOS', 'whisper-engine');
      if (fs.existsSync(engineInBundle)) {
        console.log(`[INFO] Signing inner whisper-engine with entitlements: ${engineInBundle}`);
        execSync(`codesign --force --options runtime --sign - --entitlements "${entPath}" "${engineInBundle}"`, { stdio: 'inherit' });
      }
      const appBinInBundle = path.join(appPath, 'Contents', 'MacOS', 'app');
      if (fs.existsSync(appBinInBundle)) {
        console.log(`[INFO] Signing inner app binary with entitlements: ${appBinInBundle}`);
        execSync(`codesign --force --options runtime --sign - --entitlements "${entPath}" "${appBinInBundle}"`, { stdio: 'inherit' });
      }
      execSync(`codesign --force --options runtime --deep --sign - --entitlements "${entPath}" "${appPath}"`, { stdio: 'inherit' });
      execSync(`codesign --verify --deep --strict --verbose=2 "${appPath}"`, { stdio: 'inherit' });
      console.log('[SUCCESS] macOS application bundle successfully signed & verified on disk.');
    } catch (e) {
      console.warn('[WARN] Codesigning app bundle failed:', e.message);
    }
  }

  const dmgs = searchFiles(path.join(bundleDir, 'dmg'), ['.dmg']);
  for (const src of dmgs) {
    const dest = path.join(INSTALLERS_DIR, path.basename(src));
    if (fs.existsSync(appPath)) {
      try {
        console.log(`[INFO] Packaging verified signed bundle into DMG: ${dest}`);
        fs.rmSync(dest, { force: true });
        const appDir = path.dirname(appPath);
        const appSymlink = path.join(appDir, 'Applications');
        if (!fs.existsSync(appSymlink)) {
          try { fs.symlinkSync('/Applications', appSymlink); } catch (_) {}
        }
        execSync(`hdiutil create -volname "WhisperProtocol" -srcfolder "${appDir}" -ov -format UDZO "${dest}"`, { stdio: 'inherit' });
        execSync(`codesign --force --sign - "${dest}"`, { stdio: 'inherit' });
      } catch (e) {
        console.warn('[WARN] Rebuilding DMG with hdiutil failed, copying original:', e.message);
        fs.copyFileSync(src, dest);
      }
    } else {
      fs.copyFileSync(src, dest);
    }
    collectedInstallers.push({ type: 'macOS DMG Installer', path: dest, file: path.basename(dest) });
  }
} else if (platform === 'win32') {
  const exes = searchFiles(path.join(bundleDir, 'nsis'), ['.exe']);
  const msis = searchFiles(path.join(bundleDir, 'msi'), ['.msi']);
  for (const src of [...exes, ...msis]) {
    const dest = path.join(INSTALLERS_DIR, path.basename(src));
    fs.copyFileSync(src, dest);
    collectedInstallers.push({
      type: src.endsWith('.exe') ? 'Windows NSIS Installer' : 'Windows MSI Package',
      path: dest,
      file: path.basename(dest),
    });
  }
} else if (platform === 'linux') {
  const appImages = searchFiles(path.join(bundleDir, 'appimage'), ['.appimage']);
  const debs = searchFiles(path.join(bundleDir, 'deb'), ['.deb']);
  for (const src of [...appImages, ...debs]) {
    const dest = path.join(INSTALLERS_DIR, path.basename(src));
    fs.copyFileSync(src, dest);
    if (src.toLowerCase().endsWith('.appimage')) {
      fs.chmodSync(dest, 0o755);
    }
    collectedInstallers.push({
      type: src.toLowerCase().endsWith('.appimage') ? 'Linux AppImage' : 'Debian Package',
      path: dest,
      file: path.basename(dest),
    });
  }
}

// Print Prominent Completion Banner
console.log('\n================================================================');
console.log('  WHISPERPROTOCOL DESKTOP INSTALLER READY');
console.log('================================================================');

if (collectedInstallers.length === 0) {
  console.log(`[NOTICE] Build succeeded. Bundles located in:`);
  console.log(`  ${bundleDir}`);
} else {
  for (const item of collectedInstallers) {
    const stat = fs.statSync(item.path);
    const sizeMb = (stat.size / 1024 / 1024).toFixed(2);
    console.log(`\n  Package Type: ${item.type}`);
    console.log(`  Installer:    ${item.file} (${sizeMb} MB)`);
    console.log(`  File Path:    ${item.path}`);
  }

  console.log('\n  INSTALLATION INSTRUCTIONS:');
  if (platform === 'darwin') {
    console.log('  - Double-click the .dmg file in Finder.');
    console.log('  - Drag "WhisperProtocol" into your Applications folder.');
    console.log('  - Launch WhisperProtocol from Applications.');
    console.log('  - If macOS Gatekeeper prompts on another Mac device:');
    console.log('    • Right-click WhisperProtocol.app in Applications and click "Open"');
    console.log('    • Or run in Terminal: xattr -cr /Applications/WhisperProtocol.app');
    console.log('  - When prompted for Microphone access, click "OK" to allow physical acoustic data transmission.');
  } else if (platform === 'win32') {
    console.log('  - Double-click the .exe installer.');
    console.log('  - Follow the setup wizard to install WhisperProtocol.');
  } else if (platform === 'linux') {
    console.log('  - For AppImage: Make executable and run:');
    console.log('    chmod +x installers/*.AppImage && ./installers/*.AppImage');
    console.log('  - For Debian: sudo dpkg -i installers/*.deb');
  }
}

console.log('================================================================\n');
