"""Read-only catalog of the nine recorded media triplets."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "collected_sample_data"
CATEGORIES = {"Normal walk2": "normal", "fast walk2": "fast", "Wide step 2": "wide_step"}
PATTERN = re.compile(r"^(motion|audio|video)_(\d{8}_\d{6})\.(csv|wav|h264)$")

@dataclass(frozen=True)
class Sample:
    id: str
    category: str
    timestamp: str
    paths: dict[str, Path]

def catalog() -> list[Sample]:
    output: list[Sample] = []
    for directory, category in CATEGORIES.items():
        grouped: dict[str, dict[str, Path]] = {}
        for path in (ROOT / directory).iterdir():
            match = PATTERN.match(path.name)
            if not match:
                raise AssertionError(f"unexpected fixture {path}")
            stream, timestamp, extension = match.groups()
            expected = {"motion":"csv", "audio":"wav", "video":"h264"}[stream]
            if extension != expected or stream in grouped.setdefault(timestamp, {}):
                raise AssertionError(f"duplicate or invalid fixture {path}")
            grouped[timestamp][stream] = path
        if len(grouped) != 3 or any(set(parts) != {"motion", "audio", "video"} for parts in grouped.values()):
            raise AssertionError(f"{directory} does not contain exactly three complete triplets")
        output.extend(Sample(f"{category}-{timestamp}", category, timestamp, parts) for timestamp, parts in sorted(grouped.items()))
    if len(output) != 9:
        raise AssertionError("expected exactly nine sample triplets")
    return output

def hashes(samples: list[Sample]) -> dict[str, str]:
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for sample in samples for path in sample.paths.values()}
