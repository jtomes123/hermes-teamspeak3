import sys
from pathlib import Path

import pytest

# Add tests/ directory to sys.path so mock gateway.* and tools.* packages
# are discoverable when hermes-agent is not installed in the dev environment.
_tests_dir = Path(__file__).parent
if str(_tests_dir) not in sys.path:
    sys.path.insert(0, str(_tests_dir))


@pytest.fixture
def anyio_backend():
    return "asyncio"
