# PyInstaller spec for the DICOM Anonymiser macOS app bundle
# Build with: pyinstaller dicom_anonymiser.spec

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

app_name = "DICOM Anonymiser"

# Collect Tk-safe assets to bundle inside the app. Source -> target within .app/Contents/Resources
extra_datas = [
    ("assets/icon.png", "assets"),
]

# Hidden imports: grab all pydicom submodules defensively so frozen app can read varied transfer syntaxes.
pydicom_hidden = collect_submodules("pydicom")


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=extra_datas,
    hiddenimports=pydicom_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.icns",  # replace with .icns for better fidelity on macOS
)

app = BUNDLE(
    exe,
    name=f"{app_name}.app",
    icon="assets/icon.icns",  # replace with .icns to avoid auto-conversion
    bundle_identifier="com.example.dicom-anonymiser",
    info_plist=None,
)
