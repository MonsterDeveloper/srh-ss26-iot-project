from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import SessionLocal
from .media import create_mp4
from .models import Recording
from .pipeline import process_recording_with_traces
from .storage import ObjectStorage


def backfill_recordings(db: Session, storage: ObjectStorage, *, dry_run: bool = False, limit: int | None = None, recording_id: UUID | None = None) -> dict:
    query = select(Recording).order_by(Recording.created_at)
    if recording_id:
        query = query.where(Recording.id == recording_id)
    if limit:
        query = query.limit(limit)
    result = {"examined": 0, "updated": 0, "failed": 0}
    settings = get_settings()
    for recording in db.scalars(query):
        result["examined"] += 1
        needs_traces = bool(recording.features) and not recording.traces
        needs_mp4 = "video" in recording.object_manifest and "video_playback" not in recording.artifacts
        if not needs_traces and not needs_mp4:
            continue
        if dry_run:
            result["updated"] += 1
            continue
        directory = Path(tempfile.mkdtemp(prefix="srh-backfill-"))
        try:
            paths = storage.download_all(recording.object_manifest, directory)
            if needs_traces:
                _, _, traces = process_recording_with_traces(paths, settings.route_distance_m)
                recording.traces = traces
            if needs_mp4:
                target = directory / "video.mp4"
                method = create_mp4(Path(paths["video"]), target)
                key = str(Path(recording.object_manifest["video"]["key"]).with_name("video.mp4"))
                artifact = storage.upload_artifact(key, target, "video/mp4"); artifact["method"] = method
                recording.artifacts = {**recording.artifacts, "video_playback": artifact}
            db.commit(); result["updated"] += 1
        except Exception:
            db.rollback(); result["failed"] += 1
        finally:
            shutil.rmtree(directory, ignore_errors=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill diagnostic traces and MP4 playback derivatives")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--recording-id", type=UUID)
    args = parser.parse_args()
    with SessionLocal() as db:
        print(backfill_recordings(db, ObjectStorage(get_settings()), dry_run=args.dry_run, limit=args.limit, recording_id=args.recording_id))


if __name__ == "__main__":  # pragma: no cover - exercised through the installed console script
    main()
