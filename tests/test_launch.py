import sys
import types

import launch


def test_frozen_launch_skips_source_dependency_probe(monkeypatch):
    started = []
    application = types.ModuleType("NewLight_Analysis")
    application.main = lambda: started.append(True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\NewLight_Analysis\NewLight_Analysis.exe")
    monkeypatch.setattr(launch.machine_setup, "setup_is_complete", lambda _path: True)
    monkeypatch.setattr(launch.machine_setup, "ensure_application_setup", lambda _path: True)
    monkeypatch.setattr(
        launch.importlib.util,
        "find_spec",
        lambda _name: (_ for _ in ()).throw(AssertionError("frozen launch probed source packages")),
    )
    monkeypatch.setitem(sys.modules, "NewLight_Analysis", application)

    assert launch.main() == 0
    assert started == [True]
