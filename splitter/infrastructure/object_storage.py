from __future__ import annotations

import os
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any

from ..util import ensure_dir

DEFAULT_MAX_OBJECT_BYTES = 500 * 1024 * 1024
OBJECT_STORAGE_CONFIG = {
    "backend": os.getenv("OBJECT_STORAGE_BACKEND", "local").lower(),
    "bucket": os.getenv("OBJECT_STORAGE_BUCKET"),
    "prefix": os.getenv("OBJECT_STORAGE_PREFIX", "stemsplitter"),
    "endpoint_url": os.getenv("OBJECT_STORAGE_ENDPOINT_URL"),
    "region": os.getenv("OBJECT_STORAGE_REGION") or os.getenv("AWS_REGION"),
    "access_key_id": os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID")
    or os.getenv("AWS_ACCESS_KEY_ID"),
    "secret_access_key": os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY")
    or os.getenv("AWS_SECRET_ACCESS_KEY"),
    "session_token": os.getenv("OBJECT_STORAGE_SESSION_TOKEN")
    or os.getenv("AWS_SESSION_TOKEN"),
    "presign_ttl": int(os.getenv("OBJECT_STORAGE_PRESIGN_TTL", "900")),
    "max_object_bytes": int(
        os.getenv("OBJECT_STORAGE_MAX_BYTES", str(DEFAULT_MAX_OBJECT_BYTES))
    ),
}
_DEFAULT_STORE: Any | None = None
_DEFAULT_STORE_LOCK = RLock()


class ObjectStorageError(RuntimeError):
    """Raised when an object reference or object-store operation is invalid."""


def _safe_filename(filename: str) -> str:
    name = Path(filename).name.strip()
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return safe or "input.bin"


def _normalized_prefix(prefix: str) -> str:
    return str(PurePosixPath(prefix.strip("/"))) if prefix.strip("/") else "stemsplitter"


@dataclass(frozen=True)
class ObjectRef:
    provider: str
    bucket: str
    key: str
    content_type: str | None = None
    size_bytes: int | None = None
    etag: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ObjectRef:
        provider = str(payload.get("provider") or "")
        bucket = str(payload.get("bucket") or "")
        key = str(payload.get("key") or "")
        if provider != "s3" or not bucket or not key:
            raise ObjectStorageError("invalid_object_reference")
        size = payload.get("size_bytes")
        return cls(
            provider=provider,
            bucket=bucket,
            key=key,
            content_type=str(payload["content_type"]) if payload.get("content_type") else None,
            size_bytes=int(size) if size is not None else None,
            etag=str(payload["etag"]) if payload.get("etag") else None,
        )

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "provider": self.provider,
            "bucket": self.bucket,
            "key": self.key,
        }
        if self.content_type:
            payload["content_type"] = self.content_type
        if self.size_bytes is not None:
            payload["size_bytes"] = self.size_bytes
        if self.etag:
            payload["etag"] = self.etag
        return payload


