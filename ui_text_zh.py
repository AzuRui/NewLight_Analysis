from __future__ import annotations


MODEL_NAMES = {
    "caiman": "CaImAn 运动矫正/去抖动",
    "caiman_roi": "CaImAn 识别分割",
    "fast_roi": "快速 ROI 分割",
    "deepcad_rt": "DeepCAD-RT 深度学习降噪",
    "neuroseg3": "NeuroSeg3 自动 ROI 分割",
    "neuroalign": "NeuroAlign 脑图谱配准",
    "atlas_builder": "标准图谱构建",
}

ROI_STAT_COLUMN_LABELS = {
    "ROI": "ROI",
    "Mean": "均值",
    "Std": "标准差",
    "Max": "最大值",
    "Baseline_25pct": "基线第 25 百分位",
    "CV": "变异系数 CV",
    "Peak_Count": "峰值数量",
    "Trigger_Count": "触发数量",
}


PREPROCESS_PANEL_SPECS = {
    "caiman_motion": {
        "label": MODEL_NAMES["caiman"],
        "description": (
            "CaImAn 运动矫正/去抖动。分块刚性模式会先进行整体刚性矫正，再进行局部矫正；"
            "Patch 尺寸等于步长加重叠宽度。"
        ),
        "fields": [
            ("mode", "模式", "piecewise", (("rigid", "仅刚性"), ("piecewise", "分块刚性"))),
            ("max_shift", "最大整体位移 (px)", 12),
            ("stride", "Patch 步长 (px)", 48),
            ("overlap", "Patch 重叠 (px)", 24),
            ("max_deviation", "最大局部偏差 (px)", 5),
        ],
    },
    "builtin_rigid_motion": {
        "label": "快速运动矫正",
        "description": (
            "先执行原有两轮刚性配准，再按需校正局部形变；手动模式的参考起始帧从 0 开始计数。"
            "柔性强度为 0 时仅执行刚性矫正并保持原有结果，轻度局部运动建议使用 0.2-0.5；"
            "数值越大形变越强，也越可能改变细胞轮廓。局部块越小可跟踪越细的运动，但速度更慢、稳定性更低。"
            "最大局部形变是安全上限而非目标值；较强或复杂的形变建议使用 CaImAn 分块刚性。"
        ),
        "fields": [
            ("reference_mode", "参考帧模式", "auto", (("auto", "自动"), ("manual", "手动"))),
            ("reference_start", "参考起始帧", 0),
            ("reference_frames", "参考帧数量", 100),
            ("max_shift", "最大刚性位移 (px)", 15),
            ("flexible_strength", "柔性强度 (0=关闭)", 0.0),
            ("local_block_size", "局部块尺寸 (px)", 96),
            ("max_local_deformation", "最大局部形变 (px)", 3.0),
        ],
    },
    "auto_crop_edges": {
        "label": "自动裁剪无效边缘",
        "description": (
            "自动识别运动矫正后由填充、重复或空白像素形成的外缘线条。"
            "主预览中的蓝色框可整体拖动，也可拖动边线或控制点缩放；确认后仅裁剪当前临时视频、各通道和 ROI，"
            "不会修改原始导入文件。"
        ),
        "fields": [],
    },
    "image_shift": {
        "label": "图像行偏移校正",
        "description": "校正双光子隔行扫描产生的水平行偏移。",
        "fields": [
            ("range", "搜索范围 (+/- px)", 10),
            ("row_parity", "移动行", "odd", (("odd", "奇数行"), ("even", "偶数行"))),
        ],
    },
    "gaussian_smooth": {
        "label": "高斯平滑",
        "description": "逐帧进行空间高斯平滑。",
        "fields": [("sigma", "空间 sigma", 1.0)],
    },
    "median_filter": {
        "label": "中值滤波",
        "description": "逐帧进行空间中值滤波。",
        "fields": [("size", "核大小 (px)", 3)],
    },
    "background_subtract": {
        "label": "背景扣除",
        "description": "从每帧中扣除高斯模糊后的局部背景。",
        "fields": [("sigma", "背景 sigma", 20)],
    },
    "bleach_correction": {
        "label": "光漂白校正",
        "description": "去除全画面的二次光漂白趋势。",
        "fields": [],
    },
    "enhance_contrast": {
        "label": "对比度增强",
        "description": "逐帧归一化后进行自适应直方图均衡。",
        "fields": [("clip_limit", "裁剪限制", 0.02)],
    },
    "display_adjustment": {
        "label": "显示调节",
        "description": (
            "仅调整预览和 AVI 导出的显示映射，不修改视频像素、ROI、dF/F 或后续预处理结果。"
            "阴影/高亮为显示百分位；亮度范围为 -100 至 100，对比范围为 0 至 300。"
        ),
        "fields": [
            ("shadows", "阴影 (%)", 1),
            ("highlights", "高亮 (%)", 99),
            ("brightness", "亮度 (-100 至 100)", 0),
            ("contrast", "对比 (0 至 300)", 100),
        ],
    },
    "detect_vessels": {
        "label": "检测血管/伪影",
        "description": "以红色蒙版预览可能的血管或伪影像素。",
        "fields": [("threshold", "阈值百分位", 90), ("alpha", "蒙版透明度", 0.45)],
    },
    "remove_vessel_artifact": {
        "label": "去除血管伪影",
        "description": "检测并抑制当前视频中的血管或伪影像素。",
        "fields": [("threshold", "阈值百分位", 90)],
    },
}


def preprocess_label(action_id: str) -> str:
    return PREPROCESS_PANEL_SPECS[action_id]["label"]
