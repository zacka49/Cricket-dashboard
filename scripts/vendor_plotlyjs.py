from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plotly.offline import get_plotlyjs


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "cricket_edge" / "web" / "static" / "plotly.min.js"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(get_plotlyjs(), encoding="utf-8")
    print(f"Wrote {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
