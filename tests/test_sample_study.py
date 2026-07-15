from __future__ import annotations

import math
import pytest

from tests.helpers import exercise, experiment
from tests.sample_catalog import catalog, hashes


@pytest.mark.sample
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_all_real_sample_triplets_complete_through_api(client, storage, auth_headers, subtests):
    samples = catalog(); before = hashes(samples)
    parent = experiment(client, auth_headers, properties={"study":"all samples"})
    exercises = [exercise(client, auth_headers, parent["id"], properties={"condition": sample.category, "repetition": index + 1, "timestamp": sample.timestamp}) for index, sample in enumerate(samples)]
    successes = []
    for sample, item in zip(samples, exercises, strict=True):
        with subtests.test(sample=sample.id):
            started_response = client.post(f"/exercises/{item['id']}/recording/start", headers=auth_headers)
            assert started_response.status_code == 200, started_response.text
            started = started_response.json()
            # Read persisted keys from the database response indirectly: the manifest layout is deterministic.
            manifest = storage.manifest(parent["id"], item["id"], started["recordingId"])
            for stream, spec in manifest.items():
                storage.internal.put_object(Bucket=storage.bucket, Key=spec["key"], Body=sample.paths[stream].read_bytes(), ContentType=spec["contentType"])
            response = client.post(f"/exercises/{item['id']}/recording/stop", headers=auth_headers)
            assert response.status_code == 200, response.text
            data = response.json(); assert data["status"] == "completed" and data["errors"] == {}
            assert set(data["features"]) == {"motion", "audio", "video"}
            assert client.get(f"/exercises/{item['id']}/data", headers=auth_headers).json() == data
            successes.append(data)
    assert len(successes) == 9
    assert hashes(samples) == before
