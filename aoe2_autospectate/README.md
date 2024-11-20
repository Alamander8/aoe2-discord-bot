# AoE2 AutoSpectate

Automate spectating Age of Empires II matches using Playwright and OpenCV.

## Features

- Automatically find and spectate ongoing matches on [AoE2 Companion](https://www.aoe2companion.com/ongoing).
- Detect and follow military conflicts.
- Explore player bases to understand base layouts.
- Dynamically manage camera focus.
- Seamlessly switch focus to the CaptureAge window.

## Requirements

- Python 3.7+
- Playwright
- OpenCV
- PyAutoGUI
- PyGetWindow
- Pillow
- NumPy

## Installation

1. **Clone the Repository**

```bash
git clone https://github.com/yourusername/aoe2_autospectate.git
cd aoe2_autospectate

## Repo structure

aoe2_autospectate/
├── autospectate/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── web_automation.py
│   ├── game_state.py
│   ├── spectate_logic.py
│   ├── utils.py
│   └── windows_management.py
├── templates/
│   ├── town_center.png
│   └── castle.png
├── logs/
│   └── autospectate.log
├── requirements.txt
└── README.md