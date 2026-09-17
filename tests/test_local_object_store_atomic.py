from __future__ import annotations

from io import BytesIO
from pathlib import Path

from app.saas.storage import LocalObjectStore


def test_local_object_store_publishes_files_without_partial_objects(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")
    source = tmp_path / "source.bin"
    source.write_bytes(b"complete-file")

    uri = store.put_file(source, "tenant/output/result.bin")
    target = store.local_path("tenant/output/result.bin")

    assert uri == "local://tenant/output/result.bin"
    assert target is not None
    assert target.read_bytes() == b"complete-file"
    assert not list(target.parent.glob(".*.part"))


def test_local_object_store_publishes_streams_without_partial_objects(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "objects")

    uri = store.put_stream(BytesIO(b"stream-content"), "tenant/audio/page.wav")
    target = store.local_path("tenant/audio/page.wav")

    assert uri == "local://tenant/audio/page.wav"
    assert target is not None
    assert target.read_bytes() == b"stream-content"
    assert not list(target.parent.glob(".*.part"))
