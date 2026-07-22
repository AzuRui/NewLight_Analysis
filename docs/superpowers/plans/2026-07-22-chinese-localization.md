# NewLight_Analysis Chinese Localization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 NewLight_Analysis 的用户可见界面、参数、弹窗、日志和图表完整中文化，同时保留模型原名及稳定的英文内部参数值。

**Architecture:** 新建 `ui_text_zh.py` 保存模型显示名、预处理动作 ID、中文标签和选项值映射。`NewLight_Analysis.py` 只把中文用于显示，所有动作分支和 worker 参数继续使用英文内部值；其他散布的用户可见文本按窗口、运行流程和图表分批翻译。

**Tech Stack:** Python 3.8、Tkinter/ttk、Matplotlib、unittest/pytest、现有 `caiman_latest` Conda 环境。

---

## File Map

- Create `ui_text_zh.py`: 中文显示常量、预处理动作定义、下拉选项的显示值/内部值映射。
- Create `tests/test_chinese_localization.py`: 中文化契约、内部 ID 映射、主要界面文本和布局宽度回归测试。
- Modify `NewLight_Analysis.py`: 使用中文显示目录，翻译全部 GUI、运行日志和图表文字，统一左侧按钮宽度。
- Modify `analysis_core.py`: 翻译会直接呈现给用户的校验错误，保留第三方原始日志。
- Modify `NeuroAlign_atlas_registration_help.txt`: 将应用内 NeuroAlign 帮助全文翻译为中文。
- Modify `tests/test_gui_static.py`: 把旧英文界面断言调整为中文显示和稳定内部 ID 断言。
- Modify `WORK_LOG.md`: 记录中文化范围、布局和验证结果。
- Modify `PROJECT_HANDOFF.md`: 记录中文显示层约束和后续编译注意事项。

### Task 1: 建立中文显示目录与稳定内部 ID

**Files:**
- Create: `ui_text_zh.py`
- Create: `tests/test_chinese_localization.py`

- [ ] **Step 1: 先写中文名称和内部 ID 的失败测试**

```python
import unittest

import ui_text_zh as zh


class ChineseLocalizationTests(unittest.TestCase):
    def test_model_names_keep_original_name_and_add_chinese_function(self):
        self.assertEqual(zh.MODEL_NAMES["deepcad_rt"], "DeepCAD-RT 深度学习降噪")
        self.assertEqual(zh.MODEL_NAMES["neuroseg3"], "NeuroSeg3 自动 ROI 分割")
        self.assertEqual(zh.MODEL_NAMES["neuroalign"], "NeuroAlign 脑图谱配准")

    def test_preprocess_actions_use_stable_ids_and_chinese_labels(self):
        caiman = zh.PREPROCESS_PANEL_SPECS["caiman_motion"]
        self.assertEqual(caiman["label"], "CaImAn 运动矫正")
        self.assertEqual(caiman["fields"][0][0], "mode")
        self.assertEqual(caiman["fields"][0][3], (("rigid", "仅刚性"), ("piecewise", "分块刚性")))

    def test_every_preprocess_action_has_a_unique_chinese_label(self):
        labels = [spec["label"] for spec in zh.PREPROCESS_PANEL_SPECS.values()]
        self.assertEqual(len(labels), 10)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertTrue(all(any("\u4e00" <= char <= "\u9fff" for char in label) for label in labels))
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'ui_text_zh'`。

- [ ] **Step 3: 创建最小中文显示目录**

