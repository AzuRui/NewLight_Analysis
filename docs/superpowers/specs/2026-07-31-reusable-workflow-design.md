# Reusable Processing Workflow Design

Date: 2026-07-31

## Goal

Allow a user to save the reusable, parameterized processing steps shown in the
current-data task flow and apply the same ordered steps to any subsequently
loaded dataset, including after restarting NewLight_Analysis.

The saved file is a declarative JSON document, not executable Python. It never
contains movie data or fixed input/output paths.

## User Interface

The existing `当前数据任务流` panel remains below the parameter editor.

- Increase the task-list canvas height from 185 px to approximately 250 px.
- Add two equal-width buttons below the task list:
  - `保存当前工作流`
  - `执行工作流`
- Keep `取消当前任务` in the existing status row.
- Workflow steps continue to appear as ordinary entries in the existing FIFO
  task list; no second queue or modal progress window is introduced.

`保存当前工作流` opens a save-file dialog. `执行工作流` opens a workflow-file
dialog. These are file-path dialogs and therefore remain normal dialogs rather
than being embedded in the parameter panel.

## Supported Steps

Version 1 records all non-interactive preprocessing operations that replace or
modify the current movie:

1. `caiman_motion` - CaImAn motion correction
2. `builtin_rigid_motion` - fast rigid/optional flexible motion correction
3. `image_shift` - interlaced row-shift correction
4. `gaussian_smooth` - Gaussian smoothing
5. `median_filter` - median filtering
6. `background_subtract` - background subtraction
7. `bleach_correction` - photobleaching correction
8. `enhance_contrast` - contrast enhancement
9. `remove_vessel_artifact` - vessel/artifact suppression

The following are deliberately excluded:

- Data import, channel addition, save, and export operations because workflow
  files must not pin source or destination paths.
- Manual ROI drawing/deletion and interactive crop confirmation because their
  result depends on user interaction and dataset-specific coordinates.
- Preview-only actions, including display adjustment and vessel-mask preview.
- DeepCAD-RT in its current preview/cache form because it does not replace the
  current movie consumed by the next preprocessing task.
- ROI segmentation, peak detection, analysis windows, and analysis exports;
  the user invokes these after the reusable preprocessing workflow finishes.

## Task Metadata

`AppTask` gains an optional workflow-step descriptor. The application attaches
the descriptor at enqueue time rather than inferring it later from translated
labels or Python closures.

Each descriptor contains only JSON-compatible values:

```json
{
  "function": "gaussian_smooth",
  "name": "高斯平滑",
  "parameters": {
    "sigma": "1.0"
  }
}
```

The descriptor stores the submitted parameters that produce the operation.
Parameter validation remains in the same execution functions used by manual
UI operation, preventing workflow execution from developing separate numeric
semantics.

## File Format

The suggested extension is `.nlworkflow.json`. Version 1 has this shape:

```json
{
  "format": "NewLight Workflow",
  "version": 1,
  "created_at": "2026-07-31T12:00:00+08:00",
  "application": "NewLight_Analysis",
  "steps": [
    {
      "function": "gaussian_smooth",
      "name": "高斯平滑",
      "parameters": {"sigma": "1.0"}
    }
  ]
}
```

The loader rejects a wrong format marker, unsupported version, empty or
non-list steps, unknown function IDs, non-object parameter values, and
non-JSON-compatible nested values. User-facing errors identify the invalid
step number and reason.

## Saving

The save action reads `TaskController.history` in submission order.

- Include supported tasks in `COMPLETED`, `RUNNING`, or `QUEUED` state.
- Preserve repeated operations and their exact order.
- Skip unsupported tasks and tasks in `FAILED`, `CANCELLED`, or `CANCELLING`
  state.
- Refuse to write an empty workflow and explain that no reusable processing
  steps exist in the current task flow.
- Log the output path, saved step count, and skipped count.
- Use structured JSON serialization with UTF-8 and visible Chinese names.

The workflow describes intended processing, not captured pixel data. Saving a
currently running or queued supported task is valid because its function and
parameters were already fixed at enqueue time.

## Execution

The execute action requires a currently loaded movie, then asks for a workflow
file and validates the complete document before queueing any step.

Every step calls the same `run_preprocess_action(function, parameters)` route
used by the UI. Steps are submitted to the existing single-worker FIFO queue,
so each operation starts only after the previous operation's completion
callback has applied its new movie to application state.

A workflow run receives a unique run identifier:

- If one workflow task fails, is cancelled, or is cancelling, remaining tasks
  from that run skip execution and become cancelled.
- Unrelated manual tasks already in the FIFO queue are not removed.
- The final successful step logs workflow completion.
- Executed workflow steps retain their descriptors, so the resulting current
  task flow can itself be saved again.

## Architecture

Add a small backend-independent workflow module responsible for:

- Constants for format/version and supported function IDs.
- Normalizing and validating one step.
- Building a document from task descriptors.
- Loading and saving UTF-8 JSON.

The module must not import Tk, movie arrays, model backends, or
`NewLight_Analysis.py`. This keeps file compatibility and validation directly
unit-testable.

Application responsibilities are limited to:

- Rendering buttons and the larger task panel.
- Supplying workflow metadata when supported tasks are enqueued.
- Selecting files through Tk dialogs.
- Mapping validated function IDs back to `run_preprocess_action`.
- Tracking workflow-run failure/cancellation state around the existing FIFO.

## Error Handling

- Invalid files are rejected before any processing task is queued.
- Unsupported future-version files show the supported version.
- Missing current data shows the existing no-movie warning and does not open a
  partially runnable workflow.
- A step runtime failure is shown through the existing background-task error
  route and prevents later steps in the same workflow from touching data.
- Saving uses normal filesystem exceptions and reports a concise path-specific
  message without modifying the current task flow.

## Testing

Automated coverage must include:

- JSON round trip with Chinese labels and ordered duplicate steps.
- Invalid format, version, function, parameter object, and empty workflow.
- History filtering by task state and supported descriptor.
- UI button placement below the enlarged task canvas.
- Exact parameter capture for every supported action ID.
- Replaying steps in FIFO order against the movie produced by the prior step.
- Failure/cancellation causing later steps in the same workflow to skip.
- Unrelated non-workflow tasks remaining unaffected.
- Real Tk smoke for save-dialog routing, execute-dialog routing, and visible
  task-flow buttons without layout overlap.

## Manual And Documentation Requirements

Record the implementation and verification in `WORK_LOG.md` and
`PROJECT_HANDOFF.md`. The future detailed user manual must document:

- The location and purpose of both workflow buttons.
- Which operations are supported and excluded.
- How to save a workflow after manually building a processing sequence.
- How to load new data and execute a saved workflow.
- FIFO order, stop-on-failure behavior, and cancellation behavior.
- The JSON schema with a readable example.
- Version compatibility and the fact that workflows do not contain source
  videos, output paths, ROI drawings, or analysis results.

## Compatibility

The initial format version is 1. Future capabilities must add compatible fields
or introduce a new version with explicit migration. Existing version-1 files
must remain executable as long as their function IDs remain supported.
