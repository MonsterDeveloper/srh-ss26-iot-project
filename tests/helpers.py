from __future__ import annotations

from fastapi.testclient import TestClient

def experiment(client: TestClient, headers: dict[str, str], **body) -> dict:
    response = client.post("/experiments", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()

def exercise(client: TestClient, headers: dict[str, str], experiment_id: str, **body) -> dict:
    response = client.post(f"/experiments/{experiment_id}/exercises", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()