```python
MODEL_NAMES = {
    "caiman": "CaImAn 运动矫正",
    "deepcad_rt": "DeepCAD-RT 深度学习降噪",
    "neuroseg3": "NeuroSeg3 自动 ROI 分割",
    "neuroalign": "NeuroAlign 脑图谱配准",
    "atlas_builder": "标准图谱构建",
}

PREPROCESS_PANEL_SPECS = {
    "caiman_motion": {
        "label": MODEL_NAMES["caiman"],
        "description": "CaImAn 运动矫正/去抖动。分块刚性模式会先进行整体刚性矫正，再进行局部矫正；patch 尺寸等于步长加重叠宽度。",
        "fields": [
            ("mode", "模式", "piecewise", (("rigid", "仅刚性"), ("piecewise", "分块刚性"))),
            ("max_shift", "最大整体位移 (px)", 12),
            ("stride", "Patch 步长 (px)", 48),
            ("overlap", "Patch 重叠 (px)", 24),
            ("max_deviation", "最大局部偏差 (px)", 5),
        ],
    },
    "builtin_rigid_motion": {
        "label": "内置刚性运动矫正",
        "description": "使用两轮刚性配准。手动模式下，参考起始帧从 0 开始计数。",
        "fields": [
            ("reference_mode", "参考帧模式", "auto", (("auto", "自动"), ("manual", "手动"))),
            ("reference_start", "参考起始帧", 0),
            ("reference_frames", "参考帧数量", 100),
            ("max_shift", "最大刚性位移 (px)", 15),
        ],
    },
    "image_shift": {
        "label": "图像行偏移校正",
        "description": "校正双光子隔行扫描产生的水平行偏移。",
        "fields": [
            ("range", "搜索范围 (+/- px)", 10),
            ("row_parity", "移动行", "odd", (("odd", "奇数行"), ("even", "偶数行"))),
        ],
    },
    "gaussian_smooth": {"label": "高斯平滑", "description": "逐帧进行空间高斯平滑。", "fields": [("sigma", "空间 sigma", 1.0)]},
    "median_filter": {"label": "中值滤波", "description": "逐帧进行空间中值滤波。", "fields": [("size", "核大小 (px)", 3)]},
    "background_subtract": {"label": "背景扣除", "description": "从每帧中扣除高斯模糊后的局部背景。", "fields": [("sigma", "背景 sigma", 20)]},
    "bleach_correction": {"label": "光漂白校正", "description": "去除全画面的二次光漂白趋势。", "fields": []},
    "enhance_contrast": {"label": "对比度增强", "description": "逐帧归一化后进行自适应直方图均衡。", "fields": [("clip_limit", "裁剪限制", 0.02)]},
    "detect_vessels": {"label": "检测血管/伪影", "description": "以红色蒙版预览可能的血管或伪影像素。", "fields": [("threshold", "阈值百分位", 90), ("alpha", "蒙版透明度", 0.45)]},
    "remove_vessel_artifact": {"label": "去除血管伪影", "description": "检测并抑制当前视频中的血管或伪影像素。", "fields": [("threshold", "阈值百分位", 90)]},
}
```

- [ ] **Step 4: 运行中文目录测试并确认通过**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: `3 passed`。

- [ ] **Step 5: 提交中文目录基础**

```powershell
git add -- ui_text_zh.py tests/test_chinese_localization.py
git commit -m "Add Chinese UI text catalog"
```

### Task 2: 将预处理显示文本与运行参数彻底分离

**Files:**
- Modify: `NewLight_Analysis.py:25-115`
- Modify: `NewLight_Analysis.py:1864-1950`
- Modify: `NewLight_Analysis.py:3365-3520`
- Modify: `tests/test_chinese_localization.py`
- Modify: `tests/test_gui_static.py`

- [ ] **Step 1: 写下拉选项和动作路由的失败测试**

```python
from pathlib import Path


def test_preprocess_buttons_route_by_internal_action_id():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
    assert "for action_id, spec in PREPROCESS_PANEL_SPECS.items()" in source
    assert "command=lambda key=action_id: self.show_preprocess_parameters(key)" in source
    assert 'if action_id == "caiman_motion"' in source
    assert 'if action_id == "builtin_rigid_motion"' in source


def test_parameter_choice_display_is_mapped_back_to_internal_value():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
    assert "self.parameter_choice_values" in source
    assert "display_to_value" in source
    assert "self.parameter_choice_values.get(key, {}).get(display_value, display_value)" in source
```

- [ ] **Step 2: 运行测试并确认旧代码仍按英文标签路由而失败**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: FAIL，缺少 `action_id` 路由和 `parameter_choice_values`。

- [ ] **Step 3: 导入中文目录并删除主文件中的旧英文 specs**

