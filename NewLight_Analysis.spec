# -*- mode: python ; coding: utf-8 -*-

import importlib.util
import runpy
import sys
from pathlib import Path

from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path.cwd()
WORKSPACE = ROOT.parent
PYINSTALLER_DIR = Path(importlib.util.find_spec('PyInstaller').origin).parent
WORKER_ICON = PYINSTALLER_DIR / 'bootloader' / 'images' / 'icon-console.ico'
CV2_PATCH_TOOL = ROOT / 'tools' / 'patch_frozen_cv2.py'
CUDA_RUNTIME_DLL_PATTERNS = [
    'c10_cuda.dll',
    'torch_cuda.dll',
    'caffe2_nvrtc.dll',
    'cublas*.dll',
    'cudart*.dll',
    'cudnn*.dll',
    'cufft*.dll',
    'cufftw*.dll',
    'cusolver*.dll',
    'cusolverMg*.dll',
    'cusparse*.dll',
    'nvrtc*.dll',
    'nvrtc-builtins*.dll',
]


def patch_frozen_cv2_config(app_root):
    namespace = runpy.run_path(str(CV2_PATCH_TOOL))
    namespace['patch_frozen_cv2_config'](app_root)


def collect_conda_cuda_runtime_dlls():
    library_bin = Path(sys.prefix) / 'Library' / 'bin'
    if not library_bin.exists():
        return []
    seen = set()
    binaries = []
    for pattern in CUDA_RUNTIME_DLL_PATTERNS:
        for dll in sorted(library_bin.glob(pattern)):
            key = dll.name.lower()
            if key in seen:
                continue
            seen.add(key)
            binaries.append((str(dll), '.'))
    return binaries


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
    'timm.models.layers',
    'timm.models.helpers',
    'timm.models.registry',
    'seaborn',
    'yaml',
    'gdown',
    'caiman',
    'igraph',
    'leidenalg',
]
cuda_binaries = collect_conda_cuda_runtime_dlls()
datas = [
    ('xhr.ico', '.'),
    ('background.png', '.'),
    ('neural_starlight_startup.gif', '.'),
    ('README.md', '.'),
    ('DESIGN_NOTES.md', '.'),
    ('PACKAGING.md', '.'),
    ('NeuroAlign_atlas_registration_help.txt', '.'),
    ('NeuroAlign_atlas_registration_summary.json', '.'),
    ('neuroalign_step_worker.py', '.'),
    ('machine_setup.py', '.'),
    ('tools/install_nvidia_driver.ps1', 'tools'),
    ('workers', 'workers'),
    ('csbdeep', 'csbdeep'),
    ('DeepCADRT_Model', 'DeepCADRT_Model'),
    (str(WORKSPACE / 'NeuSuite2p' / 'segment_model.pt'), 'NeuSuite2p'),
    (str(WORKSPACE / 'NeuSuite2p' / 'method'), 'NeuSuite2p/method'),
    ('NeuSuite_RuntimeDeps', 'NeuSuite_RuntimeDeps'),
    ('CaImAn_Resources', 'CaImAn_Resources'),
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
    pathex=[str(ROOT), str(WORKSPACE / 'NeuSuite2p'), str(WORKSPACE / 'DeepCAD-RT' / 'DeepCAD_RT_pytorch')],
    binaries=cuda_binaries,
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
    icon=str(WORKER_ICON),
    contents_directory='.',
)

coll = COLLECT(
    gui_exe,
    [('_internal/NewLight_Worker.exe', worker_exe.name, 'EXECUTABLE')],
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NewLight_Analysis',
)
patch_frozen_cv2_config(Path(CONF['distpath']) / 'NewLight_Analysis')
