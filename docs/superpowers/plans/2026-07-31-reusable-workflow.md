# Reusable Processing Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Save supported parameterized preprocessing tasks from the current-data FIFO history as a versioned JSON workflow and replay them in order on any currently loaded dataset.

**Architecture:** Add a Tk-independent workflow_core.py for schema validation and JSON I/O. Extend AppTask with workflow metadata, then let NewLightApp collect descriptors, replay validated steps through run_preprocess_action, and use a workflow-run ID to cancel remaining queued steps after failure or cancellation.

**Tech Stack:** Python 3.11, dataclasses, JSON, pathlib, Tk/ttk, existing TaskController, pytest/unittest.

---

## File Map

- Create workflow_core.py: format/version constants, supported IDs, document validation, UTF-8 load/save.
- Create tests/test_workflow_core.py: schema, round-trip, ordering, and invalid-document tests.
- Modify task_queue.py: optional workflow descriptor and run ID on AppTask and enqueue_task.
- Modify tests/test_task_queue.py: metadata preservation and workflow-run identity tests.
- Modify NewLight_Analysis.py: UI buttons, history collection, dialogs, replay, failure propagation, and descriptor capture for nine preprocessing actions.
- Create tests/test_workflow_gui.py: history filtering, replay ordering, parameter capture, and failure-stop behavior.
- Modify tests/test_gui_static.py: larger task panel and exact button placement.
- Modify WORK_LOG.md and PROJECT_HANDOFF.md: implementation, usage contract, verification, and manual requirements.

## Task 1: Workflow JSON Core

Files: create workflow_core.py and tests/test_workflow_core.py.

- [ ] Write failing tests for JSON round-trip with Chinese labels, duplicate ordered steps, wrong format, unsupported version, empty steps, unknown function, non-object parameters, and non-JSON values.
- [ ] Run: $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; .\.conda_envs\newlight_caiman\python.exe -m pytest tests\test_workflow_core.py -q. Expected RED because workflow_core.py does not exist.
- [ ] Implement FORMAT_NAME='NewLight Workflow', FORMAT_VERSION=1, and SUPPORTED_FUNCTIONS containing caiman_motion, builtin_rigid_motion, image_shift, gaussian_smooth, median_filter, background_subtract, bleach_correction, enhance_contrast, and remove_vessel_artifact.
- [ ] Implement WorkflowValidationError, normalize_step(step, index), validate_document(document), build_document(steps, created_at=None), load_workflow(path), and save_workflow(path, steps, created_at=None). Validate dictionaries, supported function IDs, non-empty steps, JSON-compatible parameters, application marker, version, and UTF-8 indented ensure_ascii=False output.
- [ ] Run the focused tests and verify GREEN.

## Task 2: Attach Metadata To FIFO Tasks

Files: modify task_queue.py and tests/test_task_queue.py.

- [ ] Write a failing test that enqueues a task with a descriptor, workflow_run_id='run-1', and workflow_is_last=True, then asserts all three fields are preserved.
- [ ] Run tests/test_task_queue.py and verify the new keyword arguments fail.
- [ ] Add optional workflow_step, workflow_run_id, and workflow_is_last fields to AppTask. Add matching keyword-only arguments to TaskController.enqueue_task and copy the descriptor before storing it.
- [ ] Run all task queue tests and verify no existing FIFO behavior changes.

## Task 3: Capture Supported Preprocessing Parameters

Files: modify NewLight_Analysis.py and create tests/test_workflow_gui.py.

- [ ] Write failing capture tests for every function in workflow_core.SUPPORTED_FUNCTIONS. Mock the application enqueue path and assert the task descriptor contains function, translated name, and submitted parameters.
- [ ] Run capture tests and verify tasks currently have no workflow_step.
- [ ] Change run_preprocess_action(self, action_id, values, workflow_run_id=None, workflow_is_last=False) and create a descriptor for supported action IDs.
- [ ] Thread workflow_step, workflow_run_id, and workflow_is_last through apply_movie_operation, run_caiman_motion_from_values, run_image_shift_from_values, and run_remove_vessels_from_values. Return the resulting AppTask from each supported branch. Existing manual calls use None defaults.
- [ ] Extend NewLightApp.enqueue_task with the same metadata arguments and pass them into TaskController.enqueue_task.
- [ ] Run capture tests plus rigid motion, CaImAn motion, and task queue tests.