```python
import analysis_core as core
import ui_background
from ui_text_zh import MODEL_NAMES, PREPROCESS_PANEL_SPECS
```

删除 `NewLight_Analysis.py` 内原有以 `"CaImAn Motion"` 等英文显示名为键的 `PREPROCESS_PANEL_SPECS`。

- [ ] **Step 4: 让参数面板支持中文选项到英文内部值的双向映射**

在初始化和清理阶段增加：

```python
self.parameter_choice_values = {}
self.parameter_choice_displays = {}
```

在 `show_parameter_panel` 中将选项元组解析为 `(internal_value, display_label)`：

```python
choices = tuple(field[3]) if len(field) > 3 else ()
if choices:
    value_to_display = {str(value): display for value, display in choices}
    display_to_value = {display: str(value) for value, display in choices}
    shown_default = value_to_display.get(str(default), str(default))
    value_var = tk.StringVar(value=shown_default)
    entry = ttk.Combobox(
        item,
        textvariable=value_var,
        values=tuple(display_to_value),
        state="readonly",
    )
    self.parameter_choice_values[key] = display_to_value
    self.parameter_choice_displays[key] = value_to_display
else:
    value_var = tk.StringVar(value=str(default))
    entry = ttk.Entry(item, textvariable=value_var)
```

在读取和重置参数时转换值：

```python
def panel_parameter_values(self):
    values = {}
    for key, value_var in self.parameter_vars.items():
        display_value = value_var.get()
        values[key] = self.parameter_choice_values.get(key, {}).get(display_value, display_value)
    return values

def reset_parameter_panel(self):
    for key, default in self.parameter_defaults.items():
        value_var = self.parameter_vars.get(key)
        if value_var is not None:
            shown = self.parameter_choice_displays.get(key, {}).get(str(default), str(default))
            value_var.set(shown)
```

- [ ] **Step 5: 按内部 ID 创建按钮和执行动作**

```python
for row, (action_id, spec) in enumerate(PREPROCESS_PANEL_SPECS.items()):
    ttk.Button(
        pre_box,
        text=spec["label"],
        style="Sidebar.TButton",
        command=lambda key=action_id: self.show_preprocess_parameters(key),
    ).grid(row=row, column=0, sticky="ew", pady=2)
```

`show_preprocess_parameters(action_id)` 使用 `spec = PREPROCESS_PANEL_SPECS[action_id]`，并将现有英文标签比较改为稳定 ID 比较。CaImAn、内置刚性和图像行偏移等实际 worker 参数仍为 `piecewise`、`rigid`、`auto`、`manual`、`odd`、`even`。

- [ ] **Step 6: 更新旧 GUI 静态断言并运行测试**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py tests/test_gui_static.py tests/test_caiman_motion.py tests/test_rigid_motion.py -q`

Expected: 全部 PASS，且参数传递断言保持通过。

- [ ] **Step 7: 提交内部 ID 路由**

```powershell
git add -- NewLight_Analysis.py tests/test_chinese_localization.py tests/test_gui_static.py
git commit -m "Separate Chinese labels from preprocess IDs"
```

### Task 3: 中文化主窗口并统一左侧按钮宽度

**Files:**
- Modify: `NewLight_Analysis.py:360-390`
- Modify: `NewLight_Analysis.py:1620-1880`
- Modify: `tests/test_chinese_localization.py`

- [ ] **Step 1: 写主窗口中文和布局失败测试**

```python
def test_main_tabs_and_primary_sections_are_chinese():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
    for text in ('text="数据"', 'text="预处理"', 'text="ROI"', 'text="分析"', 'text="运行日志"'):
        assert text in source
    assert 'text="CaImAn 运动矫正"' not in source  # 模型按钮来自中文目录，不重复硬编码


def test_sidebar_has_stable_width_and_uniform_button_style():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
    assert "SIDEBAR_WIDTH = 300" in source
    assert "side.configure(width=SIDEBAR_WIDTH)" in source
    assert "side.grid_propagate(False)" in source
    assert 'style.configure("Sidebar.TButton"' in source
