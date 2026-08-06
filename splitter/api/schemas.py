from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    error: str
    message: str | None = None


class FlexibleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")


class DirectUploadRequest(BaseModel):
    filename: str
    content_type: str | None = None


class ObjectReference(BaseModel):
    model_config = ConfigDict(extra="allow")

    provider: str
    bucket: str
    key: str


class DirectUploadResponse(FlexibleResponse):
    filename: str
    method: str
    url: str
    object: ObjectReference
    headers: dict[str, str] = Field(default_factory=dict)
    max_bytes: int | None = None


class ObjectJobInput(BaseModel):
    filename: str
    object: ObjectReference


class AudiusSource(BaseModel):
    provider: Literal["audius"]
    track_id: str


class CreateObjectJobRequest(BaseModel):
    profile: str | None = None
    input: ObjectJobInput


class CreateAudiusJobRequest(BaseModel):
    profile: str | None = None
    source: AudiusSource


class HealthResponse(BaseModel):
    status: str
    version: str | None = None
    dependencies: dict[str, bool] | None = None


class ProfileMetadata(FlexibleResponse):
    label: str
    public: bool
    tier: str


class ProductContract(FlexibleResponse):
    model_supported_stems: list[str]
    specialist_candidate_stems: list[str]


class StemContract(FlexibleResponse):
    target_stems: list[str]


class CapabilitiesResponse(FlexibleResponse):
    default_profile: str
    evaluation_profile: str
    recommended_profile: str
    product_contract: ProductContract
    stem_contracts: dict[str, StemContract] = Field(default_factory=dict)
    profiles: dict[str, ProfileMetadata]


class AudiusTrack(FlexibleResponse):
    id: str
    title: str = ""
    artist: str = ""
    can_import: bool
    import_reason: str
    artwork_url: str | None = None
    duration_seconds: float = 0
    genre: str | None = None
    license: str | None = None
    permalink: str | None = None


class AudiusSearchResponse(FlexibleResponse):
    provider: Literal["audius"]
    tracks: list[AudiusTrack]
    limit: int
    offset: int


class JobArtifacts(BaseModel):
    bundles: dict[str, str] = Field(default_factory=dict)
    broad_stems: dict[str, str] = Field(default_factory=dict)
    derived_stems: dict[str, str] = Field(default_factory=dict)
    specialist_substems: dict[str, str] = Field(default_factory=dict)
    tempo_locked_wavs: dict[str, str] = Field(default_factory=dict)
    midi: dict[str, str] = Field(default_factory=dict)
    analysis: dict[str, str] = Field(default_factory=dict)
    main_stems: dict[str, str] = Field(default_factory=dict)


class JobTimings(FlexibleResponse):
    local_total_seconds: float | None = None
    local_elapsed_seconds: float | None = None
    worker_total_seconds: float | None = None


class JobResponse(FlexibleResponse):
    job_id: str
    status: str
    artifacts: JobArtifacts = Field(default_factory=JobArtifacts)
    artifact_metadata: dict[str, dict[str, dict[str, Any]]] = Field(default_factory=dict)
    error: str | None = None
    missing_features: list[str] = Field(default_factory=list)
    remote_adapter_reason: str | None = None
    remote_adapter_status: str | None = None
    rejected_candidates: dict[str, Any] = Field(default_factory=dict)
    stage: str | None = None
    timings: JobTimings = Field(default_factory=JobTimings)


class JobEventsResponse(BaseModel):
    events: list[dict[str, Any]]
    next_after: int
