# Screen Trigger Macro

A Windows desktop automation tool that continuously scans a screen region for trigger words using OCR, then executes configured keyboard macros when they appear.

Built with Python 3.11, PySide6, pytesseract, OpenCV, and mss.

---

## Features

- **Live OCR scanning** of any screen region or full screen
- **Trigger rules** with contains / exact / regex matching
- **Single hotkey** or **multi-step sequence** actions with per-step delays
- **Cooldown timers** to prevent repeated rapid firing
- **Cyberpunk dark UI** with purple/blue accents and sidebar navigation
- **System tray** with quick enable/disable
- **Global hotkeys**: F8 toggle scanning, F9 emergency stop
- **Profile system** — save/load complete trigger sets as JSON
- **Activity log** with timestamps for every match and action
- Fully multi-threaded — UI never freezes

---

## Prerequisites

### 1. Python 3.11+

Download from https://www.python.org/downloads/

### 2. Tesseract OCR (required for OCR to work)

**Windows:**

1. Download the installer from https://github.com/UB-Mannheim/tesseract/wiki
2. Run the installer (default path: `C:\Program Files\Tesseract-OCR\`)
3. Add Tesseract to your system PATH **or** enter the full path in Settings → Tesseract path

**Verify installation:**
```
tesseract --version
```

---

## Installation

```bash
# Clone or extract the project
cd screen_trigger_macro

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# Install dependencies
pip install -r requirements.txt
```

---

## Running the App

```bash
python main.py
```

---

## Usage

### Dashboard
- Click **Start Scanning** (or press **F8**) to begin
- Use **Select Region** to draw a custom capture area, or **Full Screen** to reset
- The **Live OCR Preview** shows the text extracted in the last scan

### Triggers
- Click **New Trigger** to add a rule
- Each trigger has:
  - **Trigger Text** — the string to look for
  - **Match Type** — `contains`, `exact`, or `regex`
  - **Case Sensitive** toggle
  - **Cooldown** — seconds before the trigger can fire again
  - **Action** — a single hotkey (e.g. `alt+1`) or a sequence:

```
alt+1
wait 500
f2
wait 200
ctrl+3
```

### Hotkeys
| Key | Action |
|-----|--------|
| F8  | Toggle scanning on/off |
| F9  | Emergency stop (clears action queue) |

### Profiles
Go to **Settings → Profiles** to save and load named configurations.

---

## Project Structure

```
screen_trigger_macro/
├── main.py                  # Entry point
├── requirements.txt
├── config/
│   └── config.json          # Auto-saved configuration
├── profiles/                # Saved profiles (JSON)
├── logs/
│   └── stm.log              # Application log
├── core/
│   ├── config_manager.py    # JSON config persistence
│   ├── screen_capture.py    # mss capture + OpenCV preprocessing
│   ├── ocr_engine.py        # pytesseract wrapper
│   ├── trigger_engine.py    # Pattern matching + cooldowns
│   └── action_executor.py   # Keyboard macro execution
└── ui/
    ├── main_window.py        # Primary PySide6 window
    ├── trigger_dialog.py     # Add/Edit trigger dialog
    ├── region_selector.py    # Fullscreen drag-select overlay
    └── styles.py             # Global stylesheet + colour tokens
```

---

## Building a Standalone EXE with PyInstaller

```bash
# Install PyInstaller (included in requirements.txt)
pip install pyinstaller

# Build single-file executable
pyinstaller --onefile --windowed --name "ScreenTriggerMacro" ^
  --add-data "config;config" ^
  --add-data "profiles;profiles" ^
  main.py
```

The EXE will be in the `dist/` folder.

**Notes:**
- `--windowed` suppresses the console window
- `--onefile` bundles everything into one EXE (slower startup)
- For faster startup use `--onedir` instead
- Tesseract must still be installed separately on the target machine

### Full PyInstaller spec (recommended for distribution)

```bash
pyinstaller --name "ScreenTriggerMacro" \
  --windowed \
  --onedir \
  --add-data "config;config" \
  --add-data "profiles;profiles" \
  --hidden-import "pytesseract" \
  --hidden-import "cv2" \
  --hidden-import "mss" \
  --hidden-import "keyboard" \
  main.py
```

---

## Configuration Reference

`config/config.json` is auto-managed. Manual fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `scan_interval` | int | 300 | ms between scans |
| `region` | [L,T,W,H] or null | null | Capture region (null = full screen) |
| `ocr_confidence_threshold` | int | 60 | Minimum OCR word confidence (0–100) |
| `tesseract_cmd` | string | "" | Full path to tesseract.exe (optional) |
| `triggers` | array | [] | List of trigger rule objects |

### Trigger Object

```json
{
  "id": "unique-string",
  "name": "Display name",
  "enabled": true,
  "trigger": "text to find",
  "match_type": "contains",
  "case_sensitive": false,
  "cooldown": 3,
  "action": {
    "type": "hotkey",
    "keys": ["alt", "1"]
  }
}
```

For a sequence action:

```json
"action": {
  "type": "sequence",
  "sequence": [
    {"type": "hotkey", "keys": ["alt", "1"]},
    {"type": "delay", "ms": 500},
    {"type": "hotkey", "keys": ["f2"]}
  ]
}
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Tesseract not found" | Install Tesseract and add to PATH, or set path in Settings |
| No text detected | Lower the confidence threshold in Settings |
| Actions not firing | Check trigger is **Enabled** and cooldown has expired |
| Global hotkeys not working | Run as Administrator on Windows |
| Region selector not visible | Press Escape to cancel, try again |

---

## License

MIT — for personal automation and accessibility use only.
