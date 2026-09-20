"""Makes ``backend`` importable when pytest is run from the repository root."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os

# The suite must run offline on the mock provider even when a developer's .env
# holds a real key: empty values win because load_dotenv() never overrides them.
for _name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_FALLBACKS"):
    os.environ[_name] = ""
