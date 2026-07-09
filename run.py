"""Launch the Cricket Edge dashboard.

The simplest way to start the whole system: run this file with a Python 3
interpreter that has the project's dependencies installed (see
requirements.txt). From VS Code, just open this file and press Run/F5, or
run it from a terminal:

    python run.py

Then open the URL it prints (defaults to http://127.0.0.1:8765). Press
Ctrl+C in the terminal to stop it.
"""
from __future__ import annotations

import sys

try:
    from cricket_edge.server import main
except ModuleNotFoundError as exc:
    sys.exit(
        f"{exc}\n\n"
        "Missing a dependency. Install this project's requirements first:\n"
        "    python -m pip install -r requirements.txt"
    )

if __name__ == "__main__":
    main()
