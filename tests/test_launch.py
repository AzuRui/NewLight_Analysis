import sys
import types
from pathlib import Path

import launch


def _frozen_app(monkeypatch, application_dir: Path):
    started = []
    application = types.ModuleType("NewLight_Analysis")
    application.main = lambda: started.append(True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(application_dir / "NewLight_Analysis.exe"))
    monkeypatch.setattr(
        launch.importlib.util,
        "find_spec",
        lambda _name: (_ for _ in ()).throw(AssertionError("frozen launch probed source packages")),
    )
    monkeypatch.setitem(sys.modules, "NewLight_Analysis", application)
    return started


def _stub_setup_and_splash(monkeypatch, splash_calls: list, plain_calls: list):
    def fake_splash(application_dir, operation):
        splash_calls.append(Path(application_dir))
        lines: list[str] = []
        ok = operation(lines.append, lambda visible: None)
        splash_calls.append(bool(ok))
        return True

    def plain(application_dir, **kwargs):
        plain_calls.append((Path(application_dir), kwargs))
        return True

    monkeypatch.setattr(launch, "run_with_initialization_splash", fake_splash)
    monkeypatch.setattr(launch.machine_setup, "ensure_application_setup", plain)


def test_frozen_launch_skips_source_dependency_probe(monkeypatch, tmp_path):
    started = _frozen_app(monkeypatch, tmp_path)
    monkeypatch.setattr(launch.machine_setup, "setup_is_complete", lambda _path: True)
    monkeypatch.setattr(launch.machine_setup, "startup_will_install_gpu_addon", lambda _dir: False)
    monkeypatch.setattr(launch.machine_setup, "ensure_application_setup", lambda _path: True)

    assert launch.main() == 0
    assert started == [True]


def test_frozen_launch_shows_the_splash_before_a_gpu_addon_download(monkeypatch, tmp_path):
    # A machine that finished setup but has no extension downloads several gigabytes at
    # launch; that path used to start the application in silence.
    started = _frozen_app(monkeypatch, tmp_path)
    splash_calls: list = []
    plain_calls: list = []
    monkeypatch.setattr(launch.machine_setup, "setup_is_complete", lambda _path: True)
    monkeypatch.setattr(launch.machine_setup, "startup_will_install_gpu_addon", lambda _dir: True)
    _stub_setup_and_splash(monkeypatch, splash_calls, plain_calls)

    assert launch.main() == 0
    assert splash_calls[0] == tmp_path.resolve()
    assert splash_calls[1] is True  # the setup ran through the splash, not silently
    assert len(plain_calls) == 1
    # Running under the splash means every stage has a listener again.
    assert plain_calls[0][1]["progress"] is not None
    assert plain_calls[0][1]["dialog_visibility"] is not None
    assert started == [True]


def test_frozen_launch_does_not_raise_the_splash_when_nothing_is_missing(monkeypatch, tmp_path):
    started = _frozen_app(monkeypatch, tmp_path)
    splash_calls: list = []
    plain_calls: list = []
    monkeypatch.setattr(launch.machine_setup, "setup_is_complete", lambda _path: True)
    monkeypatch.setattr(launch.machine_setup, "startup_will_install_gpu_addon", lambda _dir: False)
    _stub_setup_and_splash(monkeypatch, splash_calls, plain_calls)

    assert launch.main() == 0
    assert splash_calls == []
    assert len(plain_calls) == 1
    assert plain_calls[0][1] == {}
    assert started == [True]
