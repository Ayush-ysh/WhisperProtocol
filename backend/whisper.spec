# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

block_cipher = None

datas = []
binaries = []
hiddenimports = [
    "scipy.signal",
    "scipy.fft",
    "scipy.special",
    "sounddevice",
    "_sounddevice_data",
    "soundfile",
    "cryptography",
    "cryptography.hazmat.primitives.asymmetric.x25519",
    "cryptography.hazmat.primitives.kdf.hkdf",
    "cryptography.hazmat.primitives.ciphers.aead",
    "reedsolo",
    "sqlite3",
]

for pkg in ["sounddevice", "_sounddevice_data", "soundfile", "reedsolo", "cryptography", "whisper"]:
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas.extend(pkg_datas)
    binaries.extend(pkg_binaries)
    hiddenimports.extend(pkg_hidden)

a = Analysis(
    ['whisper/engine/bridge.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'notebook', 'IPython'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='whisper-engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
