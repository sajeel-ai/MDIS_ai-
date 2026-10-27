import pytest

from conftest import require_disposable_test_database


def test_database_guard_accepts_explicit_test_database():
    require_disposable_test_database("postgresql+asyncpg://u:p@localhost:5432/cognate_ai_test")


@pytest.mark.parametrize("database", ["cognate_ai", "cognate_ai_dev", "postgres"])
def test_database_guard_rejects_non_test_database(database):
    with pytest.raises(RuntimeError, match="must end in _test"):
        require_disposable_test_database(f"postgresql+asyncpg://u:p@localhost:5432/{database}")
