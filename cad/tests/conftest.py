import sys
from pathlib import Path

CAD = Path(__file__).resolve().parents[1]
if str(CAD) not in sys.path:
    sys.path.insert(0, str(CAD))


import pytest


@pytest.fixture(scope="session")
def parts():
    """Every registered part, built once for the whole session, in its print frame."""
    import mech; mech.load_all()
    from mech import ALL
    return {spec.name: spec.build() for spec in ALL}


@pytest.fixture(scope="session")
def placed(parts):
    """The same parts carried to where they sit in the machine."""
    from mech import ALL
    at = {spec.name: spec.placement for spec in ALL}
    return {name: at[name] * p for name, p in parts.items()}
