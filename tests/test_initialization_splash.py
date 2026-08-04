from pathlib import Path

import pytest

import initialization_splash


class FakeSplash:
    def __init__(self):
        self.progress = []
        self.visibility = []
        self.closed = 0

    def set_status(self, message):
        self.progress.append(message)

    def set_visible(self, visible):
        self.visibility.append(visible)

    def run_until_complete(self, operation):
        return operation(self.set_status, self.set_visible)

    def close(self):
        self.closed += 1


def test_runner_propagates_result_progress_and_cleanup(tmp_path):
    splash = FakeSplash()

    def operation(progress, dialog_visibility):
        progress("正在验证分析后端...")
        dialog_visibility(False)
        dialog_visibility(True)
        return True

    result = initialization_splash.run_with_initialization_splash(
        tmp_path,
        operation,
        splash_factory=lambda _path: splash,
    )

    assert result is True
    assert splash.progress == ["正在验证分析后端..."]
    assert splash.visibility == [False, True]
    assert splash.closed == 1


def test_runner_closes_splash_when_operation_raises(tmp_path):
    splash = FakeSplash()

    def operation(_progress, _dialog_visibility):
        raise RuntimeError("setup failed")

    with pytest.raises(RuntimeError, match="setup failed"):
        initialization_splash.run_with_initialization_splash(
            tmp_path,
            operation,
            splash_factory=lambda _path: splash,
        )

    assert splash.closed == 1


def test_resource_dir_prefers_frozen_internal_folder(tmp_path):
    internal = tmp_path / "_internal"
    internal.mkdir()

    assert initialization_splash.resolve_resource_dir(tmp_path) == internal
    assert initialization_splash.resolve_resource_dir(tmp_path / "source") == tmp_path / "source"


def test_factory_failure_is_reported_as_splash_unavailable(tmp_path):
    def broken_factory(_path):
        raise RuntimeError("display unavailable")

    with pytest.raises(initialization_splash.SplashUnavailableError, match="display unavailable"):
        initialization_splash.run_with_initialization_splash(
            tmp_path,
            lambda _progress, _visibility: True,
            splash_factory=broken_factory,
        )