```

- [ ] **Step 2: 运行测试并确认英文主窗口与未固定侧栏导致失败**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: FAIL，缺少中文标签和 `SIDEBAR_WIDTH`。

- [ ] **Step 3: 设置统一布局常量与按钮样式**

```python
SIDEBAR_WIDTH = 300
PARAM_PANEL_WIDTH = 290
```

在主题样式初始化处加入：

```python
style.configure("Sidebar.TButton", anchor="center", padding=(8, 5))
```

在侧栏创建后加入：

```python
side.configure(width=SIDEBAR_WIDTH)
side.grid_propagate(False)
```

所有左侧功能按钮使用 `Sidebar.TButton` 并保持 `sticky="ew"`，不改变通道色块或图像工具栏按钮。

- [ ] **Step 4: 翻译主界面固定文字**

翻译范围包括：

```python
tabs.add(flow_tab, text="数据")
tabs.add(pre_tab, text="预处理")
tabs.add(roi_tab, text="ROI")
tabs.add(analysis_tab, text="分析")
```

并将数据、视图、实验协议、预处理、硬件加速、分析、导出、参数、运行日志、帧导航和 ROI 绘制工具等标签改为中文。精简按钮示例：

```text
Open Source -> 打开数据
Add Channel Data -> 添加通道
Save Current Movie -> 保存当前视频
Extract dF/F Traces -> 提取 dF/F 曲线
Stimulus Event Average -> 刺激事件对齐平均
Generate Heatmap AVI -> 生成热图 AVI
Export ROI Snapshot -> 导出 ROI 快照
```

Logo 副标题改为 `神经影像分析工作站`，功能摘要改为 `ROI | 运动矫正 | dF/F | 热图`。

- [ ] **Step 5: 运行主窗口测试和静态 GUI 测试**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py tests/test_gui_static.py -q`

Expected: 全部 PASS。

- [ ] **Step 6: 提交主窗口中文化**

```powershell
git add -- NewLight_Analysis.py tests/test_chinese_localization.py tests/test_gui_static.py
git commit -m "Localize main window and widen sidebar"
```

### Task 4: 中文化设置弹窗、NeuroAlign 向导和热图窗口

**Files:**
- Modify: `NewLight_Analysis.py:398-1550`
- Modify: `tests/test_chinese_localization.py`

- [ ] **Step 1: 写主要弹窗中文失败测试**

```python
def test_major_dialogs_use_chinese_titles_and_commands():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
    required = (
        'self.title("打开数据")',
        'self.title("标准图谱构建")',
        'self.title("NeuroAlign 脑图谱配准")',
        'self.title("生成热图 AVI")',
        'text="浏览"',
        'text="帮助"',
        'text="取消"',
        'text="运行"',
        'text="上一步"',
        'text="下一步"',
        'text="重新构建"',
        'text="使用结果"',
    )
    for text in required:
        assert text in source
```

- [ ] **Step 2: 运行测试并确认现有英文弹窗导致失败**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: FAIL，至少缺少 `self.title("打开数据")`。

- [ ] **Step 3: 翻译通用弹窗与文件选择器**

翻译 `ParameterDialog`、`SourcePickerDialog`、`TextDisplayDialog`、通道颜色选择器中的按钮、标题、说明、文件类型名称和错误提示。颜色显示名改为绿色、红色、黄色、蓝色、紫色、灰色，内部值仍保留 `green/red/yellow/blue/purple/gray`。

- [ ] **Step 4: 翻译标准图谱与 NeuroAlign 工作流**

翻译 Atlas Builder、NeuroAlign 输入窗和三步向导的参数标签、步骤名称、预览状态、帮助标题、验证错误和按钮。以下模型名必须保留：`NeuroAlign`、`Leiden`、`JSON`。

- [ ] **Step 5: 翻译自动 ROI 和热图生成窗口**

翻译内置自动 ROI、NeuroSeg3、热图 AVI 的参数、预览状态、进度、错误和完成提示。`Detection confidence` 显示为 `检测置信度`，内部参数仍为 `detection_conf`；百分位、透明度和 sigma 保留单位/符号。

