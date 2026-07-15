from __future__ import annotations

import pytest
from tests.helpers import exercise, experiment


@pytest.mark.integration
def test_exercises_parent_scoping_listing_and_delete(client, auth_headers):
    first, second = experiment(client, auth_headers), experiment(client, auth_headers)
    item = exercise(client, auth_headers, first["id"], properties={"condition":"normal", "nested":{"x":1}})
    assert client.post("/experiments/missing/exercises", headers=auth_headers, json={}).status_code == 404
    assert [x["id"] for x in client.get(f"/experiments/{first['id']}/exercises", headers=auth_headers).json()] == [item["id"]]
    assert client.get("/exercises", headers=auth_headers).json()["total"] == 1
    assert client.get(f"/exercises/{item['id']}", headers=auth_headers).json()["hasData"] is False
    assert client.delete(f"/exercises/{item['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/experiments/{first['id']}", headers=auth_headers).status_code == 200


@pytest.mark.integration
def test_exercise_rejects_unknown_fields(client, auth_headers):
    parent = experiment(client, auth_headers)
    assert client.post(f"/experiments/{parent['id']}/exercises", headers=auth_headers, json={"unknown": True}).status_code == 422
