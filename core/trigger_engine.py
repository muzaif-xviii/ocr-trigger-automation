"""
trigger_engine.py
Matches OCR output against configured trigger rules.
Handles cooldown tracking and emits match events.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class TriggerMatch:
    trigger_id: str
    trigger_name: str
    trigger_text: str
    matched_text: str
    action: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class TriggerEngine:
    """
    Evaluates a list of trigger rules against OCR text.

    Each trigger may specify:
    - match_type: 'contains' | 'exact' | 'regex'
    - case_sensitive: bool
    - cooldown: seconds before the same trigger can fire again

    Callbacks
    ---------
    on_match: Callable[[TriggerMatch], None] — called when a trigger fires.
    """

    def __init__(self) -> None:
        self._triggers: list[dict[str, Any]] = []
        self._last_fired: dict[str, float] = {}  # trigger_id -> timestamp
        self._on_match_callbacks: list[Callable[[TriggerMatch], None]] = []
        self.enabled: bool = True

    # ------------------------------------------------------------------ #
    # Configuration                                                        #
    # ------------------------------------------------------------------ #

    def set_triggers(self, triggers: list[dict[str, Any]]) -> None:
        """Replace the current trigger list (thread-safe copy)."""
        self._triggers = list(triggers)
        # Purge cooldown entries for removed triggers
        active_ids = {t.get("id") for t in self._triggers}
        self._last_fired = {k: v for k, v in self._last_fired.items() if k in active_ids}

    def add_on_match(self, callback: Callable[[TriggerMatch], None]) -> None:
        self._on_match_callbacks.append(callback)

    def remove_on_match(self, callback: Callable[[TriggerMatch], None]) -> None:
        self._on_match_callbacks = [c for c in self._on_match_callbacks if c is not callback]

    # ------------------------------------------------------------------ #
    # Evaluation                                                           #
    # ------------------------------------------------------------------ #

    def evaluate(self, ocr_text: str) -> list[TriggerMatch]:
        """
        Test ocr_text against all enabled triggers.

        Returns the list of TriggerMatch objects that fired this cycle
        (after honouring cooldowns). Fires registered callbacks for each.
        """
        if not self.enabled or not ocr_text.strip():
            return []

        matches: list[TriggerMatch] = []
        now = time.time()

        for trigger in self._triggers:
            if not trigger.get("enabled", True):
                continue

            trigger_id = trigger.get("id", "")
            cooldown = float(trigger.get("cooldown", 3))

            # Cooldown check
            last = self._last_fired.get(trigger_id, 0.0)
            if (now - last) < cooldown:
                continue

            # Text matching
            matched = self._match(ocr_text, trigger)
            if not matched:
                continue

            self._last_fired[trigger_id] = now

            action = trigger.get("action", {})
            match_obj = TriggerMatch(
                trigger_id=trigger_id,
                trigger_name=trigger.get("name", trigger.get("trigger", "")),
                trigger_text=trigger.get("trigger", ""),
                matched_text=ocr_text,
                action=action,
                timestamp=now,
            )
            matches.append(match_obj)
            self._fire_callbacks(match_obj)

        return matches

    # ------------------------------------------------------------------ #
    # Matching helpers                                                     #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _match(text: str, trigger: dict[str, Any]) -> bool:
        """Return True if text satisfies the trigger's match rule."""
        pattern = trigger.get("trigger", "")
        match_type = trigger.get("match_type", "contains")
        case_sensitive = trigger.get("case_sensitive", False)

        if not pattern:
            return False

        compare_text = text if case_sensitive else text.lower()
        compare_pattern = pattern if case_sensitive else pattern.lower()

        try:
            if match_type == "exact":
                return compare_text.strip() == compare_pattern.strip()
            elif match_type == "regex":
                flags = 0 if case_sensitive else re.IGNORECASE
                return bool(re.search(pattern, text, flags=flags))
            else:  # contains (default)
                return compare_pattern in compare_text
        except re.error as exc:
            logger.warning("Invalid regex pattern '%s': %s", pattern, exc)
            return False

    # ------------------------------------------------------------------ #
    # Callbacks                                                            #
    # ------------------------------------------------------------------ #

    def _fire_callbacks(self, match: TriggerMatch) -> None:
        for cb in self._on_match_callbacks:
            try:
                cb(match)
            except Exception as exc:
                logger.error("on_match callback raised: %s", exc)

    # ------------------------------------------------------------------ #
    # Cooldown management                                                  #
    # ------------------------------------------------------------------ #

    def reset_cooldowns(self) -> None:
        self._last_fired.clear()

    def get_cooldown_remaining(self, trigger_id: str, cooldown: float) -> float:
        """Return seconds remaining on a trigger's cooldown (0 if expired)."""
        last = self._last_fired.get(trigger_id, 0.0)
        remaining = cooldown - (time.time() - last)
        return max(0.0, remaining)
