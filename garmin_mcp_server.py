"""Compatibility entrypoint for the current project layout.

The application now lives under src/garmin_mcp, but older wrapper scripts still
run this file from the repo root. Ensure the package is importable and delegate to
its real main() entrypoint.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from garmin_mcp import main


if __name__ == "__main__":
    main()
