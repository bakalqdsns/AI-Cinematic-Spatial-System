"""
pytest configuration for AICSS backend tests.
"""
import sys
from pathlib import Path

# Ensure backend root is on sys.path for absolute imports
_backend_root = str(Path(__file__).parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)