## Task 4: Workflow Run Failure Propagation

Files: modify NewLight_Analysis.py and tests/test_workflow_gui.py.

- [ ] Write a failing FIFO test with three same-run tasks where the first worker fails; assert second and third become cancelled without touching their worker bodies.
- [ ] Add self.workflow_runs = {} during NewLightApp initialization.
- [ ] Wrap a workflow worker so it raises TaskCancelled before work when its run status is not running. Set status to failed on the first run error, cancelled on user cancellation, and completed after the last success. Later skipped cancellations must not replace failed with cancelled.
- [ ] Run failure/cancellation tests and verify unrelated manual tasks are unaffected.

## Task 5: Save Current Workflow

Files: modify NewLight_Analysis.py and tests/test_workflow_gui.py.

- [ ] Write a failing test with completed, running, queued, failed, cancelled, and unsupported AppTask records. Assert current_reusable_workflow_steps preserves supported descriptors from completed/running/queued states, duplicates, and order while reporting skipped entries.
- [ ] Implement current_reusable_workflow_steps using TaskState.COMPLETED, RUNNING, and QUEUED as included states.
- [ ] Implement save_current_workflow. If no reusable steps exist, update task-flow status and log without opening a save dialog. Otherwise use asksaveasfilename with .nlworkflow.json and current source directory as default, call workflow_core.save_workflow, and log path plus saved/skipped counts.
- [ ] Run save tests and verify GREEN.

## Task 6: Execute Workflow On Current Data

Files: modify NewLight_Analysis.py and tests/test_workflow_gui.py.

- [ ] Write a failing test that mocks file selection, loads a valid document, and asserts each step is passed to run_preprocess_action in order with one shared run ID and only the last step marked workflow_is_last.
- [ ] Implement execute_workflow: require current movie, open JSON, validate before queueing, create uuid.uuid4().hex, set workflow_runs[run_id]='running', and submit each step through run_preprocess_action.
- [ ] If a step cannot be submitted, mark the run failed so already queued steps skip; report the step number in task-flow status/log.
- [ ] Ensure replayed tasks keep descriptors so resulting history can be saved again. Do not store source/output paths.
- [ ] Run replay-order and invalid-file tests.

## Task 7: Task Panel UI

Files: modify NewLight_Analysis.py, tests/test_gui_static.py, and tests/test_workflow_gui.py.

- [ ] Write failing static tests for task-flow canvas height 250, a row below it, and buttons wired to save_current_workflow and execute_workflow.
- [ ] Increase task_flow_canvas height from 185 to 250.
- [ ] Add a two-column action row below the task canvas with equal-width buttons labelled 保存当前工作流 and 执行工作流; use Accent.TButton for execute and stable sticky='ew' spacing.
- [ ] Keep 取消当前任务 in the status row and workflow entries inside the existing scrollable task canvas.
- [ ] Run a real Tk smoke at 1440x920 and 1100x760; locate buttons, verify canvas height, invoke file-dialog cancel paths, and confirm no layout exception.

## Task 8: Records And Final Verification

Files: modify WORK_LOG.md and PROJECT_HANDOFF.md.

- [ ] Record JSON schema, button location, supported/excluded actions, current-data execution, FIFO order, stop-on-failure/cancellation, and future detailed-manual requirements.
- [ ] Run complete source verification in clean Tk processes, py_compile all touched Python files, and git diff --check.
- [ ] Confirm no sample data, model files, dist, build outputs, or unrelated dirty files were modified. Do not rebuild the EXE unless separately requested.

## Definition Of Done

- A workflow saved in one session can be opened after restart and applied to a different current dataset.
- Parameters and duplicate step order are preserved exactly.
- Failure or cancellation prevents later same-run steps from touching data.
- Task panel buttons are visible below the enlarged list.
- Format and user procedure are recorded for the detailed manual.
