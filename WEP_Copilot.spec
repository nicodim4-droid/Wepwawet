# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hiddenimports = ['wep', 'wep.__main__']
hiddenimports += collect_submodules('wep')
hiddenimports += collect_submodules('esptool')
datas = collect_data_files(
    'esptool',
    subdir='targets/stub_flasher',
    includes=['**/*.json'],
)
if not datas:
    raise RuntimeError('No esptool stub flasher data files were collected.')
datas.append(
    (
        os.path.join('src', 'wep', 'assets', 'wep_symbol.png'),
        os.path.join('wep', 'assets'),
    )
)
datas.append(
    (
        os.path.join('src', 'wep', 'assets', 'wep.ico'),
        os.path.join('wep', 'assets'),
    )
)


a = Analysis(
    ['run_wep.py'],
    pathex=['src'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WEP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=os.path.join('src', 'wep', 'assets', 'wep.ico'),
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
