import threading
import time

from task_queue import TaskController, TaskState


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return bool(predicate())


def test_tasks_run_in_fifo_order_and_next_starts_after_main_thread_completion():
    controller = TaskController()
    first_started = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    events = []

    def first_worker(cancel_event):
        first_started.set()
        assert release_first.wait(1.0)
        return "first-result"

    def second_worker(cancel_event):
        second_started.set()
        return "second-result"

    first = controller.enqueue_task("第一项", first_worker, lambda result: events.append(result))
    second = controller.enqueue_task("第二项", second_worker, lambda result: events.append(result))

    assert first_started.wait(1.0)
    assert first.state == TaskState.RUNNING
    assert second.state == TaskState.QUEUED
    assert not second_started.is_set()

    release_first.set()
    assert _wait_for(controller.has_results)
    controller.drain_results()
    assert events == ["first-result"]
    assert first.state == TaskState.COMPLETED
    assert second_started.wait(1.0)

    assert _wait_for(controller.has_results)
    controller.drain_results()
    assert events == ["first-result", "second-result"]
    assert second.state == TaskState.COMPLETED
    assert controller.current_task is None


def test_queued_task_prepares_on_drain_thread_immediately_before_worker_starts():
    controller = TaskController()
    release_first = threading.Event()
    second_started = threading.Event()
    main_thread_id = threading.get_ident()
    events = []

    controller.enqueue_task("第一项", lambda cancel_event: release_first.wait(1.0))

    def prepare_second():
        events.append(("prepare", threading.get_ident()))

    def second_worker(cancel_event):
        events.append(("worker", threading.get_ident()))
        second_started.set()

    controller.enqueue_task("第二项", second_worker, on_start=prepare_second)
    assert events == []

    release_first.set()
    assert _wait_for(controller.has_results)
    controller.drain_results()
    assert second_started.wait(1.0)
    assert events[0] == ("prepare", main_thread_id)
    assert events[1][0] == "worker"
    assert events[1][1] != main_thread_id

    assert _wait_for(controller.has_results)
    controller.drain_results()


def test_cancelling_current_task_preserves_pending_tasks_and_drops_cancelled_result():
    controller = TaskController()
    worker_started = threading.Event()
    second_started = threading.Event()
    received = []

    def cancellable_worker(cancel_event):
        worker_started.set()
        while not cancel_event.wait(0.005):
            pass
        return "must-not-be-applied"

    def second_worker(cancel_event):
        second_started.set()
        return "next-result"

    first = controller.enqueue_task("可取消项", cancellable_worker, lambda result: received.append(result))
    second = controller.enqueue_task("后续项", second_worker, lambda result: received.append(result))

    assert worker_started.wait(1.0)
    assert controller.cancel_current_task()
    assert first.state == TaskState.CANCELLING
    assert second.state == TaskState.QUEUED

    assert _wait_for(controller.has_results)
    controller.drain_results()
    assert first.state == TaskState.CANCELLED
    assert received == []
    assert second_started.wait(1.0)

    assert _wait_for(controller.has_results)
    controller.drain_results()
    assert second.state == TaskState.COMPLETED
    assert received == ["next-result"]


def test_task_history_can_reset_for_a_new_dataset_while_keeping_load_and_followups():
    controller = TaskController()
    old = controller.enqueue_task("旧数据任务", lambda cancel_event: "old")
    assert _wait_for(controller.has_results)
    controller.drain_results()
    assert old.state == TaskState.COMPLETED

    load_started = threading.Event()
    release_load = threading.Event()
    load = controller.enqueue_task(
        "载入新数据",
        lambda cancel_event: (load_started.set(), release_load.wait(1.0), "new")[2],
    )
    followup = controller.enqueue_task("新数据后续处理", lambda cancel_event: "later")
    assert load_started.wait(1.0)

    controller.reset_history_for_new_dataset()
    assert controller.history == [load, followup]
    release_load.set()
    assert _wait_for(controller.has_results)
    controller.drain_results()
    assert load.state == TaskState.COMPLETED


def test_workflow_metadata_is_preserved_and_descriptor_is_copied():
    controller = TaskController()
    descriptor = {
        "function": "gaussian_smooth",
        "name": "高斯平滑",
        "parameters": {"sigma": "1.5"},
    }

    task = controller.enqueue_task(
        "高斯平滑",
        lambda cancel_event: None,
        workflow_step=descriptor,
        workflow_run_id="run-1",
        workflow_is_last=True,
    )
    descriptor["name"] = "已修改"

    assert task.workflow_step == {
        "function": "gaussian_smooth",
        "name": "高斯平滑",
        "parameters": {"sigma": "1.5"},
    }
    assert task.workflow_run_id == "run-1"
    assert task.workflow_is_last is True