- [ ] **Step 6: 运行弹窗测试和语法检查**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py tests/test_gui_static.py -q`

Run: `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py ui_text_zh.py`

Expected: 全部 PASS，语法检查退出码为 0。

- [ ] **Step 7: 提交弹窗中文化**

```powershell
git add -- NewLight_Analysis.py tests/test_chinese_localization.py
git commit -m "Localize dialogs and workflow wizards"
```

### Task 5: 中文化运行流程、错误提示和分析图表

**Files:**
- Modify: `NewLight_Analysis.py:2040-4200`
- Modify: `analysis_core.py:220-2580`
- Modify: `tests/test_chinese_localization.py`

- [ ] **Step 1: 写运行日志、错误和图表中文失败测试**

```python
def test_runtime_messages_and_chart_titles_are_chinese():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
    required = (
        "请先打开视频",
        "处理完成",
        "临时预览",
        "ROI dF/F 曲线",
        "ROI 统计",
        "试次平均",
        "ROI 相关性",
        "导出完成",
    )
    for text in required:
        assert text in source


def test_core_validation_errors_presented_to_users_are_chinese():
    source = Path("analysis_core.py").read_text(encoding="utf-8")
    assert "不支持的视频输出类型" in source
    assert "基线起始帧" in source
    assert "至少需要两条 ROI 曲线" in source
```

- [ ] **Step 2: 运行测试并确认现有英文运行文本导致失败**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: FAIL，缺少中文运行消息和 core 校验错误。

- [ ] **Step 3: 翻译应用状态、日志和消息框**

逐项翻译 `self.status.set(...)`、`self.log(...)`、`messagebox.showinfo/showwarning/showerror(...)` 和文件对话框标题。日志保留路径、模型名、参数键和值，例如：

```python
self.log("正在运行 CaImAn 运动矫正...")
self.log("CaImAn 结果已载入当前临时预览；请使用“保存当前视频”永久保存。")
self.log(f"CaImAn 临时预览文件：{preview_path}")
```

第三方 worker 原始 traceback 不翻译，但应用生成的摘要标题和建议使用中文。

- [ ] **Step 4: 翻译直接暴露给 GUI 的 core 错误**

将加载、保存、位深、协议、刺激、ROI、运动矫正、热图和模型输出尺寸等 `ValueError/RuntimeError/IOError` 改为中文。错误中保留路径、shape、扩展名和环境/库名称，例如：

```python
raise IOError(f"无法打开视频：{path}")
raise ValueError(f"不支持的视频输出类型：{ext}。请使用 .tif、.tiff 或 .avi")
raise ValueError(f"基线起始帧 {start} 超出视频总帧数 {movie.shape[0]}")
raise ValueError("相关性导出至少需要两条 ROI 曲线")
```

- [ ] **Step 5: 翻译分析窗口和 Matplotlib 文本**

翻译 dF/F 曲线、ROI 统计、试次平均、峰值检测、相关性和刺激事件结果中的窗口标题、图题、轴标签、图例和空数据提示。数学符号、ROI 名称、dF/F 和单位保持原样。

- [ ] **Step 6: 运行核心和 GUI 回归测试**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py tests/test_gui_static.py tests/test_caiman_motion.py tests/test_rigid_motion.py tests/test_bit_depth.py -q`

Run: `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py ui_text_zh.py`

Expected: 全部 PASS，语法检查退出码为 0。

- [ ] **Step 7: 提交运行文本和图表中文化**

```powershell
git add -- NewLight_Analysis.py analysis_core.py tests/test_chinese_localization.py
git commit -m "Localize runtime messages and analysis charts"
```

### Task 6: 中文化 NeuroAlign 帮助并检查英文残留

**Files:**
- Modify: `NeuroAlign_atlas_registration_help.txt`
- Modify: `tests/test_chinese_localization.py`

- [ ] **Step 1: 写帮助文件中文和允许英文白名单测试**

