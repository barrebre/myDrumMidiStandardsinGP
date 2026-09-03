"""Allow running as `python -m gp_midi_remap`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
