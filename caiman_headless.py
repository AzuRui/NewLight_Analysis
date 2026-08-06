"""Minimal notebook compatibility for frozen, headless CaImAn workers."""

from __future__ import annotations

import sys
import types


class _DisplayObject:
    def __init__(self, data=None, **kwargs):
        self.data = data
        self.options = kwargs

    def update(self, value=None):
        self.data = value


class _ToggleButton(_DisplayObject):
    value = False

    def observe(self, *_args, **_kwargs):
        return None


def install_caiman_headless_compat() -> None:
    """Satisfy CaImAn's import-time notebook APIs without bundling Jupyter."""

    try:
        import IPython.display  # noqa: F401
        import ipywidgets  # noqa: F401
        import holoviews  # noqa: F401
        return
    except ImportError:
        pass

    if "IPython.display" not in sys.modules:
        ipython = sys.modules.get("IPython") or types.ModuleType("IPython")
        ipython.__path__ = []
        display_module = types.ModuleType("IPython.display")

        def display(value=None, **_kwargs):
            return _DisplayObject(value)

        def display_pretty(value=None, **_kwargs):
            return _DisplayObject(value)

        def publish_display_data(*_args, **_kwargs):
            return None

        display_module.display = display
        display_module.display_pretty = display_pretty
        display_module.publish_display_data = publish_display_data
        display_module.Image = _DisplayObject
        display_module.HTML = _DisplayObject
        ipython.display = display_module
        ipython.get_ipython = lambda: None
        ipython.version_info = (0, 0)
        sys.modules["IPython"] = ipython
        sys.modules["IPython.display"] = display_module

    if "ipywidgets" not in sys.modules:
        widgets = types.ModuleType("ipywidgets")
        widgets.ToggleButton = _ToggleButton
        sys.modules["ipywidgets"] = widgets

    if "holoviews" not in sys.modules:
        sys.modules["holoviews"] = types.ModuleType("holoviews")