```python
def test_neuroalign_help_is_chinese_and_keeps_technical_names():
    help_text = Path("NeuroAlign_atlas_registration_help.txt").read_text(encoding="utf-8")
    assert "NeuroAlign 脑图谱配准帮助" in help_text
    assert "标准图谱构建" in help_text
    assert "外轮廓拟合" in help_text
    assert "Leiden 聚类" in help_text


def test_primary_ui_no_longer_contains_known_english_labels():
    source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
    banned = (
        'text="Open Source"',
        'text="Save Current Movie"',
        'text="Run Log"',
        'text="Cancel"',
        'text="Apply"',
        'text="Browse"',
        'text="Generate Heatmap AVI"',
    )
    for label in banned:
        assert label not in source
```

- [ ] **Step 2: 运行测试并确认英文帮助和残留标签导致失败**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: FAIL，帮助标题仍为 `NeuroAlign help`。

- [ ] **Step 3: 翻译帮助全文**

完整翻译工具用途、标准图谱构建参数、三阶段预览流程、配准参数、输出文件和故障排查。保留 `NeuroAlign`、`Atlas JSON`、`Leiden`、`caiman_latest`、文件名和参数键，以便对照日志与论文方法。

- [ ] **Step 4: 使用 allowlist 复查界面英文残留**

Run: `rg -n 'text="[A-Za-z]|title\("[A-Za-z]|status\.set\("[A-Za-z]|self\.log\("[A-Za-z]' NewLight_Analysis.py`

逐条处理结果。只允许品牌/模型、技术缩写、文件格式、内部值或第三方原始输出；任何普通操作词都翻译为中文。

- [ ] **Step 5: 运行中文化测试**

Run: `conda run -n caiman_latest python -m pytest tests/test_chinese_localization.py -q`

Expected: 全部 PASS。

- [ ] **Step 6: 提交帮助与残留清理**

```powershell
git add -- NeuroAlign_atlas_registration_help.txt NewLight_Analysis.py tests/test_chinese_localization.py
git commit -m "Translate NeuroAlign help and remove English UI remnants"
```

### Task 7: 全量验证、窗口烟测与项目记录

**Files:**
- Modify: `WORK_LOG.md`
- Modify: `PROJECT_HANDOFF.md`

- [ ] **Step 1: 运行完整测试套件**

Run: `conda run -n caiman_latest python -m pytest -q`

Expected: 所有测试通过，0 failed。

- [ ] **Step 2: 运行语法和差异检查**

Run: `conda run -n caiman_latest python -m py_compile NewLight_Analysis.py analysis_core.py ui_text_zh.py workers/run_caiman.py`

Run: `git diff --check`

Expected: 两条命令退出码均为 0；Conda OpenCL 激活脚本现有的 `temp.txt` 提示可以出现，但不得导致测试失败。

- [ ] **Step 3: 运行隐藏 Tk 烟测**

执行一个短脚本创建 `tk.Tk()`、实例化 `NewLightApp`、调用 `update_idletasks()`，断言：

```python
assert app.root.winfo_reqwidth() >= 900
assert app.parameter_panel.winfo_exists()
assert app.parameter_panel.cget("text") == "参数"
```

随后销毁窗口，不进入主循环。Expected: 退出码 0，无 `TclError`。

- [ ] **Step 4: 通过源码启动并检查实际布局**

Run: `run_NewLight_Analysis.bat`

检查普通窗口和最大化窗口：左侧按钮宽度统一、最长名称完整、参数栏不截断、日志框和图像显示区未重叠、显示框仍按剩余区域居中。

- [ ] **Step 5: 记录完成状态**

在 `WORK_LOG.md` 记录翻译范围、按钮宽度、测试数量和未编译 EXE 状态；在 `PROJECT_HANDOFF.md` 记录：

```text
所有用户可见文本默认使用中文；模型原名和科研缩写保留。
预处理动作必须按内部 ID 路由，禁止用中文显示标签作条件判断。
下拉框通过显示值/内部值映射向 worker 传递英文参数。
```

- [ ] **Step 6: 提交记录并确认最终差异**

```powershell
git add -- WORK_LOG.md PROJECT_HANDOFF.md
git commit -m "Document Chinese localization"
git status --short
```

Expected: 本任务涉及文件没有未提交修改；不处理工作区中与本任务无关的既有修改或删除项。

