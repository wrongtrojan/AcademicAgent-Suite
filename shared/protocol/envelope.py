from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from pydantic import AnyUrl, BaseModel, Field, field_validator


class ServiceName(str, Enum):
    pdf_recognition = "pdf_recognition"
    video_recognition = "video_recognition"
    data_embedding = "data_embedding"
    data_ingesting = "data_ingesting"
    sandbox_inference = "sandbox_inference"
    visual_inference = "visual_inference"
    llm_calling = "llm_calling"
    mixture_searching = "mixture_searching"


class TaskStatus(str, Enum):
    pending = "pending"
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    dead_letter = "dead_letter"


class OutputSpec(BaseModel):
    """Where workers should write durable results (https, s3, minio, file for dev)."""

    result_url: AnyUrl | None = None
    manifest_url: AnyUrl | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class TaskEnvelope(BaseModel):
    """
    Uniform task envelope. Callers pass resource locators as URLs — never raw host filesystem paths.
    file:// is allowed only in dev (guarded by settings in workers).
    """

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str | None = None
    idempotency_key: str | None = None
    service: ServiceName
    status: TaskStatus = TaskStatus.pending

    input_refs: list[str] = Field(
        ...,
        description="List of URLs (https://, s3://, minio://, file:// for dev) pointing at inputs",
    )
    output: OutputSpec = Field(default_factory=OutputSpec)

    asset_id: str | None = None
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("input_refs")
    @classmethod
    def non_empty_inputs(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("input_refs must contain at least one URL")
        return v


class TaskResult(BaseModel):
    job_id: str
    service: ServiceName
    status: TaskStatus
    asset_id: str | None = None
    session_id: str | None = None
    output_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
