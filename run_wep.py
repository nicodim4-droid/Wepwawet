"""Run WEP directly from a source checkout."""

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    source_directory = Path(__file__).resolve().parent / "src"
    sys.path.insert(0, str(source_directory))
    runpy.run_module("wep", run_name="__main__", alter_sys=True)
