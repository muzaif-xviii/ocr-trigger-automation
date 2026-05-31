"""
config_manager.py
Handles loading, saving, and managing JSON configuration for Screen Trigger Macro.
Provides a singleton-style interface for access across modules.
"""

import json
import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "scan_interval": 300,
    "region": None,  # None = full screen
    "ocr_confidence_threshold": 60,
    "active_profile": "default",
    "triggers": [],
    "global_enabled": True,
}

DEFAULT_TRIGGER: dict[str, Any] = {
    "id": "",
    "enabled": True,
    "name": "New Trigger",
    "trigger": "",
    "match_type": "contains",  # contains | exact | regex
    "case_sensitive": False,
    "action": {
        "type": "hotkey",  # hotkey | sequence
        "keys": [],
        "sequence": [],
    },
    "cooldown": 3,
}


class ConfigManager:
    """Manages application configuration with file-based persistence."""

    def __init__(self, config_dir: str | None = None) -> None:
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "config.json"
        self._config: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def load(self) -> None:
        """Load configuration from disk, merging with defaults for missing keys."""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._config = {**deepcopy(DEFAULT_CONFIG), **saved}
                logger.info("Configuration loaded from %s", self.config_path)
            else:
                self._config = deepcopy(DEFAULT_CONFIG)
                self.save()
                logger.info("No config found — created default at %s", self.config_path)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load config: %s — using defaults", exc)
            self._config = deepcopy(DEFAULT_CONFIG)

    def save(self) -> bool:
        """Persist configuration to disk. Returns True on success."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.debug("Configuration saved to %s", self.config_path)
            return True
        except OSError as exc:
            logger.error("Failed to save config: %s", exc)
            return False

    # ------------------------------------------------------------------ #
    # Generic get / set                                                    #
    # ------------------------------------------------------------------ #

    def get(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, default)

    def set(self, key: str, value: Any, *, autosave: bool = True) -> None:
        self._config[key] = value
        if autosave:
            self.save()

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    # ------------------------------------------------------------------ #
    # Trigger helpers                                                      #
    # ------------------------------------------------------------------ #

    def get_triggers(self) -> list[dict[str, Any]]:
        return self._config.get("triggers", [])

    def add_trigger(self, trigger: dict[str, Any]) -> None:
        triggers = self.get_triggers()
        triggers.append(trigger)
        self._config["triggers"] = triggers
        self.save()

    def update_trigger(self, trigger_id: str, updated: dict[str, Any]) -> bool:
        triggers = self.get_triggers()
        for i, t in enumerate(triggers):
            if t.get("id") == trigger_id:
                triggers[i] = updated
                self._config["triggers"] = triggers
                self.save()
                return True
        return False

    def delete_trigger(self, trigger_id: str) -> bool:
        triggers = self.get_triggers()
        new_triggers = [t for t in triggers if t.get("id") != trigger_id]
        if len(new_triggers) < len(triggers):
            self._config["triggers"] = new_triggers
            self.save()
            return True
        return False

    def get_trigger_by_id(self, trigger_id: str) -> dict[str, Any] | None:
        for t in self.get_triggers():
            if t.get("id") == trigger_id:
                return t
        return None

    # ------------------------------------------------------------------ #
    # Region helpers                                                       #
    # ------------------------------------------------------------------ #

    def get_region(self) -> list[int] | None:
        return self._config.get("region")

    def set_region(self, region: list[int] | None) -> None:
        self.set("region", region)

    # ------------------------------------------------------------------ #
    # Profile helpers                                                      #
    # ------------------------------------------------------------------ #

    def list_profiles(self) -> list[str]:
        profiles_dir = self.config_dir.parent / "profiles"
        profiles_dir.mkdir(exist_ok=True)
        return [p.stem for p in profiles_dir.glob("*.json")]

    def save_profile(self, name: str) -> bool:
        profiles_dir = self.config_dir.parent / "profiles"
        profiles_dir.mkdir(exist_ok=True)
        path = profiles_dir / f"{name}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            return True
        except OSError as exc:
            logger.error("Failed to save profile '%s': %s", name, exc)
            return False

    def load_profile(self, name: str) -> bool:
        path = self.config_dir.parent / "profiles" / f"{name}.json"
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._config = {**deepcopy(DEFAULT_CONFIG), **json.load(f)}
            self.save()
            return True
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load profile '%s': %s", name, exc)
            return False
