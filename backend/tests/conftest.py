import sys
from pathlib import Path

# Make backend modules importable the same way `uvicorn app:app` sees them.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
