import unittest
from pathlib import Path


class ChineseLocalizationTests(unittest.TestCase):
    def test_model_names_keep_original_name_and_add_chinese_function(self):
        import ui_text_zh as zh

        self.assertEqual(zh.MODEL_NAMES["deepcad_rt"], "DeepCAD-RT 深度学习降噪")
        self.assertEqual(zh.MODEL_NAMES["neuroseg3"], "NeuroSeg3 自动 ROI 分割")
        self.assertEqual(zh.MODEL_NAMES["neuroalign"], "NeuroAlign 脑图谱配准")

    def test_preprocess_actions_use_stable_ids_and_chinese_labels(self):
        import ui_text_zh as zh

        caiman = zh.PREPROCESS_PANEL_SPECS["caiman_motion"]
        self.assertEqual(caiman["label"], "CaImAn 运动矫正/去抖动")
        self.assertEqual(caiman["fields"][0][0], "mode")
        self.assertEqual(
            caiman["fields"][0][3],
            (("rigid", "仅刚性"), ("piecewise", "分块刚性")),
        )
        fast = zh.PREPROCESS_PANEL_SPECS["builtin_rigid_motion"]
        self.assertEqual(fast["label"], "快速运动矫正")
        self.assertIn("柔性强度为 0", fast["description"])
        self.assertIn("0.2-0.5", fast["description"])
        self.assertIn("CaImAn", fast["description"])

    def test_every_preprocess_action_has_a_unique_chinese_label(self):
        import ui_text_zh as zh

        labels = [spec["label"] for spec in zh.PREPROCESS_PANEL_SPECS.values()]
        self.assertEqual(len(labels), 12)
        self.assertEqual(len(labels), len(set(labels)))
        self.assertIn("自动裁剪无效边缘", labels)
        self.assertIn("显示调节", labels)
        self.assertTrue(
            all(any("\u4e00" <= char <= "\u9fff" for char in label) for label in labels)
        )

    def test_preprocess_buttons_route_by_internal_action_id(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        self.assertIn("for action_id, spec in PREPROCESS_PANEL_SPECS.items()", source)
        self.assertIn(
            "command=lambda key=action_id: self.show_preprocess_parameters(key)",
            source,
        )
        self.assertIn('if action_id == "caiman_motion"', source)
        self.assertIn('if action_id == "builtin_rigid_motion"', source)

    def test_parameter_choice_display_is_mapped_back_to_internal_value(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        self.assertIn("self.parameter_choice_values", source)
        self.assertIn("display_to_value", source)
        self.assertIn(
            "self.parameter_choice_values.get(key, {}).get(display_value, display_value)",
            source,
        )

    def test_main_tabs_and_primary_sections_are_chinese(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        for text in (
            'tabs.add(flow_tab, text="数据")',
            'tabs.add(pre_tab, text="预处理")',
            'tabs.add(roi_tab, text="ROI")',
            'tabs.add(analysis_tab, text="分析")',
            'text="运行日志"',
        ):
            self.assertIn(text, source)

    def test_sidebar_has_stable_width_and_uniform_button_style(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        self.assertIn("SIDEBAR_WIDTH = 300", source)
        self.assertIn("side.configure(width=SIDEBAR_WIDTH)", source)
        self.assertIn("side.grid_propagate(False)", source)
        self.assertIn('style.configure("Sidebar.TButton"', source)

    def test_major_dialogs_use_chinese_titles_and_commands(self):
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
            self.assertIn(text, source)

    def test_neuroalign_help_is_chinese_and_keeps_technical_names(self):
        help_text = Path("NeuroAlign_atlas_registration_help.txt").read_text(encoding="utf-8")
        self.assertIn("NeuroAlign 脑图谱配准帮助", help_text)
        self.assertIn("标准图谱构建", help_text)
        self.assertIn("外轮廓拟合", help_text)
        self.assertIn("Leiden 聚类", help_text)

    def test_runtime_messages_and_chart_titles_are_chinese(self):
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
            self.assertIn(text, source)

    def test_core_validation_errors_presented_to_users_are_chinese(self):
        source = Path("analysis_core.py").read_text(encoding="utf-8")
        self.assertIn("不支持的视频输出类型", source)
        self.assertIn("基线起始帧", source)
        self.assertIn("至少需要两条 ROI 曲线", source)


if __name__ == "__main__":
    unittest.main()
