import sys
from pathlib import Path

import pytest

from caiman_headless import install_caiman_headless_compat


def test_headless_notebook_import_contracts_are_available():
    names = ("IPython", "IPython.display", "ipywidgets", "holoviews")
    originals = {name: sys.modules.pop(name, None) for name in names}
    try:
        install_caiman_headless_compat()
        from IPython.display import HTML, Image, display
        import IPython
        import ipywidgets
        import holoviews

        handle = display(None, display_id=True)
        if handle is not None:
            handle.update(Image(data=b"test"))
        assert HTML("content").data == "content"
        assert IPython.get_ipython() is None
        assert ipywidgets.ToggleButton(description="Stop") is not None
        assert holoviews.__name__ == "holoviews"
    finally:
        for name in names:
            sys.modules.pop(name, None)
            if originals[name] is not None:
                sys.modules[name] = originals[name]


def test_caiman_version_uses_bundled_release_without_git_or_package_directory(monkeypatch):
    install_caiman_headless_compat()
    import caiman.utils.utils as caiman_utils

    resource_dir = Path(__file__).resolve().parents[1] / "CaImAn_Resources"
    monkeypatch.setenv("CAIMAN_DATA", str(resource_dir))
    monkeypatch.setattr(
        caiman_utils.subprocess,
        "check_output",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError("git unavailable")),
    )
    monkeypatch.setattr(
        caiman_utils.inspect,
        "getfile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("package directory was scanned")),
    )

    assert caiman_utils.get_caiman_version() == ("RELEASE", "1.13.1")
