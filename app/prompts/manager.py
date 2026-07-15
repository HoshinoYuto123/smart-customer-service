"""Prompt manager – loads YAML templates, renders them with variables,
and supports version management with optional A/B testing."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Sentinel to signal a missing required variable
_MISSING = object()


class PromptManager:
    """Loads and renders prompt templates with version management.

    Templates are YAML files stored in *templates_dir*. Each template declares
    a ``name``, ``version``, list of ``variables``, and a ``template`` string
    that uses Python ``str.format()``-style placeholders.

    Usage::

        mgr = PromptManager(Path(__file__).parent / "templates")
        text = mgr.render("router_prompt", {"user_input": "...", ...})
        system = mgr.get_system_prompt("router_prompt", {"user_input": "...", ...})
    """

    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = Path(templates_dir)
        self._cache: dict[str, dict] = {}
        self._config_cache: dict[str, Any] = {}
        self._load_all()

    # ── Public API ────────────────────────────────────────────────

    def load_template(self, name: str) -> dict:
        """Return the raw template dict for *name* (from cache or disk)."""
        if name not in self._cache:
            self._cache[name] = self._read_template(name)
        return self._cache[name]

    def render(self, name: str, variables: dict[str, Any] | None = None) -> str:
        """Render a template by name, substituting in *variables*.

        Missing required variables are replaced with ``"{{VARNAME}}"`` so the
        upstream LLM can still see which slots are unfilled.
        """
        if variables is None:
            variables = {}

        tmpl = self.load_template(name)
        template_str: str = tmpl.get("template", "")
        declared_vars: list[str] = tmpl.get("variables", [])

        # Inject default placeholders for any required variable not provided
        safe_vars: dict[str, str] = {}
        for var in declared_vars:
            if var in variables:
                safe_vars[var] = str(variables[var])
            else:
                logger.debug(
                    "Template '%s' is missing variable '%s'", name, var
                )
                safe_vars[var] = f"{{{{{var}}}}}"

        # Also pass any extra variables the caller provided
        for k, v in variables.items():
            if k not in safe_vars:
                safe_vars[k] = str(v)

        return template_str.format(**safe_vars)

    def get_system_prompt(self, name: str, variables: dict[str, Any] | None = None) -> str:
        """Convenience: render *name* as a system-level prompt (same as render)."""
        return self.render(name, variables)

    def reload(self) -> None:
        """Clear caches and re-read all templates from disk."""
        self._cache.clear()
        self._config_cache.clear()
        self._load_all()
        logger.info("Prompt templates reloaded from %s", self.templates_dir)

    # ── Version / config helpers ──────────────────────────────────

    def get_version(self, name: str) -> str | None:
        """Return the current version string for a template."""
        config = self._load_config()
        versions = config.get("current_versions", {})
        return versions.get(name)

    def is_ab_test_enabled(self) -> bool:
        """Return whether A/B testing is active."""
        config = self._load_config()
        ab = config.get("ab_test", {})
        return bool(ab.get("enabled", False))

    # ── Internals ─────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Preload all YAML templates from the templates directory."""
        if not self.templates_dir.is_dir():
            logger.warning("Prompt templates directory not found: %s", self.templates_dir)
            return

        for path in self.templates_dir.glob("*.yaml"):
            if path.name == "prompt_config.yaml":
                continue  # Handled separately
            try:
                with open(path, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if isinstance(data, dict) and "name" in data:
                    self._cache[data["name"]] = data
            except Exception:
                logger.exception("Failed to load prompt template: %s", path)

    def _read_template(self, name: str) -> dict:
        """Read a single template file from disk."""
        path = self.templates_dir / f"{name}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"Prompt template not found: {path}")

        with open(path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        if not isinstance(data, dict) or "template" not in data:
            raise ValueError(f"Invalid template format in {path}")

        return data

    def _load_config(self) -> dict:
        """Load (cached) prompt_config.yaml."""
        if self._config_cache:
            return self._config_cache

        config_path = self.templates_dir / "prompt_config.yaml"
        if config_path.is_file():
            with open(config_path, encoding="utf-8") as fh:
                self._config_cache = yaml.safe_load(fh) or {}
        return self._config_cache


# Singleton instance pointing at the templates directory next to this file
prompt_manager = PromptManager(Path(__file__).parent / "templates")
