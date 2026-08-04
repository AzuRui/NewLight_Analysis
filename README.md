# NewLight_Analysis

NewLight_Analysis 是面向实验人员的双光子成像分析软件。它整合了
LabVIEW 双光子分析流程、`2cafe_analysis` 的 ROI 与热图分析方式、
CaImAn 源提取算法，以及已授权的 NeuSuite 实例分割模型。

软件采用低眩光的深色神经成像工作站风格，同时保持灰度图像区域的高
对比度，便于检查成像数据。主界面使用 Python/Tkinter 实现，后台模型和
耗时任务通过独立 worker 运行。

## 软件架构

- 主程序使用 Python/Tkinter，源码调试可运行 `run_NewLight_Analysis.bat`。
- 快速 ROI 后端使用授权的 `NeuSuite2p/segment_model.pt`，并通过已有的
  CUDA-enabled `neuroseg3` 环境运行。
- CaImAn ROI 后端使用 CNMF/CNMF-E，并通过项目环境
  `.conda_envs/newlight_caiman` 运行。
- 两个 ROI worker 输出带版本信息的 NPZ 结果，并保留每个 ROI 的任意形状，
  不会把实例强制转换为圆形、椭圆或合并后的连通区域。
- 软件内置运动矫正、滤波、血管/伪影检测、ROI 绘制、dF/F、热图、曲线和
  相关性分析等基础算法。

软件用户只需要面对一个分析界面；不同算法的环境隔离由开发和打包脚本
负责维护。

## 源码运行

在项目根目录执行：

```bat
run_NewLight_Analysis.bat
```

或者：

```powershell
cd E:\WorkSpace\NewLight_Analysis
python NewLight_Analysis.py
```

源码运行用于开发和调试。正式用户应运行打包后的
`NewLight_Analysis.exe`，不需要打开源码环境。

## 编译 EXE

在安装了 Conda 的 Windows 编译机上，推荐执行：

```bat
build_portable_exe.bat
```

该脚本会先检查或准备 `caiman_latest` 编译环境，再调用
`build_exe.bat` 生成便携版程序。已有的 CUDA、cuDNN 和 PyTorch 包会被
保留，不会因为编译而自动替换。

只准备环境而不编译：

```bat
setup_build_environment.bat
```

完整的中文环境配置、编译、验证和发布说明见：

```text
BUILD_README.md
```

## 用户手册

详细中文用户手册位于：

```text
docs\NewLight_Analysis_User_Manual.md
docs\NewLight_Analysis_User_Manual.docx
docs\NewLight_Analysis_User_Manual.pdf
```

发布构建会将手册复制到 `dist\NewLight_Analysis`。手册中保留了编号的
截图占位位置，后续可以补充界面截图而不需要重写操作流程。

## 主要功能

- 导入 `.tif`、`.tiff`、`.avi`、`.mp4`、`.mov`、`.mkv` 等视频或图像数据。
- 导入刺激事件文件，或按照固定时间间隔生成刺激触发点。
- 设置视频帧率、刺激采样率、baseline 起始帧、baseline 持续帧数及刺激前后窗口。
- 预览均值、最大值、标准差和 25% 分位数图像。
- 使用帧滑块检查预处理后任意帧。
- 支持 8 bit 和 16 bit 数据处理，并尽量保持输入位深。
- 预处理：CaImAn 运动矫正、快速刚性运动矫正、刚性加柔性形变矫正、
  高斯平滑、中值滤波、背景扣除、漂白校正、阴影/高亮/亮度/对比度调整、
  血管和伪影检测抑制、DeepCAD-RT 深度学习降噪。
- 加速状态检查：检查 CUDA 状态，支持时使用 CuPy，没有 CuPy 时回退到 CPU/NumPy。
- ROI：`CaImAn 识别分割`、`快速 ROI 分割`、自适应拟合、低质量标记、
  图谱导入、中心圆、自由轮廓、ROI 列表、颜色管理、NPZ 保存和载入。
- Atlas Reference Builder 标准图谱构建和 NeuroAlign 当前视频流脑区配准。
- 分析：dF/F、25% 分位数或指定帧区间 baseline、刺激-响应对齐平均、峰值标记、
  ROI 相关性、统计表、热图、热图 AVI，以及 CSV/XLSX/PNG/JSON/NPZ/TIFF/AVI 导出。
