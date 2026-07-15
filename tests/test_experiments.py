from __future__ import annotations

import pytest
from sqlalchemy import update

from api.models import Experiment
from tests.helpers import experiment


@pytest.mark.integration
def test_experiment_crud_patch_and_pagination(client, auth_headers):
    empty = experiment(client, auth_headers)
    full = experiment(client, auth_headers, patientNumber="p-1", height=170, age=70, weight=65, properties={"a":{"b":1}})
    patch = client.patch(f"/experiments/{full['id']}", headers=auth_headers, json={"height": 171, "properties":{"replacement":True}})
    assert patch.status_code == 200 and patch.json()["properties"] == {"replacement": True}
    listing = client.get("/experiments?page=1&pageSize=1", headers=auth_headers).json()
    assert listing["total"] == 2 and len(listing["items"]) == 1
    assert client.get(f"/experiments/{empty['id']}", headers=auth_headers).status_code == 200
    assert client.delete(f"/experiments/{empty['id']}", headers=auth_headers).status_code == 204
    assert client.get(f"/experiments/{empty['id']}", headers=auth_headers).status_code == 404


@pytest.mark.integration
@pytest.mark.parametrize("path", ["/experiments?page=0", "/experiments?pageSize=0", "/experiments?pageSize=101"])
def test_experiment_pagination_validation(client, auth_headers, path):
    assert client.get(path, headers=auth_headers).status_code == 422


@pytest.mark.integration
@pytest.mark.parametrize("body", [{"height": 0}, {"height": 301}, {"age": -1}, {"age": 131}, {"weight": 0}, {"weight": 501}, {"unknown": True}])
def test_experiment_rejects_invalid_or_unknown_fields(client, auth_headers, body):
    assert client.post("/experiments", headers=auth_headers, json=body).status_code == 422
