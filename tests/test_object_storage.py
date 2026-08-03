from __future__ import annotations

from pathlib import Path

import pytest

from splitter.object_storage import ObjectStorageError, S3ObjectStore


class FakeS3Client:
    def __init__(self) -> None:
        self.presigned_request: tuple[tuple[object, ...], dict[str, object]] | None = None

    def head_object(self, **kwargs):
        return {"ContentLength": 1234, "ContentType": "audio/wav", "ETag": '"abc123"'}

    def download_fileobj(self, bucket, key, handle):
        handle.write(b"RIFF-direct-object")

    def generate_presigned_url(self, *args, **kwargs):
        self.presigned_request = (args, kwargs)
        operation = args[0] if args else ""
        return f"https://objects.example/{operation}"


def _store(client: FakeS3Client) -> S3ObjectStore:
    return S3ObjectStore(
        {
            "bucket": "private-audio",
            "prefix": "stemsplitter",
            "presign_ttl": 600,
            "max_object_bytes": 4096,
        },
        client=client,
    )


def test_presigned_put_upload_is_scoped_and_declares_size_limit() -> None:
    client = FakeS3Client()
    grant = _store(client).create_upload("artist song.wav", "audio/wav")

    assert grant["method"] == "PUT"
    assert grant["headers"] == {"Content-Type": "audio/wav"}
    assert grant["max_bytes"] == 4096
    assert grant["object"]["bucket"] == "private-audio"
    assert str(grant["object"]["key"]).startswith("stemsplitter/inputs/")
    assert client.presigned_request is not None
    args, kwargs = client.presigned_request
    assert args == ("put_object",)
    assert kwargs["Params"]["ContentType"] == "audio/wav"


def test_stat_and_download_reject_references_outside_owned_prefix(tmp_path: Path) -> None:
    store = _store(FakeS3Client())
    invalid = {"provider": "s3", "bucket": "private-audio", "key": "another-app/song.wav"}

    with pytest.raises(ObjectStorageError, match="object_key_outside_prefix"):
        store.stat(invalid)

    valid = {"provider": "s3", "bucket": "private-audio", "key": "stemsplitter/inputs/id/song.wav"}
    verified = store.stat(valid)
    target = store.download(verified.as_dict(), tmp_path / "song.wav")

    assert verified.size_bytes == 1234
    assert verified.etag == "abc123"
    assert target.read_bytes() == b"RIFF-direct-object"
