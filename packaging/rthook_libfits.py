"""PyInstaller runtime hook: set PYFITS_LIB_PATH to bundled libfits.so."""

from __future__ import annotations

import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    meipass = Path(sys._MEIPASS)
    for name in ("libfits.so", "libfits"):
        candidate = meipass / name
        if candidate.is_file():
            os.environ["PYFITS_LIB_PATH"] = str(candidate)
            break
