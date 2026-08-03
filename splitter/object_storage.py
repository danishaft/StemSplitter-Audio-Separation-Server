"""Compatibility imports for the infrastructure object-store adapter."""

from .infrastructure.object_storage import (
    ObjectRef,
    ObjectStorageError,
    S3ObjectStore,
    materialize_object,
    object_store_from_config,
    shutdown_object_store,
)

__all__ = [
    "ObjectRef",
    "ObjectStorageError",
    "S3ObjectStore",
    "materialize_object",
    "object_store_from_config",
    "shutdown_object_store",
]
