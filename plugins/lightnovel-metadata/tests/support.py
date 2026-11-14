"""Load the pure source package without importing the Calibre-only entrypoint."""
import sys
import types
from pathlib import Path
SRC = Path(__file__).resolve().parents[1] / 'src'
if 'lightnovel_metadata' not in sys.modules:
    pkg = types.ModuleType('lightnovel_metadata')
    pkg.__path__ = [str(SRC)]
    sys.modules['lightnovel_metadata'] = pkg
