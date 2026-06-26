"""
config_manager.py
Handles loading, saving, and managing JSON configuration for Screen Trigger Macro.

PATH RESOLUTION — frozen vs source
------------------------------------
PyInstaller onefile bundles extract all application files into a temporary
directory whose path is stored in sys._MEIPASS.  Within that temp dir,
__file__ resolves correctly for imports, but it is the WRONG base for any
path that must persist between runs (config, profiles, logs).

The only stable anchor point for a frozen onefile EXE is:

    Path(sys.executable).parent

That is the directory that contains ScreenTriggerMacro.exe itself, which is
exactly where the user placed the EXE and where they expect config/ and
profiles/ to live.

When running from source (python main.py) there is no sys.frozen attribute,
so we fall back to the project root derived from this file's real location:

    Path(__file__).resolve().parent.parent

This gives: <repo>/core/../  ==  <repo>/

Layout produced in both modes
------------------------------
Frozen EXE (onefile):
    <exe_dir>/
        ScreenTriggerMacro.exe
        config/
            config.json
        profiles/
            *.json
        logs/
            stm.log

Source run:
    <repo>/
        main.py
        config/
            config.json
        profiles/
            *.json
        logs/
            stm.log

All path properties are logged at INFO level during __init__ so the runtime
location can be verified in the log file without attaching a debugger.
"""

import json
import logging
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base-directory resolution  (module-level so main.py can import it too)
# ---------------------------------------------------------------------------

def _resolve_base_dir() -> Path:
    """
    Return the stable base directory for all persistent application data.

    Rule: if running as a PyInstaller frozen executable, use the directory
    that contains the EXE (sys.executable).  Otherwise use the project root
    derived from this source file's real on-disk location.

    This function is deliberately not cached so that tests can monkeypatch
    sys.frozen and sys.executable independently.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller sets sys.frozen = True and sys.executable = full path
        # to the EXE.  sys._MEIPASS points to the temp extraction dir — we
        # deliberately do NOT use it here.
        base = Path(sys.executable).resolve().parent
    else:
        # Running from source: go up from core/ to the project root.
        base = Path(__file__).resolve().parent.parent

    return base


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "scan_interval": 300,
    "region": None,
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
    "match_type": "contains",
    "case_sensitive": False,
    "action": {
        "type": "hotkey",
        "keys": [],
        "sequence": [],
    },
    "cooldown": 3,
}


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

class ConfigManager:
    """Manages application configuration with file-based persistence."""

    def __init__(self, config_dir: str | Path | None = None) -> None:
        if config_dir is None:
            base = _resolve_base_dir()
            config_dir = base / "config"

        self.config_dir: Path = Path(config_dir).resolve()
        self.profiles_dir: Path = self.config_dir.parent / "profiles"
        self.config_path: Path = self.config_dir / "config.json"

        # Create directories before anything else so the log lines below
        # are emitted after the directories exist.
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # ── Startup path diagnostics ──────────────────────────────────── #
        # These lines are the primary debugging tool for the frozen-path bug.
        # They appear in logs/stm.log and on stdout at every startup.
        frozen_status = "FROZEN (PyInstaller)" if getattr(sys, "frozen", False) else "source"
        logger.info("=" * 60)
        logger.info("Screen Trigger Macro — path diagnostics")
        logger.info("  Runtime mode   : %s", frozen_status)
        logger.info("  sys.executable : %s", sys.executable)
        if getattr(sys, "frozen", False):
            logger.info("  sys._MEIPASS   : %s", getattr(sys, "_MEIPASS", "n/a"))
        logger.info("  config dir     : %s", self.config_dir)
        logger.info("  config file    : %s", self.config_path)
        logger.info("  profiles dir   : %s", self.profiles_dir)
        logger.info("=" * 60)

        self._config: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------ #
    # Load / Save                                                          #
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
        """Return stem names of all .json files in the profiles directory."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        return sorted(p.stem for p in self.profiles_dir.glob("*.json"))

    def save_profile(self, name: str) -> bool:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        path = self.profiles_dir / f"{name}.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            logger.info("Profile saved: %s", path)
            return True
        except OSError as exc:
            logger.error("Failed to save profile '%s': %s", name, exc)
            return False

    def load_profile(self, name: str) -> bool:
        path = self.profiles_dir / f"{name}.json"
        if not path.exists():
            logger.warning("Profile not found: %s", path)
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._config = {**deepcopy(DEFAULT_CONFIG), **json.load(f)}
            self.save()
            logger.info("Profile loaded: %s", path)
            return True
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load profile '%s': %s", name, exc)
            return False
