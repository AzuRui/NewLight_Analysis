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
- 项目内的 DeepCAD-RT、CaImAn、NeuSuite 模型和运行时资源。

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

必须整体复制 `dist\NewLight_Analysis`，不能只复制主 EXE；Python、CUDA、
模型和 worker 位于 `_internal` 目录。

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

## 五、编译后验证

在发布目录执行：

```bat
dist\NewLight_Analysis\check_backends.bat /verify-only
```

它会检查冻结后的 Python、OpenCV、CaImAn、NeuSuite 和 DeepCAD-RT worker，
并报告 CUDA/cuDNN 状态。

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
DeepCADRT_Model\E_02_Iter_6416.pth
..\NeuSuite2p\segment_model.pt
CaImAn_Resources\model\cnn_model.pkl
CaImAn_Resources\model\cnn_model_online.pkl
NeuSuite_RuntimeDeps\
```

### DeepCAD-RT 无法运行

确认目标电脑有 NVIDIA GPU 和兼容驱动。DeepCAD-RT 没有 CPU fallback；
打包模型和 CUDA DLL 不会让它在 CPU、AMD 或 Intel 机器上可用。

## 七、GitHub 发布

源码和脚本可以提交到 GitHub，但不要把安装包写入 Git 历史。GitHub
Release 单个附件必须小于 `2 GiB`；当前完整安装包约 `2.4 GB`，超过该
限制。建议将安装包放在 OneDrive、Google Drive、OSS 等大文件存储中，
并在 GitHub Release 中提供下载链接和 SHA-256 校验值：

```powershell
Get-FileHash Output\NewLight_Analysis_setup.exe -Algorithm SHA256
```
