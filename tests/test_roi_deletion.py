from unittest import mock

import numpy as np

import analysis_core as core
from NewLight_Analysis import NewLightApp


def app_with_rois(names, metadata=None):
    app = object.__new__(NewLightApp)
    app.state = core.AnalysisState()
    app.state.roi_masks = []
    for index in range(len(names)):
        mask = np.zeros((3, max(3, len(names))), dtype=bool)
        mask[0, index] = True
        app.state.roi_masks.append(mask)
    app.state.roi_names = list(names)
    app.state.roi_metadata = list(metadata or ({"source": "atlas", "base_name": name} for name in names))
    app.state.traces = np.ones((4, len(names)), dtype=np.float32)
    app.redraw = mock.Mock()
    app.log = mock.Mock()
    app.refresh_roi_list_if_visible = mock.Mock()
    return app


def test_deleting_first_generated_roi_shifts_following_sequence_and_preserves_quality():
    app = app_with_rois(
        ["AtlasROI1", "AtlasROI2", "AtlasROI3*"],
        [
            {"source": "atlas", "base_name": "AtlasROI1"},
            {"source": "atlas", "base_name": "AtlasROI2"},
            {"source": "atlas", "base_name": "AtlasROI3", "low_quality": True},
        ],
    )
    revision = app.state.roi_revision

    app.delete_roi_at(0, 0)

    assert app.state.roi_names == ["AtlasROI1", "AtlasROI2*"]
    assert [item["base_name"] for item in app.state.roi_metadata] == ["AtlasROI1", "AtlasROI2"]
    assert app.state.roi_metadata[1]["low_quality"] is True
    assert app.state.roi_revision == revision + 1
    assert app.state.traces is None


def test_deleting_middle_generated_roi_closes_only_that_sequence_gap():
    app = app_with_rois(["Fast_ROI1", "Fast_ROI2", "Fast_ROI3", "Fast_ROI4"])

    app.delete_roi_at(1, 0)

    assert app.state.roi_names == ["Fast_ROI1", "Fast_ROI2", "Fast_ROI3"]


def test_deleting_custom_name_does_not_rename_remaining_generated_or_custom_names():
    app = app_with_rois(["Region-A", "AtlasROI7", "VisualArea2026"])

    app.delete_roi_at(0, 0)

    assert app.state.roi_names == ["AtlasROI7", "VisualArea2026"]
