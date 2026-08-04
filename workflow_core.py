"""Versioned, declarative processing workflow files for NewLight_Analysis."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path


FORMAT_NAME = "NewLight Workflow"
FORMAT_VERSION = 1
APPLICATION_NAME = "NewLight_Analysis"
SUPPORTED_FUNCTIONS = frozenset(
    {
        "caiman_motion",
        "builtin_rigid_motion",
        "image_shift",
        "gaussian_smooth",
        "median_filter",
        "background_subtract",
        "bleach_correction",
        "enhance_contrast",
        "remove_vessel_artifact",
        "load_roi",
    }
)


class WorkflowValidationError(ValueError):
    """Raised when a workflow document cannot be executed safely."""


def normalize_step(step, index):
    if not isinstance(step, dict):
        raise WorkflowValidationError(f"step {index}: must be an object")
    function = str(step.get("function", ""))
    if function not in SUPPORTED_FUNCTIONS:
        raise WorkflowValidationError(f"step {index}: unsupported function {function!r}")
    parameters = step.get("parameters", {})
    if not isinstance(parameters, dict):
        raise WorkflowValidationError(f"step {index}: parameters must be an object")
    normalized = {
        "function": function,
        "name": str(step.get("name", function)),
        "parameters": dict(parameters),
    }
    try:
        json.dumps(normalized, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise WorkflowValidationError(f"step {index}: parameters are not JSON-compatible") from exc
    return normalized


def build_document(steps, created_at=None):
    normalized = [normalize_step(step, index) for index, step in enumerate(steps, 1)]
    if not normalized:
        raise WorkflowValidationError("workflow must contain at least one step")
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "application": APPLICATION_NAME,
        "steps": normalized,
    }


def validate_document(document):
    if not isinstance(document, dict):
        raise WorkflowValidationError("workflow document must be an object")
    if document.get("format") != FORMAT_NAME:
        raise WorkflowValidationError(f"unsupported workflow format: {document.get('format')!r}")
    if document.get("version") != FORMAT_VERSION:
        raise WorkflowValidationError(
            f"unsupported workflow version: {document.get('version')!r}; supported version is {FORMAT_VERSION}"
        )
    steps = document.get("steps")
    if not isinstance(steps, list) or not steps:
        raise WorkflowValidationError("workflow steps must be a non-empty list")
    normalized_steps = [normalize_step(step, index) for index, step in enumerate(steps, 1)]
    if document.get("application") != APPLICATION_NAME:
        raise WorkflowValidationError(f"unsupported workflow application: {document.get('application')!r}")
    created_at = document.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        raise WorkflowValidationError("workflow created_at must be a non-empty string")
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "created_at": created_at,
        "application": APPLICATION_NAME,
        "steps": normalized_steps,
    }


def load_workflow(path):
    with Path(path).open("r", encoding="utf-8") as handle:
        document = json.load(handle)
    return validate_document(document)


def save_workflow(path, steps, created_at=None):
    document = build_document(steps, created_at=created_at)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return document
