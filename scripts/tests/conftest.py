import sys
from pathlib import Path

# Add the scripts directory to sys.path once for the entire pytest session,
# so test modules can import script packages without per-file path mutation.
sys.path.insert(0, str(Path(__file__).parent.parent))
