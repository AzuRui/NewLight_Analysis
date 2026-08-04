# Responsive Task Queue Design

Date: 2026-07-23

## Goal

Keep the Tk UI responsive while any user-triggered analysis, preprocessing,
file conversion, model inference, import, save, or export work runs. The
application processes one task at a time because all operations act on one
current dataset and may depend on the preceding result.

## Interaction Model

- Every long operation becomes an application task with a label, state,
  cancellation event, worker function, and main-thread completion callback.
- Tasks execute in FIFO order. New requests while another task runs are added
  to the end of the queue instead of being rejected or run concurrently.
- The UI main loop remains free for painting, window movement, pan/zoom, log
  updates, parameter editing, and opening dialogs.
- State-mutating results are committed only by the Tk main thread after a task
  finishes. A queued task snapshots the then-current dataset when it starts,
  so queued preprocessing operations naturally compose in order.
- `取消当前任务` requests cooperative cancellation for the running task; queued
  tasks remain queued. The task flow displays cancellation rather than claiming
  success. CPU routines that cannot safely interrupt a native call stop at the
  next frame/loop boundary; external worker processes are terminated when a
  cancellable handle is available.

## Task Flow UI

The left control column becomes a vertical composition of the existing
parameter panel and a persistent `当前数据任务流` panel below it.

- Completed task: light-gray text, no active highlight.
- Queued task: white text.
- Running task: white text with a green outline.
- Last completed task when no job is running and no jobs wait: light-gray text
  with a blue outline.
- Failed or cancelled tasks remain visible with an explanatory suffix and a
  muted warning color.
- The panel shows a cancel button while a task is active and scrolls when the
  current-data history becomes longer than its fixed display area.

## Architecture

`NewLightApp` owns one `TaskController` abstraction. It stores a FIFO pending
queue, the current task, task history for the current dataset, and a
main-thread result queue.

The controller API is:

```python
enqueue_task(label, worker, on_success, on_error=None, cancellable=True)
cancel_current_task()
```

`worker(cancel_event)` performs only background computation/I/O and returns
plain Python/NumPy data. It must not call Tk. `on_success(result)` and
`on_error(error)` always execute from the Tk polling callback.

The existing `run_worker()` becomes a compatibility wrapper over this
controller. Direct background threads for DeepCAD-RT save/cache, heatmap AVI,
NeuroAlign wizard rebuilds, imports, exports, trace extraction, and movie
preprocessing are migrated to it. File dialogs and parameter dialogs remain on
the Tk thread; their resulting paths/values are captured before enqueueing.

## Scope and Safety

- All expensive user-visible operations must execute through the controller.
- Fast, view-only operations may continue on the Tk thread.
- The controller never mutates `AnalysisState` in a worker. It returns results
  to a main-thread callback that updates state and redraws.
- Completed task history is reset when a newly loaded primary dataset becomes
  active, then retains that load task and all later tasks for the new dataset.
- Existing direct calls to `core.run_conda_worker()` gain optional cancellation
  support without changing normal worker behavior.

## Tests

- FIFO order: a second task cannot start until the first callback completes.
- UI polling: worker result delivery starts the following queued task.
- Cancellation: queued work stays pending; a cooperative worker observes its
  event and transitions the current task to cancelled.
- Task-flow state mapping: queued, running, completed-last, failed, and
  cancelled entries receive the specified visual state.
- Regression coverage confirms preprocessing now queues rather than executes
  synchronously and that the task-flow panel is persistent below parameters.

## Non-Goals

- Parallel processing of the same dataset.
- Guaranteed immediate interruption inside uninterruptible C/CUDA calls.
- Persisting the temporary task queue across application restarts.
