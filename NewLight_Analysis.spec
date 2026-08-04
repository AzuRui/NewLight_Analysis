# -*- mode: python ; coding: utf-8 -*-

import importlib.util
import os
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
DEEPCAD_ADDON_DLL_PATTERNS = {
    'magma.dll',
    'cudss*.dll',
    'cusolver*.dll',
    'cusparse*.dll',
}


def patch_frozen_cv2_config(app_root):
    namespace = runpy.run_path(str(CV2_PATCH_TOOL))
    namespace['patch_frozen_cv2_config'](app_root)


def collect_conda_cuda_runtime_dlls(include_deepcad_addon=False):
    library_bin = Path(sys.prefix) / 'Library' / 'bin'
    if not library_bin.exists():
        return []
    seen = set()
    binaries = []
    for pattern in CUDA_RUNTIME_DLL_PATTERNS:
        if not include_deepcad_addon and pattern in DEEPCAD_ADDON_DLL_PATTERNS:
            continue
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
    'seaborn',
    'yaml',
    'gdown',
    'caiman',
    'igraph',
    'leidenalg',
]
build_mode = os.environ.get('NEWLIGHT_BUILD_MODE', 'cpu').strip().lower()
cuda_binaries = (
    collect_conda_cuda_runtime_dlls(include_deepcad_addon=True)
    if build_mode == 'gpu'
    else []
)
slim_excludes = [
    # These optional GUI/notebook stacks are not used by the Tkinter app or
    # its bundled workers.
    'IPython',
    'ipykernel',
    'ipywidgets',
    'jupyter',
    'jupyter_client',
    'jupyter_core',
    'jupyter_server',
    'jupyterlab',
    'nbclassic',
    'nbconvert',
    'nbformat',
    'notebook',
    'panel',
    'bokeh',
    'holoviews',
    'param',
    'pyviz_comms',
    'PySide6',
    'openvino',
    'hf_xet',
    'av',
    'imagecodecs',
    'torch',
    'torchvision',
    'timm',
    # The application accepts TIFF/AVI/video inputs, not NWB files. CaImAn's
    # optional NWB schema stack is therefore outside the packaged workflow.
    'hdmf',
    'pynwb',
]
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
    ('gpu_addon_manifest.json', '.'),
    ('tools/install_nvidia_driver.ps1', 'tools'),
    ('workers', 'workers'),
    ('csbdeep', 'csbdeep'),
    ('CaImAn_Resources', 'CaImAn_Resources'),
    (str(WORKSPACE / '2cafe_analysis' / 'NeuroAlign'), 'NeuroAlign'),
]
ipyparallel_spec = importlib.util.find_spec('ipyparallel')
if ipyparallel_spec and ipyparallel_spec.origin:
    ipyparallel_root = Path(ipyparallel_spec.origin).parent
    shellcmd_receiver = ipyparallel_root / 'cluster' / 'shellcmd_receive.py'
    if shellcmd_receiver.exists():
        datas.append((str(shellcmd_receiver), 'ipyparallel/cluster'))


a = Analysis(
    ['launch.py'],
    # DeepCAD-RT is an optional runtime addon. Keep its source and model out
    # of the core package; machine_setup downloads it after CUDA validation.
    pathex=[str(ROOT), str(WORKSPACE / 'NeuSuite2p')],
    binaries=cuda_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=slim_excludes,
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