- 工作流：保存当前数据任务流为 JSON，并在其他数据上重新执行。

## 推荐操作流程

1. 源码调试时运行 `run_NewLight_Analysis.bat`，发布版运行 `NewLight_Analysis.exe`。
2. 在“数据”页面导入视频、TIFF 或双光子原始数据文件夹。
3. 如有刺激，导入刺激文件并设置视频帧率、刺激采样率和 baseline 参数。
4. 根据需要执行预处理，每一步都会进入任务流和撤销记录。
5. 使用 CaImAn、快速 ROI、图谱导入、圆形或自由轮廓生成 ROI。
6. 检查 ROI 列表和低质量标记，必要时进行自适应拟合或手动补充。
7. 提取 dF/F，检查峰值、刺激对齐平均、相关性和热图。
8. 使用“保存当前视频”或分析页面导出结果，也可以保存当前任务流为 JSON。

## ROI 算法选择

### 快速 ROI 分割

适合快速得到投影图 ROI。主要参数包括置信度、实例 IoU、模型输入尺寸和
恢复后的像素面积范围。worker 直接读取实例 mask，并保留重叠的独立 ROI。

### CaImAn 识别分割

适合利用钙信号时间变化进行源提取。细胞直径转换为：

```text
gSig = max(1, round(细胞直径 / 4))
```

组件还可以根据时间信噪比、空间相关性和可选 CaImAn CNN 分数筛选。

## 后端环境

```bat
setup_newlight_caiman.bat
setup_neusuite_runtime.bat
```

前者准备 CaImAn 环境和 CNN 资源，后者准备 NeuSuite 纯 Python 运行时依赖。

## CUDA 限制

> **重要：DeepCAD-RT 必须依赖 CUDA。** DeepCAD-RT 没有 CPU fallback，
> 只能在具备兼容 NVIDIA GPU 和驱动的电脑上运行。安装包中的模型和 CUDA
> 运行库不会让它在纯 CPU、AMD 或 Intel 显卡电脑上可用。
> CUDA 不是 NewLight_Analysis 主程序的启动条件。驱动安装被取消、失败，
> 或 GTX 960 等旧显卡无法使用当前 CUDA 扩展时，软件仍会进入 CPU 模式；
> 每次启动都会重新检查可选 GPU 扩展是否已完整配置。

- 快速 ROI 分割可以通过 PyTorch 使用 CUDA。
- 投影、dF/F、平滑和 ROI 曲线提取在安装 CuPy 时可以使用 GPU。
- 没有 CuPy 时，这些基础运算回退到 CPU/NumPy。
- CaImAn 运动矫正速度取决于版本、CPU、磁盘和参数。

## Git LFS 与大文件

Git LFS 会把大文件以指针形式放入 Git 仓库，把真实二进制内容放到 LFS
对象存储中。它适合管理模型文件、较大的示例资源或其他二进制文件。

但 Git LFS 不是无限容量，也不能绕过 GitHub 的所有限制：

- 单个 LFS 文件仍受 GitHub 单文件大小限制。当前安装包约 2.4 GB，仍超过常用的 2 GiB 上限。
- LFS 还受仓库存储容量和下载流量配额限制，额度取决于 GitHub 账户计划。
- 使用 LFS 后，协作者需要安装 Git LFS，并执行 `git lfs pull` 才能取回真实文件。
- GitHub Release 附件和 Git LFS 是两套机制；LFS 文件不会自动成为 Release 附件。

建议：源码、配置和小型模型正常提交 Git；小于限制的模型可以使用 LFS；
2.4 GB 安装包放到 OneDrive、Google Drive、OSS 等大文件存储中，并在
GitHub Release 或 README 中提供下载地址和 SHA-256 校验值。

启用 LFS 的示例：

```powershell
git lfs install
git lfs track "DeepCADRT_Model/*.pth"
git add .gitattributes DeepCADRT_Model/*.pth
git commit -m "chore: track model with Git LFS"
```

使用前请确认模型大小、LFS 存储配额和团队成员的下载方式。不要对当前
2.4 GB 安装包直接执行 `git lfs track`，因为它仍超过单文件限制。
