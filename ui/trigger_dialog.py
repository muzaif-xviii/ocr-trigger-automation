"""
trigger_dialog.py
Modal dialog for creating and editing trigger rules.
Supports hotkey, text, and sequence action types.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT_PRIMARY,
    BG_ELEVATED,
    BG_PANEL,
    BORDER_DEFAULT,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

# ── Sequence editor help / placeholder ────────────────────────────────── #

_SEQUENCE_PLACEHOLDER = """\
# One action per line. Examples:
# alt+1
# wait 500
# ctrl+shift+f2
# text /ma "Cure" <t>
# key enter
# wait 200
"""

_SEQUENCE_HELP = (
    "One action per line:\n"
    "  Hotkey:  alt+1  |  ctrl+shift+f2  |  f1\n"
    "  Text:    text /ma \"Cure\" <t>\n"
    "  Key:     key enter  |  key tab\n"
    "  Delay:   wait 500  (milliseconds)"
)

# Index constants for the action-panel stacked widget
_IDX_HOTKEY   = 0
_IDX_TEXT     = 1
_IDX_SEQUENCE = 2


# ── Sequence serialisation helpers ────────────────────────────────────── #

def _parse_sequence_text(raw: str) -> list[dict[str, Any]]:
    """
    Convert the human-readable sequence editor content into the internal
    step-list format stored in config JSON.

    Recognised line formats
    -----------------------
    alt+1                       -> {"type":"hotkey","keys":["alt","1"]}
    ctrl+shift+f2               -> {"type":"hotkey","keys":["ctrl","shift","f2"]}
    wait 500                    -> {"type":"delay","ms":500}
    key enter                   -> {"type":"key","key":"enter"}
    text /ma "Cure" <t>         -> {"type":"text","text":"/ma \"Cure\" <t>"}
    Lines starting with # and blank lines are ignored.
    """
    steps: list[dict[str, Any]] = []
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        lower = line.lower()

        # delay
        if lower.startswith("wait "):
            parts = lower.split(None, 1)
            if len(parts) == 2:
                try:
                    steps.append({"type": "delay", "ms": int(parts[1])})
                except ValueError:
                    pass
            continue

        # single named key
        if lower.startswith("key "):
            key_name = line[4:].strip()
            if key_name:
                steps.append({"type": "key", "key": key_name.lower()})
            continue

        # text — preserve original case and all characters after "text "
        if lower.startswith("text "):
            text_body = line[5:]  # keep original casing / punctuation
            if text_body:
                steps.append({"type": "text", "text": text_body})
            continue

        # hotkey — any remaining non-empty line
        keys = [k.strip().lower() for k in line.split("+") if k.strip()]
        if keys:
            steps.append({"type": "hotkey", "keys": keys})

    return steps


def _sequence_to_text(steps: list[dict[str, Any]]) -> str:
    """Serialise an internal step list back to the human-readable editor format."""
    lines: list[str] = []
    for step in steps:
        t = step.get("type")
        if t == "delay":
            lines.append(f"wait {step.get('ms', 0)}")
        elif t == "hotkey":
            lines.append("+".join(step.get("keys", [])))
        elif t == "key":
            lines.append(f"key {step.get('key', '')}")
        elif t == "text":
            lines.append(f"text {step.get('text', '')}")
    return "\n".join(lines)


# ── Dialog ────────────────────────────────────────────────────────────── #

class TriggerDialog(QDialog):
    """
    Add / Edit trigger dialog.

    Pass an existing trigger dict to ``trigger`` to pre-populate for editing;
    pass None to start a blank new trigger.

    After ``exec()`` returns ``QDialog.Accepted``, call ``get_trigger()`` to
    retrieve the validated trigger dict ready for config storage.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        trigger: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self._trigger = trigger
        self._result: dict[str, Any] | None = None
        self._setup_ui()
        if trigger:
            self._populate(trigger)
        self.setMinimumWidth(560)

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        is_edit = self._trigger is not None
        self.setWindowTitle("Edit Trigger" if is_edit else "New Trigger")
        self.setModal(True)
        self.setStyleSheet(f"QDialog {{ background: {BG_PANEL}; }}")

        root = QVBoxLayout(self)
        root.setSpacing(16)
        root.setContentsMargins(24, 24, 24, 24)

        # ── Header ──────────────────────────────────────────────────── #
        header = QLabel("Edit Trigger" if is_edit else "New Trigger")
        header.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY}; margin-bottom: 4px;"
        )
        root.addWidget(header)

        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER_DEFAULT};")
        root.addWidget(sep)

        # ── Trigger form ─────────────────────────────────────────────── #
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        def lbl(text: str) -> QLabel:
            l = QLabel(text)
            l.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: 500;")
            return l

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Trigger name (optional)")
        form.addRow(lbl("Name"), self._name_edit)

        self._trigger_edit = QLineEdit()
        self._trigger_edit.setPlaceholderText("Text to detect on screen…")
        form.addRow(lbl("Trigger Text *"), self._trigger_edit)

        self._match_combo = QComboBox()
        self._match_combo.addItems(["contains", "exact", "regex"])
        form.addRow(lbl("Match Type"), self._match_combo)

        self._case_check = QCheckBox("Case sensitive")
        form.addRow(lbl(""), self._case_check)

        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(0, 3600)
        self._cooldown_spin.setValue(3)
        self._cooldown_spin.setSuffix(" s")
        self._cooldown_spin.setToolTip("Minimum seconds between repeated triggers")
        form.addRow(lbl("Cooldown"), self._cooldown_spin)

        self._enabled_check = QCheckBox("Enabled")
        self._enabled_check.setChecked(True)
        form.addRow(lbl(""), self._enabled_check)

        root.addLayout(form)

        # ── Action section header ────────────────────────────────────── #
        action_header = QLabel("ACTION")
        action_header.setStyleSheet(
            f"font-size: 11px; font-weight: 600; color: {TEXT_MUTED}; letter-spacing: 1.5px;"
        )
        root.addWidget(action_header)

        # Action type selector row
        type_row = QHBoxLayout()
        type_lbl = QLabel("Type:")
        type_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        self._action_type_combo = QComboBox()
        self._action_type_combo.addItems(["hotkey", "text", "sequence"])
        self._action_type_combo.currentIndexChanged.connect(self._on_action_type_changed)
        type_row.addWidget(type_lbl)
        type_row.addWidget(self._action_type_combo)
        type_row.addStretch()
        root.addLayout(type_row)

        # ── Stacked panels — one per action type ─────────────────────── #
        self._action_stack = QStackedWidget()
        self._action_stack.addWidget(self._build_hotkey_panel())   # _IDX_HOTKEY   = 0
        self._action_stack.addWidget(self._build_text_panel())     # _IDX_TEXT     = 1
        self._action_stack.addWidget(self._build_sequence_panel()) # _IDX_SEQUENCE = 2
        root.addWidget(self._action_stack)

        # ── Button box ──────────────────────────────────────────────── #
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        save_btn.setObjectName("PrimaryButton")
        save_btn.setMinimumWidth(100)
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.setMinimumWidth(80)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ── Individual action panels ─────────────────────────────────────── #

    def _build_hotkey_panel(self) -> QWidget:
        """Panel for the 'hotkey' action type."""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        keys_lbl = QLabel("Keys:")
        keys_lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")

        self._hotkey_edit = QLineEdit()
        self._hotkey_edit.setPlaceholderText("e.g. alt+1  or  ctrl+shift+f2")

        hint = QLabel("Use + to separate keys")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        layout.addWidget(keys_lbl)
        layout.addWidget(self._hotkey_edit, 1)
        layout.addWidget(hint)
        return panel

    def _build_text_panel(self) -> QWidget:
        """
        Panel for the 'text' action type.

        Uses a multiline QTextEdit so that multi-line macros (e.g. a chat
        command followed by a line break) can be entered naturally.  Each
        non-empty line will be typed followed by the newline character, except
        when the user enters a single line in which case no trailing newline is
        appended — matching the most common FFXI macro use-case of
        '/ma "Cure" <t>' with no newline (the enter key is typically a
        separate sequence step or hotkey).
        """
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        hint = QLabel(
            "Text to type exactly as written. Special characters, spaces, quotes,\n"
            "and angle brackets (e.g. <t>) are all supported.\n"
            "For multi-line input each line will be typed followed by Enter."
        )
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        hint.setWordWrap(True)

        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText('/ma "Cure" <t>')
        self._text_edit.setMinimumHeight(80)
        self._text_edit.setMaximumHeight(140)
        self._text_edit.setStyleSheet(
            f"font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px;"
        )

        layout.addWidget(hint)
        layout.addWidget(self._text_edit)
        return panel

    def _build_sequence_panel(self) -> QWidget:
        """Panel for the 'sequence' action type."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        hint = QLabel(_SEQUENCE_HELP)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")

        self._sequence_edit = QTextEdit()
        self._sequence_edit.setPlaceholderText(_SEQUENCE_PLACEHOLDER)
        self._sequence_edit.setMinimumHeight(130)
        self._sequence_edit.setMaximumHeight(220)
        self._sequence_edit.setStyleSheet(
            f"font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px;"
        )

        layout.addWidget(hint)
        layout.addWidget(self._sequence_edit)
        return panel

    # ------------------------------------------------------------------ #
    # Slots                                                                #
    # ------------------------------------------------------------------ #

    def _on_action_type_changed(self, index: int) -> None:
        self._action_stack.setCurrentIndex(index)

    def _on_save(self) -> None:
        trigger_text = self._trigger_edit.text().strip()
        if not trigger_text:
            QMessageBox.warning(self, "Validation Error", "Trigger text cannot be empty.")
            return

        action_type = self._action_type_combo.currentText()
        action: dict[str, Any] = {"type": action_type}

        if action_type == "hotkey":
            raw = self._hotkey_edit.text().strip()
            if not raw:
                QMessageBox.warning(self, "Validation Error", "Please enter at least one key.")
                return
            action["keys"] = [k.strip().lower() for k in raw.split("+") if k.strip()]

        elif action_type == "text":
            body = self._text_edit.toPlainText()
            if not body.strip():
                QMessageBox.warning(self, "Validation Error", "Text to type cannot be empty.")
                return
            action["text"] = body

        elif action_type == "sequence":
            seq_text = self._sequence_edit.toPlainText()
            steps = _parse_sequence_text(seq_text)
            if not steps:
                QMessageBox.warning(
                    self, "Validation Error",
                    "Sequence is empty or invalid.\n"
                    "Add at least one action (hotkey, text, key, or delay).",
                )
                return
            action["sequence"] = steps

        existing_id = self._trigger.get("id") if self._trigger else None

        self._result = {
            "id": existing_id or str(uuid.uuid4()),
            "name": self._name_edit.text().strip() or trigger_text,
            "enabled": self._enabled_check.isChecked(),
            "trigger": trigger_text,
            "match_type": self._match_combo.currentText(),
            "case_sensitive": self._case_check.isChecked(),
            "cooldown": self._cooldown_spin.value(),
            "action": action,
        }
        self.accept()

    # ------------------------------------------------------------------ #
    # Populate from existing trigger                                       #
    # ------------------------------------------------------------------ #

    def _populate(self, t: dict[str, Any]) -> None:
        """Pre-fill all fields from an existing trigger dict."""
        self._name_edit.setText(t.get("name", ""))
        self._trigger_edit.setText(t.get("trigger", ""))

        match_idx = self._match_combo.findText(t.get("match_type", "contains"))
        if match_idx >= 0:
            self._match_combo.setCurrentIndex(match_idx)

        self._case_check.setChecked(bool(t.get("case_sensitive", False)))
        self._cooldown_spin.setValue(int(t.get("cooldown", 3)))
        self._enabled_check.setChecked(bool(t.get("enabled", True)))

        action = t.get("action", {})
        action_type = action.get("type", "hotkey")

        type_idx = self._action_type_combo.findText(action_type)
        if type_idx >= 0:
            self._action_type_combo.setCurrentIndex(type_idx)
            # Stack switches via signal; set contents explicitly below too
            self._action_stack.setCurrentIndex(type_idx)

        if action_type == "hotkey":
            self._hotkey_edit.setText("+".join(action.get("keys", [])))

        elif action_type == "text":
            self._text_edit.setPlainText(action.get("text", ""))

        elif action_type == "sequence":
            self._sequence_edit.setPlainText(
                _sequence_to_text(action.get("sequence", []))
            )

    # ------------------------------------------------------------------ #
    # Result                                                               #
    # ------------------------------------------------------------------ #

    def get_trigger(self) -> dict[str, Any] | None:
        """Return the validated trigger dict after accept(), or None."""
        return self._result
