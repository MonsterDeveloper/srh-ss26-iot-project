from __future__ import annotations

import pytest

PUBLIC = ["/", "/health/live", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"]
BUSINESS = [
    ("GET", "/experiments"), ("POST", "/experiments"), ("GET", "/experiments/nope"),
    ("PATCH", "/experiments/nope"), ("DELETE", "/experiments/nope"),
    ("POST", "/experiments/nope/exercises"), ("GET", "/experiments/nope/exercises"),
    ("GET", "/exercises"), ("GET", "/exercises/nope"), ("DELETE", "/exercises/nope"),
    ("POST", "/exercises/nope/recording/start"), ("POST", "/exercises/nope/recording/uploads/refresh"),
    ("POST", "/exercises/nope/recording/stop"), ("POST", "/exercises/nope/recording/retry"),
    ("GET", "/exercises/nope/data"), ("DELETE", "/exercises/nope/data"), ("GET", "/experiments/nope/export"),
]

@pytest.mark.integration
@pytest.mark.parametrize("path", PUBLIC)
def test_public_routes(client, path):
    assert client.get(path).status_code == 200

@pytest.mark.integration
def test_ready_and_openapi_security(client):
    assert client.get("/health/ready").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    models = schema["components"]["schemas"]
    assert {"ExperimentResponse", "ExerciseResponse", "ExperimentPage", "ExercisePage", "UploadResponse", "RecordingDataResponse", "ErrorResponse"} <= set(models)

@pytest.mark.integration
def test_cors_preflight(client):
    allowed = client.options("/experiments", headers={"Origin":"http://testserver", "Access-Control-Request-Method":"GET"})
    rejected = client.options("/experiments", headers={"Origin":"https://bad.test", "Access-Control-Request-Method":"GET"})
    assert allowed.status_code == 200 and allowed.headers["access-control-allow-origin"] == "http://testserver"
    assert rejected.status_code == 400

@pytest.mark.integration
@pytest.mark.parametrize("method,path", BUSINESS)
@pytest.mark.parametrize("headers", [{}, {"Authorization":"Basic no"}, {"Authorization":"Bearer wrong"}])
def test_business_routes_reject_bad_auth(client, method, path, headers):
    assert client.request(method, path, headers=headers, json={}).status_code == 401

@pytest.mark.integration
@pytest.mark.parametrize("method,path", BUSINESS)
def test_correct_token_reaches_route(client, auth_headers, method, path):
    assert client.request(method, path, headers=auth_headers, json={}).status_code != 401


@pytest.mark.integration
@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/experiments/missing"),
        ("PATCH", "/experiments/missing"),
        ("DELETE", "/experiments/missing"),
        ("POST", "/experiments/missing/exercises"),
        ("GET", "/experiments/missing/exercises"),
        ("GET", "/experiments/missing/export"),
        ("GET", "/exercises/missing"),
        ("DELETE", "/exercises/missing"),
        ("POST", "/exercises/missing/recording/start"),
        ("POST", "/exercises/missing/recording/uploads/refresh"),
        ("POST", "/exercises/missing/recording/stop"),
        ("POST", "/exercises/missing/recording/retry"),
        ("GET", "/exercises/missing/data"),
        ("DELETE", "/exercises/missing/data"),
    ],
)
def test_each_resource_endpoint_returns_explicit_404(client, auth_headers, method, path):
    assert client.request(method, path, headers=auth_headers, json={}).status_code == 404
