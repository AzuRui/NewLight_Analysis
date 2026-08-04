import json

import pytest

import workflow_core as workflow


def test_workflow_round_trip_preserves_chinese_order_and_duplicates(tmp_path):
    steps = [
        {"function": "gaussian_smooth", "name": "高斯平滑", "parameters": {"sigma": "1.2"}},
        {"function": "gaussian_smooth", "name": "高斯平滑", "parameters": {"sigma": "2.0"}},
    ]
    path = tmp_path / "repeat.nlworkflow.json"

    workflow.save_workflow(path, steps, created_at="2026-07-31T12:00:00+08:00")
    document = workflow.load_workflow(path)

    assert document["steps"] == steps
    assert document["format"] == "NewLight Workflow"
    assert document["version"] == 1
    assert "高斯平滑" in path.read_text(encoding="utf-8")


def test_workflow_v1_supports_loading_roi_files():
    assert "load_roi" in workflow.SUPPORTED_FUNCTIONS
    document = workflow.build_document(
        [
            {
                "function": "load_roi",
                "name": "载入 ROI",
                "parameters": {"path": "C:/data/rois.npz", "format": "npz"},
            }
        ]
    )
    assert document["steps"][0]["function"] == "load_roi"


@pytest.mark.parametrize(
    "document, message",
    [
        ({"format": "wrong", "version": 1, "steps": [{}]}, "format"),
        ({"format": "NewLight Workflow", "version": 2, "steps": [{}]}, "version"),
        ({"format": "NewLight Workflow", "version": 1, "steps": []}, "step"),
        (
            {"format": "NewLight Workflow", "version": 1, "steps": [{"function": "unknown", "parameters": {}}]},
            "function",
        ),
        (
            {
                "format": "NewLight Workflow",
                "version": 1,
                "steps": [{"function": "gaussian_smooth", "parameters": []}],
            },
            "parameters",
        ),
    ],
)
def test_invalid_workflow_documents_are_rejected(document, message, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(workflow.WorkflowValidationError, match=message):
        workflow.load_workflow(path)


def test_non_json_parameter_values_are_rejected():
    with pytest.raises(workflow.WorkflowValidationError, match="JSON"):
        workflow.build_document(
            [{"function": "gaussian_smooth", "name": "高斯平滑", "parameters": {"sigma": object()}}]
        )
