import os
import sys

import pytest

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)
REAL_BANKS = os.path.join(ROOT, "banks")


@pytest.fixture(scope="session")
def fixtures(tmp_path_factory):
    """build every mock bank once per test session."""
    import mock_ds
    import mock_utau

    base = str(tmp_path_factory.mktemp("fixtures"))
    banks = {}
    banks.update(mock_ds.build_all(base))
    banks.update(mock_utau.build_all(base))
    return {"base": base, "banks": banks, "vocoders": os.path.join(base, "vocoders")}


def real_banks():
    from warble.bank import common

    if not os.path.isdir(REAL_BANKS):
        return []
    return common.scan(REAL_BANKS)
