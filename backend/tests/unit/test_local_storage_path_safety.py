from pathlib import Path

import pytest

from app.providers.storage.local import LocalStorageProvider


def test_storage_key_must_remain_under_storage_root(tmp_path: Path):
    provider = LocalStorageProvider(str(tmp_path / "documents"))

    with pytest.raises(ValueError, match="outside the storage root"):
        provider._resolve_path("../outside.txt")


def test_local_storage_scheme_is_supported(tmp_path: Path):
    provider = LocalStorageProvider(str(tmp_path / "documents"))

    resolved = provider._resolve_path("local:documents/file.bin")

    assert resolved == (tmp_path / "documents" / "documents" / "file.bin").resolve()
