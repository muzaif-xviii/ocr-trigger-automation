"""
action_executor.py
Executes keyboard actions (hotkeys, text typing, sequences, delays) via the
keyboard library. Runs actions in a dedicated thread to avoid blocking the
OCR loop.

Supported top-level action types
---------------------------------
hotkey   — press a key combination: {"type":"hotkey","keys":["alt","1"]}
text     — type a string verbatim:  {"type":"text","text":"/ma \"Cure\" <t>"}
sequence — ordered list of steps:   {"type":"sequence","sequence":[...]}

Supported sequence step types
-------------------------------
hotkey   — {"type":"hotkey","keys":["ctrl","1"]}
key      — {"type":"key","key":"enter"}        (single named key)
text     — {"type":"text","text":"hello"}       (typed string)
delay    — {"type":"delay","ms":500}            (sleep N milliseconds)
"""

import logging
import time
from queue import Empty, Queue
from threading import Event, Thread
from typing import Any

import keyboard

logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Thread-safe action queue that executes keyboard macros.

    Usage
    -----
    executor = ActionExecutor()
    executor.start()
    executor.execute(action_dict)
    executor.stop()
    """

    def __init__(self) -> None:
        self._queue: Queue[dict[str, Any]] = Queue()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self.enabled: bool = True

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._worker, name="ActionExecutor", daemon=True)
        self._thread.start()
        logger.debug("ActionExecutor started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.debug("ActionExecutor stopped")

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def execute(self, action: dict[str, Any]) -> None:
        """Enqueue an action for asynchronous execution."""
        if self.enabled:
            self._queue.put(action)

    def clear_queue(self) -> None:
        """Drain all pending actions (emergency stop)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Empty:
                break

    # ------------------------------------------------------------------ #
    # Worker                                                               #
    # ------------------------------------------------------------------ #

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                action = self._queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                self._dispatch(action)
            except Exception as exc:
                logger.error("Action execution error: %s", exc)
            finally:
                self._queue.task_done()

    def _dispatch(self, action: dict[str, Any]) -> None:
        """Route a top-level action dict to the correct handler."""
        action_type = action.get("type", "hotkey")

        if action_type == "hotkey":
            self._press_hotkey(action.get("keys", []))

        elif action_type == "text":
            self._type_text(action.get("text", ""))

        elif action_type == "sequence":
            self._run_sequence(action.get("sequence", []))

    # ------------------------------------------------------------------ #
    # Sequence runner                                                      #
    # ------------------------------------------------------------------ #

    def _run_sequence(self, steps: list[dict[str, Any]]) -> None:
        """Execute each step in the sequence in order."""
        for step in steps:
            step_type = step.get("type")

            if step_type == "hotkey":
                self._press_hotkey(step.get("keys", []))

            elif step_type == "key":
                k = step.get("key", "").strip()
                if k:
                    keyboard.press_and_release(k)
                    logger.debug("Key: %s", k)

            elif step_type == "text":
                self._type_text(step.get("text", ""))

            elif step_type == "delay":
                ms = int(step.get("ms", 0))
                if ms > 0:
                    time.sleep(ms / 1000.0)
                    logger.debug("Delay: %dms", ms)

            else:
                logger.warning("Unknown sequence step type: %r", step_type)

    # ------------------------------------------------------------------ #
    # Primitive actions                                                    #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _press_hotkey(keys: list[str]) -> None:
        """
        Press a key combination.

        keys = ["alt", "1"]              ->  Alt+1
        keys = ["ctrl", "shift", "f2"]   ->  Ctrl+Shift+F2
        """
        if not keys:
            return
        clean = [k.strip().lower() for k in keys if k.strip()]
        if not clean:
            return
        combo = "+".join(clean)
        keyboard.press_and_release(combo)
        logger.debug("Hotkey: %s", combo)

    @staticmethod
    def _type_text(text: str) -> None:
        """
        Type a string exactly as provided using keyboard.write().

        keyboard.write() sends individual key-down/key-up events for each
        character, which works correctly with game chat boxes.  It respects
        the current keyboard layout for standard ASCII characters.

        Special characters like <t>, quotes, angle brackets, and spaces are
        all typed literally — no escaping is needed.
        """
        if not text:
            return
        keyboard.write(text, delay=0.02)
        logger.debug("Text typed: %r", text[:40])

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def parse_hotkey_string(hotkey_str: str) -> list[str]:
        """
        Parse 'Alt+1' or 'Ctrl+Shift+F2' into a list of key name strings.
        Returns an empty list on empty input.
        """
        if not hotkey_str:
            return []
        return [part.strip().lower() for part in hotkey_str.split("+") if part.strip()]

    @staticmethod
    def keys_to_display_string(keys: list[str]) -> str:
        """Convert ['ctrl', 'shift', 'f2'] -> 'Ctrl+Shift+F2'"""
        return "+".join(k.capitalize() for k in keys)
