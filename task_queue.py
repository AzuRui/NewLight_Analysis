"""Single-worker FIFO task controller for the NewLight Tk application.

Workers run outside Tk and return plain data.  Their callbacks are applied by
the Tk thread through :meth:`TaskController.drain_results`, which is also the
only place where the following queued task can start.
"""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
from enum import Enum
import queue
import threading
from typing import Any, Callable, Deque, List, Optional


class TaskState(str, Enum):
    """States shown by the task-flow panel."""

    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class TaskCancelled(Exception):
    """Optional signal for cooperative workers that stop early."""


Worker = Callable[[threading.Event], Any]
StartCallback = Callable[[], None]
SuccessCallback = Callable[[Any], None]
ErrorCallback = Callable[[BaseException], None]
CancelCallback = Callable[[], None]


@dataclass
class AppTask:
    """One queued application operation and its UI-facing state."""

    identifier: int
    label: str
    worker: Worker = field(repr=False)
    on_start: Optional[StartCallback] = field(default=None, repr=False)
    on_success: Optional[SuccessCallback] = field(default=None, repr=False)
    on_error: Optional[ErrorCallback] = field(default=None, repr=False)
    on_cancel: Optional[CancelCallback] = field(default=None, repr=False)
    cancellable: bool = True
    state: TaskState = TaskState.QUEUED
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    error: Optional[str] = None
    workflow_step: Optional[dict] = None
    workflow_run_id: Optional[str] = None
    workflow_is_last: bool = False


@dataclass
class _TaskResult:
    task: AppTask
    value: Any = None
    error: Optional[BaseException] = None


class TaskController:
    """Run one background task at a time and marshal completion to Tk.

    ``drain_results`` must be called by the application's main thread.  It is
    intentional that a finished worker does not start the next task itself:
    the completion callback may replace the active movie, and that state must
    exist before a queued operation begins.
    """

    def __init__(self) -> None:
        self._pending: Deque[AppTask] = deque()
        self._history: List[AppTask] = []
        self._result_queue: queue.Queue[_TaskResult] = queue.Queue()
        self._current_task: Optional[AppTask] = None
        self._next_identifier = 1
        self._lock = threading.RLock()

    @property
    def current_task(self) -> Optional[AppTask]:
        with self._lock:
            return self._current_task

    @property
    def history(self) -> List[AppTask]:
        with self._lock:
            return list(self._history)

    @property
    def pending_tasks(self) -> List[AppTask]:
        with self._lock:
            return list(self._pending)

    def enqueue_task(
        self,
        label: str,
        worker: Worker,
        on_success: Optional[SuccessCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        on_cancel: Optional[CancelCallback] = None,
        *,
        cancellable: bool = True,
        on_start: Optional[StartCallback] = None,
        workflow_step: Optional[dict] = None,
        workflow_run_id: Optional[str] = None,
        workflow_is_last: bool = False,
    ) -> AppTask:
        """Append a task and start it immediately only when idle."""
        with self._lock:
            task = AppTask(
                identifier=self._next_identifier,
                label=label,
                worker=worker,
                on_start=on_start,
                on_success=on_success,
                on_error=on_error,
                on_cancel=on_cancel,
                cancellable=cancellable,
                workflow_step=copy.deepcopy(workflow_step),
                workflow_run_id=workflow_run_id,
                workflow_is_last=workflow_is_last,
            )
            self._next_identifier += 1
            self._history.append(task)
            self._pending.append(task)
            self._start_next_locked()
            return task

    def cancel_current_task(self) -> bool:
        """Request cooperative cancellation without discarding queued work."""
        with self._lock:
            task = self._current_task
            if task is None or not task.cancellable or task.state != TaskState.RUNNING:
                return False
            task.state = TaskState.CANCELLING
            task.cancel_event.set()
            return True

    def has_results(self) -> bool:
        return not self._result_queue.empty()

    def drain_results(self) -> int:
        """Apply finished worker outcomes on the caller's (Tk) thread.

        Returns one when an outcome was processed.  Processing a single result
        keeps a completed task visible for one Tk event-loop turn before a
        very short following task can complete.
        """
        try:
            outcome = self._result_queue.get_nowait()
        except queue.Empty:
            return 0
        self._apply_outcome(outcome)
        return 1

    def reset_history_for_new_dataset(self) -> None:
        """Forget prior-dataset entries while retaining active/new work.

        A primary-load completion calls this after the new dataset becomes
        active.  The loading task and all tasks already queued after it are
        therefore still visible in the new task flow.
        """
        with self._lock:
            retained: List[AppTask] = []
            if self._current_task is not None:
                retained.append(self._current_task)
            retained.extend(self._pending)
            self._history = retained

    def _start_next_locked(self) -> None:
        if self._current_task is not None or not self._pending:
            return
        task = self._pending.popleft()
        task.state = TaskState.RUNNING
        self._current_task = task
        try:
            if task.on_start is not None:
                task.on_start()
        except BaseException as exc:
            self._result_queue.put(_TaskResult(task=task, error=exc))
            return
        threading.Thread(
            target=self._run_task,
            args=(task,),
            name=f"NewLightTask-{task.identifier}",
            daemon=True,
        ).start()

    def _run_task(self, task: AppTask) -> None:
        try:
            value = task.worker(task.cancel_event)
            outcome = _TaskResult(task=task, value=value)
        except BaseException as exc:  # Returned to Tk for normal UI handling.
            outcome = _TaskResult(task=task, error=exc)
        self._result_queue.put(outcome)

    def _apply_outcome(self, outcome: _TaskResult) -> None:
        """Run callbacks, then permit the following FIFO task to begin."""
        task = outcome.task
        with self._lock:
            if task is not self._current_task:
                return

        try:
            if task.cancel_event.is_set() or isinstance(outcome.error, TaskCancelled):
                task.state = TaskState.CANCELLED
                if task.on_cancel is not None:
                    task.on_cancel()
                return

            if outcome.error is not None:
                task.state = TaskState.FAILED
                task.error = str(outcome.error)
                if task.on_error is not None:
                    task.on_error(outcome.error)
                return

            if task.on_success is not None:
                task.on_success(outcome.value)
            task.state = TaskState.COMPLETED
        except BaseException as exc:
            task.state = TaskState.FAILED
            task.error = str(exc)
            if task.on_error is not None:
                try:
                    task.on_error(exc)
                except BaseException as callback_exc:
                    task.error = f"{task.error}\n{callback_exc}"
        finally:
            with self._lock:
                if task is self._current_task:
                    self._current_task = None
                    self._start_next_locked()
