# NewLight_Analysis 环境配置与 EXE 编译说明

本文说明如何在 Windows 编译机上准备环境，并生成可迁移的
NewLight_Analysis 便携版 EXE。编译脚本默认使用 Python 3.8 兼容流程，
并优先复用已有的 `caiman_latest` Conda 环境。

## 一、编译前检查

编译机需要具备：

- Windows 10/11 64 位。
- Miniconda 或 Anaconda，并且 `conda` 已加入 PATH。
- 项目根目录外的配套源码目录：`E:\WorkSpace\NeuSuite2p`、
  `E:\WorkSpace\DeepCAD-RT\DeepCAD_RT_pytorch`、
  `E:\WorkSpace\2cafe_analysis\NeuroAlign`。
- 项目内的 CaImAn 资源。NeuSuite、DeepCAD-RT、Torch/CUDA 运行库和模型
  通过独立 GPU 扩展包提供，不再固定装入核心 EXE。

编译脚本不会删除或修改 `2`、`example`、`eye` 等验证和实验数据。

## 二、准备环境

在项目根目录执行：

```bat
setup_build_environment.bat
```

脚本会检查 Conda、准备或修复 `caiman_latest`、安装
`setuptools<81` 和 PyInstaller 6.x，并验证科学计算导入与模型路径。
如果 `caiman_latest` 不存在，会使用 `environment-build.yml` 创建 Python
3.8 基础环境。

无人值守模式：

```bat
setup_build_environment.bat /nopause
```

已有 `caiman_latest` 时，脚本不会替换其中的 CUDA、cuDNN 或 PyTorch。
如果需要 DeepCAD-RT 或快速 ROI 推理，必须安装与 NVIDIA 驱动匹配的
CUDA-enabled PyTorch。AMD/Intel 显卡可以使用部分 CPU 功能，但不能运行
DeepCAD-RT 等 CUDA 功能。

## 三、生成便携版 EXE

推荐执行：

```bat
build_portable_exe.bat
```

它会先准备环境，再调用 `build_exe.bat`。输出目录为：

```text
dist\NewLight_Analysis\NewLight_Analysis.exe
```

必须整体复制 `dist\NewLight_Analysis`，不能只复制主 EXE；Python、OpenCV、
CaImAn 和 CPU worker 位于 `_internal` 目录。Torch、CUDA、NeuSuite、
DeepCAD-RT 源码和 `.pth` 权重不在核心包中。

生成完整 GPU 独立扩展包：

```bat
build_gpu_addon.bat
```

将生成的 `GPU_Addon_CUDA.zip.part01` 和 `.part02` 上传到
`gpu_addon_manifest.json` 指向的 GitHub Release。首次启动检测到
NVIDIA 驱动时，软件会自动下载、校验、拼接并解压到
`_internal\GPU_Addon`；AMD/Intel 或 CPU 环境会跳过 GPU 功能。

当前 PyInstaller spec 已排除未使用的 Jupyter、Panel、Bokeh、PySide6、
OpenVINO、PyAV、imagecodecs 和可选 NWB schema 组件。实验构建显示便携目录
核心便携目录实测约 1.10 GB，同时 CPU CaImAn/OpenCV 后端检查通过；GPU
扩展单独发布。最终安装包压缩大小仍需在
安装了 Inno Setup 的机器上实测。

无人值守编译：

```bat
build_portable_exe.bat /nopause
```

## 四、生成安装程序

安装 Inno Setup 6 并确保 `ISCC.exe` 可用后，执行：

```bat
build_full_release.bat
```

脚本会生成便携版，并在 Inno Setup 可用时生成：

```text
Output\NewLight_Analysis_setup.exe
```

没有 Inno Setup 时，脚本仍会保留完整的便携版目录。

对于已经生成的 `dist_slim2_20260804` 精简包，可以单独运行：

```bat
build_slim2_installer.bat
```

该脚本使用 `NewLight_Analysis_slim2_setup.iss`，输出
`Output\NewLight_Analysis_slim2_setup.exe`，并采用固实
`lzma2/ultra64` 压缩。当前机器没有 `ISCC.exe`，因此尚未实际生成该安装包。

## 五、编译后验证

在发布目录执行：

```bat
dist\NewLight_Analysis\check_backends.bat /verify-only
```

它会检查冻结后的 Python、OpenCV 和 CaImAn；GPU 扩展安装后还会检查
NeuSuite 和 DeepCAD-RT GPU worker。

## 六、常见问题

### `No module named pkg_resources`

重新执行 `setup_build_environment.bat`。脚本会安装兼容的
`setuptools<81`。

### `cv2 recursion is detected`

重新执行 `build_exe.bat /nopause`。构建脚本会执行
`tools\patch_frozen_cv2.py` 修正冻结版 OpenCV 加载路径。

### 模型文件缺失

确认以下路径存在：

```text
DeepCADRT_Model\E_02_Iter_6416.pth（仅用于生成可选 DeepCAD GPU 扩展包）
..\NeuSuite2p\segment_model.pt
CaImAn_Resources\model\cnn_model.pkl
CaImAn_Resources\model\cnn_model_online.pkl
NeuSuite_RuntimeDeps\
```

### DeepCAD-RT 无法运行

确认目标电脑有 NVIDIA GPU 和兼容驱动，并确认首次启动能访问
`gpu_addon_manifest.json` 中的 GitHub Release。DeepCAD-RT 没有 CPU
fallback；扩展模型和 CUDA DLL 不会让它在 CPU、AMD 或 Intel 机器上可用。
当前仓库为私有仓库时，其他电脑无法匿名下载 Release 附件；发布给外部
用户前，需要将扩展附件放到无需登录的公开 Release 或对象存储，并同步更新
manifest 的 URL 和 SHA-256。

## 七、GitHub 发布

源码和脚本可以提交到 GitHub，但不要把安装包写入 Git 历史。GitHub
Release 单个附件必须小于 `2 GiB`；当前完整安装包约 `2.4 GB`，超过该
限制。建议将安装包放在 OneDrive、Google Drive、OSS 等大文件存储中，
并在 GitHub Release 中提供下载链接和 SHA-256 校验值：

```powershell
Get-FileHash Output\NewLight_Analysis_setup.exe -Algorithm SHA256
```

## 八、核心包与 GPU 扩展包

核心安装包不包含 Torch。运行：

```bat
build_exe.bat
```

`build_exe.bat` 使用 `caiman_latest`，但 spec 明确排除 Torch、TorchVision、
timm 和 CUDA DLL。核心不包含 DeepCAD-RT、NeuSuite 或 GPU 模型。

GPU 扩展使用 CUDA 环境单独构建：

```bat
build_gpu_addon.bat
```

该脚本生成 CUDA worker、CUDA 运行库、DeepCAD-RT 源码和模型，并生成：

```text
GPU_Addon_CUDA.zip.part01
GPU_Addon_CUDA.zip.part02
```

两个分段都必须上传到 `gpu-addon-v1` 对应的 GitHub Release。首次启动
检测到 NVIDIA 驱动后，软件会自动下载两个分段，逐段校验、拼接完整 ZIP，
再校验完整 SHA-256 并解压到 `_internal\GPU_Addon`。AMD/Intel 或 CPU-only
电脑会跳过 GPU 扩展。
