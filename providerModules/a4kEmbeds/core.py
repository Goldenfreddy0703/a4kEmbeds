# -*- coding: utf-8 -*-
"""Shared utilities for a4kEmbeds providers."""

from __future__ import annotations

import os


class tools:
    @staticmethod
    def log(message, level="debug"):
        try:
            import xbmc

            xbmc.log(f"[a4kEmbeds] {message}", getattr(xbmc, f"LOG{level.upper()}", xbmc.LOGDEBUG))
        except Exception:
            pass

    @staticmethod
    def get_setting(setting_id, default=""):
        try:
            import xbmcaddon

            return xbmcaddon.Addon().getSetting(setting_id) or default
        except Exception:
            return default

    @staticmethod
    def get_bool_setting(setting_id, default=False):
        value = tools.get_setting(setting_id, "false" if not default else "true")
        return str(value).lower() in ("true", "1", "yes", "on")


def get_all_relative_py_files(init_file):
    """Return provider module names next to an adaptive package __init__.py."""
    folder = os.path.dirname(os.path.abspath(init_file))
    names = []
    for name in os.listdir(folder):
        if not name.endswith(".py"):
            continue
        if name in ("__init__.py",):
            continue
        names.append(name[:-3])
    return sorted(names)
