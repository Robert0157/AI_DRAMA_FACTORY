"""Make `import auto_drama` work when pytest targets this directory from the repo root."""
import sys
from pathlib import Path

AUTO_DRAMA_ROOT = Path(__file__).resolve().parents[1]
if str(AUTO_DRAMA_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTO_DRAMA_ROOT))
