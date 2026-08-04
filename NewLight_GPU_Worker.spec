# -*- mode: python ; coding: utf-8 -*-

import importlib.util
import sys
from pathlib import Path

ROOT = Path.cwd()
PYINSTALLER_DIR = Path(importlib.util.find_spec('PyInstaller').origin).parent
CUDA_PATTERNS = [
    'c10_cuda.dll', 'torch_cuda.dll', 'caffe2_nvrtc.dll',
    'cublas*.dll', 'cudart*.dll', 'cudnn*.dll', 'cufft*.dll',
    'cufftw*.dll', 'cusolver*.dll', 'cusolverMg*.dll',
    'cusparse*.dll', 'nvrtc*.dll', 'nvrtc-builtins*.dll',
    'magma*.dll', 'cudss*.dll',
]


def collect_cuda_binaries():
    library_bin = Path(sys.prefix) / 'Library' / 'bin'
    seen = set()
    result = []
    for pattern in CUDA_PATTERNS:
        for dll in sorted(library_bin.glob(pattern)):
            if dll.name.lower() not in seen:
                seen.add(dll.name.lower())
                result.append((str(dll), '.'))
    return result


a = Analysis(
    ['worker_launcher.py'],
    pathex=[str(ROOT)],
    binaries=collect_cuda_binaries(),
    datas=[
        ('workers/run_deepcadrt.py', 'workers'),
        ('workers/run_neusuite_roi.py', 'workers'),
        ('csbdeep', 'csbdeep'),
        (str(ROOT.parent / 'NeuSuite2p' / 'segment_model.pt'), 'NeuSuite2p'),
        (str(ROOT.parent / 'NeuSuite2p' / 'method'), 'NeuSuite2p/method'),
        ('NeuSuite_RuntimeDeps', 'NeuSuite_RuntimeDeps'),
    ],
    hiddenimports=[
        'cv2', 'numpy', 'scipy', 'skimage', 'tifffile', 'torch', 'torchvision',
        'PIL', 'matplotlib', 'pandas', 'yaml', 'seaborn',
        'timm', 'timm.models.layers', 'timm.models.helpers', 'timm.models.registry',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'jupyter', 'notebook', 'panel', 'bokeh', 'PySide6', 'openvino'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NewLight_GPU_Worker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(PYINSTALLER_DIR / 'bootloader' / 'images' / 'icon-console.ico'),
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NewLight_GPU_Worker',
)
