"""Asset initialization and task publishing (post-init, all work goes through the broker)."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from shared.database.pool import get_database
from shared.messaging.redis_streams import JobBroker, StreamsConfig
from shared.messaging.reliability import record_job_pending
from shared.protocol.envelope import OutputSpec, ServiceName, TaskEnvelope, TaskStatus

logger = logging.getLogger(__name__)


def _public_file_url(_storage_root: Path, rel: Path, public_base: str) -> str:
    return f"{public_base.rstrip('/')}/static/storage/{rel.as_posix()}"


class AssetManager:
    def __init__(self) -> None:
        self._redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self._storage = Path(os.environ.get("STORAGE_ROOT", "./storage")).resolve()
        self._public_base = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
        self._broker: JobBroker | None = None

    async def connect(self) -> None:
        self._broker = JobBroker(StreamsConfig(redis_url=self._redis_url, consumer_name="asset-mgr"))
        await self._broker.connect()

    async def close(self) -> None:
        if self._broker:
            await self._broker.close()
            self._broker = None

    def _upload_rel(self, asset_id: str, kind: str, filename: str) -> Path:
        rel = Path("upload") / kind / asset_id / filename
        full = self._storage / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        return rel

    async def register_upload(
        self,
        *,
        title: str | None,
        asset_type: str,
        filename: str,
        data: bytes,
    ) -> tuple[str, str]:
        """Persist upload, insert DB row, return (asset_id, upload_url)."""
        asset_id = str(uuid.uuid4())
        rel = self._upload_rel(asset_id, asset_type, filename)
        full_path = self._storage / rel
        full_path.write_bytes(data)
        upload_url = _public_file_url(self._storage, rel, self._public_base)

        db = get_database()
        await db.execute(
            """
            INSERT INTO assets (id, title, type, status, upload_path, ext_metadata)
            VALUES ($1, $2, $3, 'Raw', $4, $5::jsonb)
            """,
            uuid.UUID(asset_id),
            title or filename,
            asset_type,
            upload_url,
            "{}",
        )
        logger.info("registered asset %s type=%s", asset_id, asset_type)
        return asset_id, upload_url

    async def enqueue_pdf_pipeline(self, asset_id: str) -> str:
        """After client calls sync: publish pdf_recognition to ingress."""
        if not self._broker:
            await self.connect()
        assert self._broker is not None
        row = await get_database().fetchrow(
            "SELECT upload_path FROM assets WHERE id = $1",
            uuid.UUID(asset_id),
        )
        if not row:
            raise ValueError("asset not found")
        upload_path = row["upload_path"]
        process_rel = Path("processed") / "pdf" / asset_id
        process_dir = self._storage / process_rel
        process_dir.mkdir(parents=True, exist_ok=True)
        process_url = _public_file_url(self._storage, process_rel / "manifest.json", self._public_base)

        await get_database().execute(
            "UPDATE assets SET status = 'recognizing', process_path = $2 WHERE id = $1",
            uuid.UUID(asset_id),
            process_url,
        )

        env = TaskEnvelope(
            service=ServiceName.pdf_recognition,
            status=TaskStatus.pending,
            input_refs=[upload_path],
            output=OutputSpec(result_url=process_url),
            asset_id=asset_id,
            idempotency_key=f"{asset_id}:pdf_recognition",
            payload={"stage": "pdf", "process_dir_rel": process_rel.as_posix()},
        )
        await record_job_pending(env)
        await self._broker.publish_ingress(env)
        logger.info("enqueued pdf_recognition for asset %s job %s", asset_id, env.job_id)
        return env.job_id

    async def enqueue_video_pipeline(self, asset_id: str) -> str:
        if not self._broker:
            await self.connect()
        assert self._broker is not None
        row = await get_database().fetchrow(
            "SELECT upload_path FROM assets WHERE id = $1",
            uuid.UUID(asset_id),
        )
        if not row:
            raise ValueError("asset not found")
        upload_path = row["upload_path"]
        process_rel = Path("processed") / "video" / asset_id
        (self._storage / process_rel).mkdir(parents=True, exist_ok=True)
        process_url = _public_file_url(self._storage, process_rel / "manifest.json", self._public_base)
        await get_database().execute(
            "UPDATE assets SET status = 'recognizing', process_path = $2 WHERE id = $1",
            uuid.UUID(asset_id),
            process_url,
        )
        env = TaskEnvelope(
            service=ServiceName.video_recognition,
            input_refs=[upload_path],
            output=OutputSpec(result_url=process_url),
            asset_id=asset_id,
            idempotency_key=f"{asset_id}:video_recognition",
            payload={"stage": "video", "process_dir_rel": process_rel.as_posix()},
        )
        await record_job_pending(env)
        await self._broker.publish_ingress(env)
        return env.job_id
