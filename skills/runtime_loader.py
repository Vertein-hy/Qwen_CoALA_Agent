"""Dynamic loader for internalized skill plugins."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Callable

from skills.catalog import SkillCatalog


class SkillPluginLoader:
    """Load user-generated skill functions from disk in a controlled way."""

    def __init__(self, skills_file: Path, index_file: Path | None = None):
        self.skills_file = skills_file
        self.index_file = index_file

    def load(self) -> dict[str, Callable]:
        if not self.skills_file.exists():
            return {}

        module_name = "custom_skills_runtime"
        if module_name in sys.modules:
            del sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(module_name, str(self.skills_file))
        if spec is None or spec.loader is None:
            return {}

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # noqa: BLE001
            # Keep agent startup resilient: one malformed generated skill file
            # must not break the whole runtime.
            print(f"[skills] failed to load '{self.skills_file}': {exc}")
            return {}

        allowed = self._allowed_names()
        loaded: dict[str, Callable] = {}
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if not callable(attr) or attr_name.startswith("_"):
                continue
            if not inspect.isfunction(attr):
                continue
            if allowed is not None and attr_name not in allowed:
                continue
            loaded[attr_name] = attr
        return loaded

    def _allowed_names(self) -> set[str] | None:
        if self.index_file is None or not self.index_file.exists():
            return None
        catalog = SkillCatalog(index_file=self.index_file)
        names = catalog.enabled_skill_names()
        return names if names else None
