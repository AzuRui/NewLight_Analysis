"""Guards for the process-exit path of the desktop application.

Closing the main window used to leave ``NewLight_Analysis.exe`` running with no
window at all: Tk runs a posted menu in its own tracking loop, so destroying the
root window from inside that loop never returned from ``mainloop()`` and the
interpreter was never finalized.  The windowless process kept the executable
open, which blocked the next build and left a second launch competing with it.
The application now performs its own exit cleanup and ends the process directly.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY_ROOT))

import NewLight_Analysis  # noqa: E402
import analysis_core  # noqa: E402


def _call_names(function: ast.FunctionDef) -> list[str]:
    names = []
    for node in ast.walk(function):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.append(node.func.attr)
    return names


def test_close_exits_the_process_only_when_the_application_owns_it(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(NewLight_Analysis, "finish_application", lambda application=None: calls.append(application))

    owned = SimpleNamespace(
        exits_process_on_close=True,
        cleaned=0,
        destroyed=False,
        cleanup_session_temp=lambda: setattr(owned, "cleaned", owned.cleaned + 1),
    )
    owned.root = SimpleNamespace(destroy=lambda: setattr(owned, "destroyed", True))
    NewLight_Analysis.NewLightApp.on_close(owned)

    assert owned.destroyed is True
    assert owned.cleaned == 1, "the session temp dir is cleaned while the window closes"
    assert calls == [owned], "closing an owned window has to reach the process exit"

    borrowed = SimpleNamespace(
        exits_process_on_close=False,
        cleaned=0,
        destroyed=False,
        cleanup_session_temp=lambda: setattr(borrowed, "cleaned", borrowed.cleaned + 1),
    )
    borrowed.root = SimpleNamespace(destroy=lambda: setattr(borrowed, "destroyed", True))
    NewLight_Analysis.NewLightApp.on_close(borrowed)

    assert borrowed.destroyed is True
    assert calls == [owned], "a host that embeds the window keeps running after it closes"


def _fail_destroy() -> None:
    import tkinter as tk

    raise tk.TclError("window already torn down")


def test_close_exits_even_when_destroying_the_window_fails(monkeypatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(NewLight_Analysis, "finish_application", lambda application=None: calls.append(application))

    broken = SimpleNamespace(
        exits_process_on_close=True,
        cleanup_session_temp=lambda: None,
    )
    broken.root = SimpleNamespace(destroy=_fail_destroy)
    NewLight_Analysis.NewLightApp.on_close(broken)

    assert calls == [broken], "a failed destroy must not leave the process behind"


def test_main_exits_after_the_mainloop_returns() -> None:
    """The path that returns normally also ends the process explicitly."""
    source = Path(NewLight_Analysis.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    names = _call_names(main)

    assert "mainloop" in names and "finish_application" in names
    assert names.index("finish_application") > names.index("mainloop"), (
        "the exit runs after mainloop() so it cannot tear down a window that is still in use"
    )


def _run_script(tmp_path: Path, filename: str, code: str, timeout: int = 300) -> subprocess.CompletedProcess:
    script = tmp_path / filename
    script.write_text(textwrap.dedent(code), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_finish_application_cleans_up_then_ends_the_process(tmp_path) -> None:
    marker = tmp_path / "cleanup.txt"
    process = _run_script(
        tmp_path,
        "exit_helper.py",
        f"""
        import sys
        from pathlib import Path

        sys.path.insert(0, {str(REPOSITORY_ROOT)!r})
        import NewLight_Analysis

        class Application:
            def cleanup_session_temp(self):
                Path({str(marker)!r}).write_text("cleaned", encoding="utf-8")

        NewLight_Analysis.finish_application(Application())
        print("SHOULD NOT REACH THIS")
        """,
    )

    assert process.returncode == 0, process.stdout + process.stderr
    assert "SHOULD NOT REACH THIS" not in process.stdout, "the exit must be final, not a return"
    assert marker.read_text(encoding="utf-8") == "cleaned"


def test_finish_application_exits_when_cleanup_fails(tmp_path) -> None:
    process = _run_script(
        tmp_path,
        "cleanup_fails.py",
        f"""
        import sys

        sys.path.insert(0, {str(REPOSITORY_ROOT)!r})
        import NewLight_Analysis

        class Application:
            def cleanup_session_temp(self):
                raise RuntimeError("the temp dir is busy")

        NewLight_Analysis.finish_application(Application())
        print("SHOULD NOT REACH THIS")
        """,
    )

    assert process.returncode == 0, process.stdout + process.stderr
    assert "SHOULD NOT REACH THIS" not in process.stdout


def test_worker_processes_do_not_outlive_the_application(tmp_path) -> None:
    child = tmp_path / "child.py"
    child.write_text("import time\n\ntime.sleep(300)\n", encoding="utf-8")
    process = _run_script(
        tmp_path,
        "exit_with_worker.py",
        f"""
        import subprocess
        import sys

        sys.path.insert(0, {str(REPOSITORY_ROOT)!r})
        import NewLight_Analysis
        import analysis_core

        proc = subprocess.Popen([sys.executable, {str(child)!r}])
        analysis_core._register_worker(proc)
        print("CHILD", proc.pid, flush=True)
        NewLight_Analysis.finish_application(None)
        print("SHOULD NOT REACH THIS")
        """,
    )
    assert process.returncode == 0, process.stdout + process.stderr
    assert "SHOULD NOT REACH THIS" not in process.stdout

    child_pid = int(process.stdout.split("CHILD")[1].split()[0])
    deadline = time.time() + 20
    while time.time() < deadline:
        if not _pid_alive(child_pid):
            return
        time.sleep(0.2)
    pytest.fail(f"worker process {child_pid} was still running after the application exited")


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


CLOSE_WHILE_MENU_POSTED = f"""
import sys
import tkinter as tk
from types import SimpleNamespace

