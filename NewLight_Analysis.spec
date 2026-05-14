# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path.cwd()


a = Analysis(
    ['launch.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ('xhr.ico', '.'),
        ('README.md', '.'),
        ('DESIGN_NOTES.md', '.'),
        ('PACKAGING.md', '.'),
        ('NeuroAlign_atlas_registration_help.txt', '.'),
        ('NeuroAlign_atlas_registration_summary.json', '.'),
        ('neuroalign_step_worker.py', '.'),
        ('workers', 'workers'),
        ('DeepCADRT_Model', 'DeepCADRT_Model'),
    ],
    hiddenimports=[
        'cv2',
        'matplotlib.backends.backend_tkagg',
        'numpy',
        'openpyxl',
        'pandas',
        'PIL',
        'scipy',
        'skimage',
        'tifffile',
    ],
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
    [],
    exclude_binaries=True,
    name='NewLight_Analysis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='xhr.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NewLight_Analysis',
)
