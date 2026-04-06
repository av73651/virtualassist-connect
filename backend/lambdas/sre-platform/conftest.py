"""Root conftest — adds shared Lambda layer to Python path for tests."""

import sys
from pathlib import Path

# Add the Lambda layer path so 'from shared.middleware...' imports work
_LAYER_PATH = str(Path(__file__).parent.parent.parent / "lambda-layer" / "python")
if _LAYER_PATH not in sys.path:
    sys.path.insert(0, _LAYER_PATH)