class S3ObjectStore:
    def __init__(self, config: Mapping[str, object], *, client: Any | None = None) -> None:
        self.bucket = str(config.get("bucket") or "")
        if not self.bucket:
            raise ObjectStorageError("object_storage_bucket_missing")
        self.prefix = _normalized_prefix(str(config.get("prefix") or "stemsplitter"))
        self.presign_ttl = int(config.get("presign_ttl") or 900)
        self.max_object_bytes = int(config.get("max_object_bytes") or 0)
        self._client = client or self._build_client(config)

    @staticmethod
    def _build_client(config: Mapping[str, object]) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - depends on production extra
            raise ObjectStorageError("boto3_not_installed") from exc

        kwargs: dict[str, object] = {
            "config": Config(signature_version="s3v4"),
        }
        for source, target in (
            ("endpoint_url", "endpoint_url"),
            ("region", "region_name"),
            ("access_key_id", "aws_access_key_id"),
            ("secret_access_key", "aws_secret_access_key"),
            ("session_token", "aws_session_token"),
        ):
            value = config.get(source)
            if value:
                kwargs[target] = value
        return boto3.client("s3", **kwargs)

    def create_upload(
        self,
        filename: str,
        content_type: str,
        *,
        owner_id: str | None = None,
    ) -> dict[str, object]:
        safe_name = _safe_filename(filename)
        owner_prefix = f"users/{_safe_identity(owner_id)}/" if owner_id else ""
        key = f"{self.prefix}/{owner_prefix}inputs/{uuid.uuid4().hex}/{safe_name}"
        upload_url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=self.presign_ttl,
        )
        return {
            "method": "PUT",
            "url": upload_url,
            "headers": {"Content-Type": content_type},
            "expires_in": self.presign_ttl,
            "max_bytes": self.max_object_bytes,
            "object": ObjectRef("s3", self.bucket, key, content_type=content_type).as_dict(),
        }

    def ping(self) -> bool:
        try:
            self._client.head_bucket(Bucket=self.bucket)
            return True
        except Exception as exc:
            raise ObjectStorageError("object_storage_unavailable") from exc

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()

    def stat(self, reference: Mapping[str, object]) -> ObjectRef:
        ref = self._validated_ref(reference)
        try:
            result = self._client.head_object(Bucket=self.bucket, Key=ref.key)
        except Exception as exc:
            raise ObjectStorageError("object_not_found_or_inaccessible") from exc
        size = int(result.get("ContentLength") or 0)
        if size <= 0:
            raise ObjectStorageError("object_is_empty")
        if self.max_object_bytes > 0 and size > self.max_object_bytes:
            raise ObjectStorageError("object_exceeds_size_limit")
        return ObjectRef(
            provider="s3",
            bucket=self.bucket,
            key=ref.key,
            content_type=str(result.get("ContentType") or ref.content_type or "application/octet-stream"),
            size_bytes=size,
            etag=str(result.get("ETag") or "").strip('"') or None,
        )

    def download(self, reference: Mapping[str, object], target: Path) -> Path:
        ref = self._validated_ref(reference)
        ensure_dir(target.parent)
        temp_path = target.with_name(f".{target.name}.part")
        try:
            with temp_path.open("wb") as handle:
                self._client.download_fileobj(self.bucket, ref.key, handle)
            temp_path.replace(target)
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            raise ObjectStorageError("object_download_failed") from exc
        return target.resolve()

    def read_range(
        self,
        reference: Mapping[str, object],
        *,
        start: int,
        length: int,
    ) -> bytes:
        if start < 0 or length <= 0:
            raise ObjectStorageError("object_range_invalid")
        ref = self._validated_ref(reference)
        try:
            result = self._client.get_object(
                Bucket=self.bucket,
                Key=ref.key,
                Range=f"bytes={start}-{start + length - 1}",
            )
            payload = result["Body"].read()
        except Exception as exc:
            raise ObjectStorageError("object_range_read_failed") from exc
        if not payload:
            raise ObjectStorageError("object_range_is_empty")
        return payload

    def upload(
        self,
        source: Path,
        key: str,
        content_type: str,
        *,
        transfer_config: Any | None = None,
    ) -> ObjectRef:
        normalized_key = self._validated_key(key)
        try:
            upload_kwargs: dict[str, object] = {
                "ExtraArgs": {"ContentType": content_type},
            }
            if transfer_config is not None:
                upload_kwargs["Config"] = transfer_config
            with source.open("rb") as handle:
                self._client.upload_fileobj(
                    handle,
                    self.bucket,
                    normalized_key,
                    **upload_kwargs,
                )
        except Exception as exc:
            raise ObjectStorageError("object_upload_failed") from exc
        return ObjectRef(
            provider="s3",
            bucket=self.bucket,
            key=normalized_key,
            content_type=content_type,
            size_bytes=source.stat().st_size,
        )

    def delete(self, reference: Mapping[str, object]) -> None:
        ref = self._validated_ref(reference)
        try:
            self._client.delete_object(Bucket=self.bucket, Key=ref.key)
        except Exception as exc:
            raise ObjectStorageError("object_delete_failed") from exc

    def artifact_key(self, job_id: str, group: str, filename: str) -> str:
        safe_job_id = re.sub(r"[^A-Za-z0-9_-]+", "", job_id)
        safe_group = re.sub(r"[^A-Za-z0-9_-]+", "", group)
        if not safe_job_id or not safe_group:
            raise ObjectStorageError("invalid_artifact_identity")
        return f"{self.prefix}/jobs/{safe_job_id}/{safe_group}/{_safe_filename(filename)}"

    def signed_download_url(self, reference: Mapping[str, object], filename: str | None = None) -> str:
        ref = self._validated_ref(reference)
        params: dict[str, object] = {"Bucket": self.bucket, "Key": ref.key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{_safe_filename(filename)}"'
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params=params,
                ExpiresIn=self.presign_ttl,
            )
        )

    def _validated_ref(self, reference: Mapping[str, object]) -> ObjectRef:
        ref = ObjectRef.from_dict(reference)
        if ref.bucket != self.bucket:
            raise ObjectStorageError("object_bucket_not_allowed")
        self._validated_key(ref.key)
        return ref

    def _validated_key(self, key: str) -> str:
        path = PurePosixPath(key)
        if path.is_absolute() or ".." in path.parts:
            raise ObjectStorageError("invalid_object_key")
        normalized = str(path)
        if normalized != self.prefix and not normalized.startswith(f"{self.prefix}/"):
            raise ObjectStorageError("object_key_outside_prefix")
        return normalized

    def validate_input_owner(self, reference: Mapping[str, object], owner_id: str) -> None:
        ref = self._validated_ref(reference)
        expected = f"{self.prefix}/users/{_safe_identity(owner_id)}/inputs/"
        if not ref.key.startswith(expected):
            raise ObjectStorageError("object_not_owned_by_principal")


def object_store_from_config(config: Mapping[str, object] | None = None) -> S3ObjectStore | None:
    if config is not None:
        return _build_object_store(config)
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is None:
            _DEFAULT_STORE = _build_object_store(OBJECT_STORAGE_CONFIG)
        return _DEFAULT_STORE


def _build_object_store(config: Mapping[str, object]) -> S3ObjectStore | None:
    resolved = config
    backend = str(resolved.get("backend") or "local").lower()
    if backend == "local":
        return None
    if backend != "s3":
        raise ObjectStorageError(f"unsupported_object_storage_backend:{backend}")
    return S3ObjectStore(resolved)


def shutdown_object_store() -> None:
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is not None:
            _DEFAULT_STORE.close()
            _DEFAULT_STORE = None


def materialize_object(reference: Mapping[str, object], target: Path) -> Path:
    store = object_store_from_config()
    if store is None:
        raise ObjectStorageError("object_storage_not_configured")
    return store.download(reference, target)


def _safe_identity(value: str | None) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
    if not normalized:
        raise ObjectStorageError("invalid_owner_identity")
    return normalized[:128]