sys.path.insert(0, {str(REPOSITORY_ROOT)!r})
try:
    root = tk.Tk()
except tk.TclError as exc:
    print("TK-UNAVAILABLE", exc)
    raise SystemExit(97)

import NewLight_Analysis

application = SimpleNamespace(
    root=root,
    cleanup_session_temp=lambda: print("CLEANED", flush=True),
    exits_process_on_close=True,
)
root.protocol("WM_DELETE_WINDOW", lambda: NewLight_Analysis.NewLightApp.on_close(application))
menu = tk.Menu(root, tearoff=0)
menu.add_command(label="probe item")
print("ROOT_HWND", root.winfo_id(), flush=True)
menu.post(root.winfo_rootx() + 40, root.winfo_rooty() + 40)
root.mainloop()
print("SHOULD NOT REACH THIS: mainloop returned before the process ended")
"""


@pytest.mark.skipif(sys.platform != "win32", reason="the Tk menu tracking loop is the Windows defect")
def test_closing_the_window_while_a_menu_is_posted_ends_the_process(tmp_path) -> None:
    import ctypes
    import threading

    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010

    script = tmp_path / "close_with_menu.py"
    script.write_text(textwrap.dedent(CLOSE_WHILE_MENU_POSTED), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    lines: list[str] = []
    reader = threading.Thread(target=lambda: lines.extend(line.rstrip() for line in proc.stdout), daemon=True)
    reader.start()

    root_child_hwnd = None
    deadline = time.time() + 120
    while time.time() < deadline and root_child_hwnd is None:
        for line in lines:
            if line.startswith("ROOT_HWND"):
                root_child_hwnd = int(line.split()[1])
                break
        if root_child_hwnd is None and proc.poll() is not None:
            break
        time.sleep(0.1)
    assert root_child_hwnd is not None, "the probe window never opened:\n" + "\n".join(lines)
    if lines and lines[0].startswith("TK-UNAVAILABLE"):
        pytest.skip("Tk cannot open a window here: " + lines[0])

    # Tk's toplevel is the parent of the window winfo_id() reports.
    toplevel = user32.GetParent(ctypes.c_void_p(root_child_hwnd)) or root_child_hwnd
    close_at = time.time()
    assert user32.PostMessageW(ctypes.c_void_p(toplevel), WM_CLOSE, 0, 0), "WM_CLOSE was not delivered"

    try:
        exited = proc.wait(timeout=90)
    except subprocess.TimeoutExpired:
        output = "\n".join(lines)
        proc.kill()
        proc.wait(timeout=30)
        pytest.fail(
            "the process survived the closed main window, which is the defect this guards: "
            f"alive {time.time() - close_at:.1f}s after WM_CLOSE\n{output}"
        )
    proc.stdout.close()
    output = "\n".join(lines)

    assert exited == 0, f"exit code {exited} after {time.time() - close_at:.1f}s:\n{output}"
    assert "CLEANED" in output
    assert "SHOULD NOT REACH THIS" not in output, output


def test_exit_helper_is_importable_without_tk() -> None:
    """The exit path is reachable for analysis_core's worker registry alone."""
    assert callable(NewLight_Analysis.finish_application)
    assert callable(analysis_core.terminate_active_workers)
