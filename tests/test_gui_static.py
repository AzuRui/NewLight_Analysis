import unittest
from pathlib import Path


class GuiStaticTests(unittest.TestCase):
    def test_preprocess_tab_exposes_image_shift_button(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        labels = Path("ui_text_zh.py").read_text(encoding="utf-8")

        self.assertIn('"image_shift"', labels)
        self.assertIn('"builtin_rigid_motion"', labels)
        self.assertLess(
            labels.index('"builtin_rigid_motion"'),
            labels.index('"image_shift"'),
        )

    def test_main_surfaces_render_background_image_themselves(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("side = ui_background.BackgroundPane", source)
        self.assertIn("main = ui_background.BackgroundPane", source)

    def test_empty_preview_draws_window_background(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("def draw_empty_preview_background", source)
        self.assertIn("self.draw_empty_preview_background()", source)
        self.assertIn("self.redraw(preserve_view=False)", source)

    def test_logo_starfield_uses_small_quiet_points(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("for _ in range(24):", source)
        self.assertIn('"r": rng.choice([0.45, 0.55, 0.65])', source)
        self.assertNotIn('r = s["r"] + (1 if pulse > 0.96 else 0)', source)

    def test_data_tab_exposes_import_depth_selector(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("self.movie_import_depth_var", source)
        self.assertIn("导入位深", source)
        self.assertIn("import_depth = self.import_bit_depth()", source)
        self.assertIn("bit_depth=import_depth", source)

    def test_main_layout_has_parameter_side_panel(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn('self.parameter_panel = ttk.LabelFrame(main, text="参数"', source)
        self.assertIn("main.columnconfigure(0, minsize=PARAM_PANEL_WIDTH)", source)
        self.assertIn("main.columnconfigure(1, weight=1)", source)
        self.assertIn('self.canvas.get_tk_widget().grid(row=0, column=1', source)
        self.assertIn("log_box.grid(row=4, column=1", source)

    def test_parameter_panel_has_an_independent_vertical_scrollbar(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("self.parameter_scroll_canvas = tk.Canvas(", source)
        self.assertIn("self.parameter_scrollbar = ttk.Scrollbar(", source)
        self.assertIn("command=self.parameter_scroll_canvas.yview", source)
        self.assertIn("yscrollcommand=self.parameter_scrollbar.set", source)
        self.assertIn("def _on_parameter_mousewheel", source)
        self.assertIn("def _reset_parameter_scroll_position", source)
        self.assertIn("self._reset_parameter_scroll_position()", source)

    def test_parameter_panel_supports_embedded_paths_checkboxes_and_actions(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def show_parameter_panel(")
        end = source.index("    def reset_parameter_panel", start)
        method = source[start:end]

        self.assertIn('field_type == "checkbox"', method)
        self.assertIn('field_type == "action"', method)
        self.assertIn('field_type == "buttons"', method)
        self.assertIn("_browse_parameter_path", method)
        self.assertIn('text="浏览"', method)

    def test_configuration_entry_points_do_not_open_legacy_toplevel_dialogs(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        def method(name, next_name):
            start = source.index(f"    def {name}(")
            end = source.index(f"    def {next_name}(", start)
            return source[start:end]

        self.assertIn("self._show_source_picker_panel", method("open_movie", "add_channel_data"))
        self.assertNotIn("SourcePickerDialog", method("open_movie", "add_channel_data"))
        self.assertIn("self.show_parameter_panel", method("atlas_reference_builder", "_run_atlas_reference_builder_from_panel"))
        self.assertNotIn("AtlasReferenceBuilderDialog", method("atlas_reference_builder", "_run_atlas_reference_builder_from_panel"))
        self.assertIn("self._show_neuroalign_panel", method("neuroalign", "_neuroalign_stage_fields"))
        self.assertNotIn("NeuroAlignWizard", method("neuroalign", "_neuroalign_stage_fields"))
        self.assertIn("self.show_parameter_panel", method("auto_roi", "_auto_roi_use_current_samples"))
        self.assertNotIn("BuiltInAutoROIDialog", method("auto_roi", "_auto_roi_use_current_samples"))
        self.assertIn("self.show_parameter_panel", method("neuroseg3_roi", "_run_neuroseg3_from_panel"))
        self.assertNotIn("NeuroSeg3Dialog", method("neuroseg3_roi", "_run_neuroseg3_from_panel"))
        self.assertIn("self._show_heatmap_video_panel", method("generate_heatmap_avi", "_show_heatmap_video_panel"))
        self.assertNotIn("HeatmapVideoDialog", method("generate_heatmap_avi", "_show_heatmap_video_panel"))

    def test_preprocess_buttons_use_embedded_parameter_panel(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("PREPROCESS_PANEL_SPECS", source)
        self.assertIn("self.show_preprocess_parameters", source)
        self.assertIn("def show_parameter_panel", source)
        self.assertIn("def run_parameter_action", source)

    def test_comboboxes_match_the_transparent_panel_background(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn('"TCombobox"', source)
        self.assertIn('fieldbackground=THEME["panel"]', source)
        self.assertIn('fieldbackground=[("readonly", THEME["panel"])', source)
        self.assertIn('"*TCombobox*Listbox.background"', source)

    def test_caiman_mode_is_a_readonly_choice(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        labels = Path("ui_text_zh.py").read_text(encoding="utf-8")

        self.assertIn('("mode", "模式", "piecewise"', labels)
        self.assertIn('("max_shift", "最大整体位移 (px)", 12)', labels)
        self.assertIn('("stride", "Patch 步长 (px)", 48)', labels)
        self.assertIn('("overlap", "Patch 重叠 (px)", 24)', labels)
        self.assertIn('("max_deviation", "最大局部偏差 (px)", 5)', labels)
        self.assertIn("ttk.Combobox", source)
        self.assertIn('state="readonly"', source)
        self.assertIn("max_shift=max_shift", source)
        self.assertIn("stride=stride", source)
        self.assertIn("overlap=overlap", source)
        self.assertIn("max_deviation=max_deviation", source)

    def test_fast_motion_exposes_rigid_and_flexible_controls(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        labels = Path("ui_text_zh.py").read_text(encoding="utf-8")

        self.assertIn('"label": "快速运动矫正"', labels)
        self.assertIn('("reference_mode", "参考帧模式", "auto"', labels)
        self.assertIn('("reference_start", "参考起始帧", 0)', labels)
        self.assertIn('("reference_frames", "参考帧数量", 100)', labels)
        self.assertIn('("max_shift", "最大刚性位移 (px)", 15)', labels)
        self.assertIn('("flexible_strength", "柔性强度 (0=关闭)", 0.0)', labels)
        self.assertIn('("local_block_size", "局部块尺寸 (px)", 96)', labels)
        self.assertIn('("max_local_deformation", "最大局部形变 (px)", 3.0)', labels)
        self.assertIn("0.2-0.5", labels)
        self.assertIn("CaImAn", labels)
        self.assertIn("core.fast_motion_correction(", source)
        self.assertIn("reference_mode=reference_mode", source)
        self.assertIn("reference_start=reference_start", source)
        self.assertIn("reference_frames=reference_frames", source)
        self.assertIn("max_shift=max_shift", source)
        self.assertIn("flexible_strength=flexible_strength", source)
        self.assertIn("local_block_size=local_block_size", source)
        self.assertIn("max_local_deformation=max_local_deformation", source)
        self.assertIn("info['reference_start']", source)

    def test_caiman_completion_is_described_as_temporary_preview(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("CaImAn 结果已载入当前临时预览", source)
        self.assertIn("clean_backend_log(log)", source)
        self.assertIn("previous_source = self.display_source", source)
        self.assertIn('if previous_source[0] == "frame":', source)
        self.assertIn("self.show_frame(previous_source[1])", source)
        self.assertIn("CaImAn 临时预览文件：", source)

    def test_trial_average_uses_the_task_queue(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def show_trial_average(self):")
        end = source.index("    def peak_detection(self):", start)
        method = source[start:end]

        self.assertIn('self.enqueue_task("计算试次平均", worker, finish)', method)
        self.assertIn("core.detect_stimulus_triggers(", method)
        self.assertIn("core.extract_traces(", method)
        self.assertIn("core.trial_average(", method)
        self.assertNotIn("self.extract_traces()", method)
        self.assertNotIn("self.detect_triggers()", method)

    def test_roi_interaction_uses_the_active_view_projection(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def on_mode_changed(self):")
        end = source.index("    @staticmethod\n    def view_label", start)
        method = source[start:end]

        self.assertIn('self.projection_mode.get()', method)
        self.assertIn('self.queue_movie_view_refresh("切换 ROI 交互视图", preserve_view=True, on_complete=ready)', method)
        self.assertIn('self.roi_view_refresh_pending = True', method)
        self.assertNotIn('self.projection_mode.set("mean")', method)
        self.assertNotIn("self.show_frame(", method)

    def test_protocol_exposes_invalid_start_frames_and_wires_analysis(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        core_source = Path("analysis_core.py").read_text(encoding="utf-8")

        self.assertIn('self.invalid_start_frames_var = tk.StringVar(value="0")', source)
        self.assertIn('("无效起始帧数", self.invalid_start_frames_var)', source)
        self.assertIn("invalid_start_frames: int = 0", core_source)
        self.assertIn("self.state.invalid_start_frames = invalid_start_frames", source)
        self.assertIn("invalid_start_frames=self.state.invalid_start_frames", source)

    def test_deepcad_cache_and_both_run_paths_include_invalid_start_frames(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("self.deepcad_cache_invalid_start_frames", source)
        self.assertGreaterEqual(source.count("invalid_start_frames=invalid_start_frames"), 2)

    def test_protocol_log_reports_effective_baseline_start(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("effective_baseline_start = max(", source)
        self.assertIn("f\"dF/F 基线使用第 {effective_baseline_start}-{end_frame} 帧的均值。\"", source)

    def test_roi_sidebar_uses_caiman_and_authorized_fast_engines_only(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        labels = Path("ui_text_zh.py").read_text(encoding="utf-8")
        start = source.index('roi_box = ttk.LabelFrame(roi_tab, text="ROI 工具"')
        end = source.index('analysis_box = ttk.LabelFrame(analysis_tab, text="分析"', start)
        sidebar = source[start:end]

        self.assertIn('"caiman_roi": "CaImAn 识别分割"', labels)
        self.assertIn('"fast_roi": "快速 ROI 分割"', labels)
        self.assertIn('command=self.caiman_roi', sidebar)
        self.assertIn('command=self.fast_roi', sidebar)
        self.assertNotIn('command=self.neuroseg3_roi', sidebar)
        self.assertNotIn('command=self.auto_roi', sidebar)

    def test_new_roi_engines_use_embedded_parameters_persistence_and_fifo(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        caiman_start = source.index("    def caiman_roi(self):")
        fast_start = source.index("    def fast_roi(self):", caiman_start)
        legacy_start = source.index("    def auto_roi(self):", fast_start)
        caiman_methods = source[caiman_start:fast_start]
        fast_methods = source[fast_start:legacy_start]

        self.assertIn("self.show_parameter_panel", caiman_methods)
        self.assertIn('self.user_settings.get("caiman_roi"', caiman_methods)
        self.assertIn('self.user_settings["caiman_roi"]', caiman_methods)
        self.assertIn('self.enqueue_task(MODEL_NAMES["caiman_roi"]', caiman_methods)
        self.assertIn("core.run_caiman_roi_segmentation(", caiman_methods)
        self.assertIn("if result.masks.shape[0] == 0:", caiman_methods)
        self.assertIn("self.set_rois(result.masks", caiman_methods)

        self.assertIn("self.show_parameter_panel", fast_methods)
        self.assertIn('self.user_settings.get("fast_roi"', fast_methods)
        self.assertIn('self.user_settings["fast_roi"]', fast_methods)
        self.assertIn('self.enqueue_task(MODEL_NAMES["fast_roi"]', fast_methods)
        self.assertIn("core.compute_projection(", fast_methods)
        self.assertIn("core.run_fast_roi_segmentation(", fast_methods)
        self.assertIn("if result.masks.shape[0] == 0:", fast_methods)
        self.assertIn("self.set_rois(result.masks", fast_methods)

    def test_roi_engines_expose_quality_presets_and_adaptive_actions(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        caiman_start = source.index("    def caiman_roi(self):")
        fast_start = source.index("    def fast_roi(self):", caiman_start)
        legacy_start = source.index("    def auto_roi(self):", fast_start)
        caiman_methods = source[caiman_start:fast_start]
        fast_methods = source[fast_start:legacy_start]

        for methods in (caiman_methods, fast_methods):
            self.assertIn('"quality_preset"', methods)
            self.assertIn('("recall", "高召回")', methods)
            self.assertIn('("balanced", "均衡")', methods)
            self.assertIn('("precision", "高精度")', methods)
            self.assertIn('("custom", "自定义")', methods)
            self.assertIn("根据当前 ROI 自适应拟合并运行", methods)
            self.assertIn("不训练或修改模型权重", methods)
        self.assertIn("从当前 ROI 填入面积", fast_methods)

    def test_adaptive_roi_uses_separate_banks_signatures_and_stale_guards(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn('self.roi_candidate_banks = {"fast": None, "caiman": None}', source)
        self.assertIn("self.movie_generation = 0", source)
        self.assertIn("def mark_movie_changed(self):", source)
        self.assertGreaterEqual(source.count("self.mark_movie_changed()"), 8)
        self.assertIn("roi_fit.candidate_source_signature(", source)
        self.assertIn("roi_fit.adaptive_result_is_current(", source)
        self.assertIn("source_roi_revision = int(self.state.roi_revision)", source)
        self.assertIn("candidate_mode=True", source)
        self.assertIn("self.roi_candidate_banks[engine]", source)

    def test_fast_roi_cache_identity_includes_runtime_code_and_dependencies(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def _roi_model_identity(engine):")
        end = source.index("    @staticmethod\n    def _candidate_bank_from_result", start)
        method = source[start:end]

        self.assertIn("core.NEUSUITE_DEFAULT_WEIGHTS", method)
        self.assertIn("core.NEUSUITE_RUNTIME_ROOT", method)
        self.assertIn('core.PROJECT_DIR / "NeuSuite_RuntimeDeps"', method)
        self.assertIn("_roi_path_identity", method)
        self.assertIn("core.caiman_worker_environment()", method)
        self.assertIn("core.resolve_conda_environment_prefix", method)
        self.assertIn("core.CAIMAN_RESOURCE_DIR", method)

    def test_roi_name_sync_preserves_existing_base_identity(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def sync_roi_names(self):")
        end = source.index("    def set_rois", start)
        method = source[start:end]

        self.assertNotIn('item["base_name"] = f"ROI{index + 1}"', method)
        self.assertIn("self.next_roi_base_name", method)

    def test_automatic_global_roi_uses_revision_incrementing_mutation_path(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("def ensure_global_roi(self):", source)
        self.assertIn('self.set_rois([full_roi], source="全局 ROI"', source)
        self.assertNotIn("self.state.roi_masks = [full_roi]", source)
        self.assertNotIn("self.state.roi_masks = [np.ones(self.state.movie.shape[1:], dtype=bool)]", source)

    def test_parameter_choices_support_selection_callbacks_for_presets(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def show_parameter_panel(")
        end = source.index("    def reset_parameter_panel", start)
        method = source[start:end]

        self.assertIn('entry.bind("<<ComboboxSelected>>"', method)
        self.assertIn('spec.get("on_change")', method)

    def test_roi_toolbar_exposes_embedded_roi_list(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn('text="显示 ROI 列表", command=self.show_roi_list', source)
        start = source.index("    def show_roi_list(self):")
        end = source.index("    def refresh_roi_list_if_visible", start)
        method = source[start:end]
        self.assertIn("self.show_parameter_panel", method)
        self.assertIn('"type": "roi_table"', method)
        self.assertIn("core.roi_color_hex(index)", method)
        self.assertIn("np.count_nonzero(mask)", method)

    def test_parameter_panel_supports_roi_color_table(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        start = source.index("    def show_parameter_panel(")
        end = source.index("    def reset_parameter_panel", start)
        method = source[start:end]

        self.assertIn('field_type == "roi_table"', method)
        self.assertIn('columns=("roi", "area", "quality")', method)
        self.assertIn('text="颜色"', method)
        self.assertIn('text="ROI"', method)
        self.assertIn('text="面积 (px^2)"', method)

    def test_roi_table_selection_highlights_the_corresponding_overlay(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        panel_start = source.index("    def show_parameter_panel(")
        reset_start = source.index("    def reset_parameter_panel", panel_start)
        panel = source[panel_start:reset_start]
        select_start = source.index("    def select_roi_from_list(")
        refresh_start = source.index("    def refresh_roi_list_if_visible", select_start)
        selection = source[select_start:refresh_start]
        redraw_start = source.index("    def redraw(")
        empty_start = source.index("    def draw_empty_preview_background", redraw_start)
        redraw = source[redraw_start:empty_start]

        self.assertIn('table.bind("<<TreeviewSelect>>"', panel)
        self.assertIn('iid=f"roi_{roi_row[\'index\']}"', panel)
        self.assertIn('"on_select": self.select_roi_from_list', source)
        self.assertIn("self.highlighted_roi_index = index", selection)
        self.assertNotIn("self.root.after", selection)
        self.assertNotIn("roi_highlight_flash_on", source)
        self.assertNotIn("_advance_roi_highlight_flash", source)
        self.assertIn("highlighted_index=self.highlighted_roi_index", redraw)

    def test_roi_list_refreshes_after_roi_mutations(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")

        self.assertIn("self.active_parameter_panel_id = None", source)
        self.assertIn('panel_id="roi_list"', source)
        self.assertIn('if self.active_parameter_panel_id == "roi_list":', source)
        set_rois_start = source.index("    def set_rois(")
        mark_start = source.index("    def mark_rois_changed", set_rois_start)
        clear_start = source.index("    def clear_rois", mark_start)
        load_start = source.index("    def load_roi", clear_start)
        self.assertIn("self.refresh_roi_list_if_visible()", source[set_rois_start:mark_start])
        self.assertIn("self.refresh_roi_list_if_visible()", source[mark_start:clear_start])
        self.assertIn("self.refresh_roi_list_if_visible()", source[clear_start:load_start])

    def test_gui_trace_views_use_shared_roi_colors(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        trace_start = source.index("    def show_trace_window(self, traces):")
        trial_start = source.index("    def show_trial_average(self):", trace_start)
        trial_window_start = source.index("    def _show_trial_average_window", trial_start)
        peak_start = source.index("    def peak_detection", trial_window_start)

        self.assertIn("color=core.roi_color_hex(i)", source[trace_start:trial_start])
        self.assertIn("color=core.roi_color_hex(i)", source[trial_window_start:peak_start])

    def test_roi_state_mutations_keep_metadata_and_revision_aligned(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        set_start = source.index("    def set_rois(")
        recompute_start = source.index("    def recompute_baseline_image", set_start)
        mutation_methods = source[set_start:recompute_start]
        add_start = source.index("    def add_roi(")
        load_start = source.index("    def load_roi", add_start)
        drawing_methods = source[add_start:load_start]

        self.assertIn("metadata=None", mutation_methods)
        self.assertIn("self.state.roi_metadata", mutation_methods)
        self.assertIn("self.state.roi_revision += 1", mutation_methods)
        self.assertIn('"source": "manual"', drawing_methods)
        self.assertGreaterEqual(drawing_methods.count("self.state.roi_metadata.pop"), 2)
        self.assertIn("self.state.roi_metadata = []", drawing_methods)

    def test_roi_npz_persists_metadata_and_loads_legacy_files(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        load_start = source.index("    def load_roi(self):")
        atlas_start = source.index("    def atlas_roi", load_start)
        save_start = source.index("    def save_roi(self):")
        defaults_start = source.index("    def current_movie_result_defaults", save_start)

        self.assertIn("deserialize_roi_metadata", source[load_start:atlas_start])
        self.assertIn('"metadata_json" in data', source[load_start:atlas_start])
        self.assertIn("serialize_roi_metadata", source[save_start:defaults_start])
        self.assertIn("metadata_json=metadata_json", source[save_start:defaults_start])

    def test_roi_list_displays_quality_status_and_star_help(self):
        source = Path("NewLight_Analysis.py").read_text(encoding="utf-8")
        show_start = source.index("    def show_roi_list(self):")
        refresh_start = source.index("    def refresh_roi_list_if_visible", show_start)
        method = source[show_start:refresh_start]
        panel_start = source.index("    def show_parameter_panel(")
        reset_start = source.index("    def reset_parameter_panel", panel_start)
        panel = source[panel_start:reset_start]

        self.assertIn('"quality":', method)
        self.assertIn("低质量*", method)
        self.assertIn('columns=("roi", "area", "quality")', panel)
        self.assertIn('text="质量"', panel)
        self.assertIn("名称末尾的 * 表示", method)


if __name__ == "__main__":
    unittest.main()
