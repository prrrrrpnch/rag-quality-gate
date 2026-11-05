import pytest

from rqg.config import get_settings
from rqg.safety.attack_runner import AttackRunner, load_attacks


def attack_params():
    return [pytest.param(a, id=a.id) for a in load_attacks(get_settings().attacks_path)]


@pytest.fixture(scope="session")
def runner():
    return AttackRunner(get_settings(), guardrails=True)
