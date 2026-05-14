# -*- mode: python ; coding: utf-8 -*-

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path.cwd()
WORKSPACE = ROOT.parent


hiddenimports = [
    'cv2',
    'matplotlib.backends.backend_tkagg',
    'numpy',
    'openpyxl',
    'pandas',
    'PIL',
    'scipy',
    'skimage',
    'tifffile',
    'torch',
    'torchvision',
    'timm',
    'seaborn',
    'yaml',
    'gdown',
    'ultralytics',
    'caiman',
    'igraph',
    'leidenalg',
]
hiddenimports += collect_submodules('ultralytics')
datas = [
    ('xhr.ico', '.'),
    ('README.md', '.'),
    ('DESIGN_NOTES.md', '.'),
    ('PACKAGING.md', '.'),
    ('NeuroAlign_atlas_registration_help.txt', '.'),
    ('NeuroAlign_atlas_registration_summary.json', '.'),
    ('neuroalign_step_worker.py', '.'),
    ('workers', 'workers'),
    ('csbdeep', 'csbdeep'),
    ('DeepCADRT_Model', 'DeepCADRT_Model'),
    (str(WORKSPACE / 'NeuroSeg3' / 'ultralytics'), 'NeuroSeg3/ultralytics'),
    (str(WORKSPACE / 'NeuroSeg3' / 'weights'), 'NeuroSeg3/weights'),
    (str(WORKSPACE / 'NeuroSeg3' / 'dataset_cfg'), 'NeuroSeg3/dataset_cfg'),
    (str(WORKSPACE / 'NeuroSeg3' / 'utils'), 'NeuroSeg3/utils'),
    (str(WORKSPACE / 'DeepCAD-RT' / 'DeepCAD_RT_pytorch' / 'deepcad'), 'DeepCAD-RT/DeepCAD_RT_pytorch/deepcad'),
    (str(WORKSPACE / '2cafe_analysis' / 'NeuroAlign'), 'NeuroAlign'),
]
datas += collect_data_files('hdmf')
datas += collect_data_files('pynwb')

ipyparallel_spec = importlib.util.find_spec('ipyparallel')
if ipyparallel_spec and ipyparallel_spec.origin:
    ipyparallel_root = Path(ipyparallel_spec.origin).parent
    shellcmd_receiver = ipyparallel_root / 'cluster' / 'shellcmd_receive.py'
    if shellcmd_receiver.exists():
        datas.append((str(shellcmd_receiver), 'ipyparallel/cluster'))


a = Analysis(
    ['launch.py'],
    pathex=[str(ROOT), str(WORKSPACE / 'NeuroSeg3'), str(WORKSPACE / 'DeepCAD-RT' / 'DeepCAD_RT_pytorch')],
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

gui_exe = EXE(
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

worker_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NewLight_Worker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon='xhr.ico',
)

coll = COLLECT(
    gui_exe,
    worker_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NewLight_Analysis',
)
