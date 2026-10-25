"""Run the experimental Textual interface from a source checkout."""

import multiprocessing
import sys
from pathlib import Path

if __name__ == "__main__":
    source_directory = Path(__file__).resolve().parent / "src"
    sys.path.insert(0, str(source_directory))
    multiprocessing.freeze_support()

    from wep.textual_app import main

    main()
