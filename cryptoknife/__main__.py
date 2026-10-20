import sys
from pathlib import Path

if not __package__:  # run as a file (e.g. VS Code "Run Python File"): make the project root importable
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptoknife.gui.app import main

main()
