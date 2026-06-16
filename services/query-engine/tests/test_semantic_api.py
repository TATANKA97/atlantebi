from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.models import (
    SemanticGenerationRequest,
    SemanticReviewRequest,
    SemanticValidationRequest,
)
from app.semantic import build_semantic_seed, compute_semantic_hash
from app.semantic_discovery import SemanticDiscoveryError
from tests.test_semantic_builder import (
    GRAPH_VERSION_ID,
    SEMANTIC_VERSION_ID,
    adventureworks_graph,
    semantic_draft,
)
from tests.test_semantic_discovery import proposal_from_fixture


AUTH_HEADERS = {"x-atlante-query-engine-token": "semantic-token"}


def semantic_seed():
    return build_semantic_seed(
        graph=adventureworks_graph(),
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
    )


def provider_config():
    return {
        "provider": "openai",
        "setting_id": "00000000-0000-4000-8000-000000000001",
        "model_id": "gpt-5.5",
        "thinking": {
            "type": "openai_reasoning",
            "effort": "medium",
        },
        "secret_ref": (
            "gcp-secret-manager://projects/demo/secrets/"
            "atlantebi-tenant-setting-openai-ai-key"
        ),
    }


class FakeGateway:
    provider = "openai"
    model_version = "fixture-model-v2"
    thinking_config = {"type": "openai_reasoning", "effort": "medium"}

    async def generate(self, discovery_input):
        return SimpleNamespace(
            response_id="resp_semantic_api",
            proposal=proposal_from_fixture(),
        )


class FailingGateway:
    provider = "openai"
    model_version = "fixture-model-v2"
    thinking_config = {"type": "openai_reasoning", "effort": "medium"}

    async def generate(self, discovery_input):
        raise SemanticDiscoveryError("provider detail must not leak")


def test_semantic_generation_and_validation_requests_are_strict() -> None:
    graph = adventureworks_graph()
    seed = semantic_seed()
    generation_payload = {
        "graph": graph.model_dump(mode="json"),
        "provider_config": provider_config(),
        "seed": seed.model_dump(mode="json"),
    }

    SemanticGenerationRequest.model_validate(generation_payload)
    SemanticValidationRequest.model_validate(
        {
            "graph": generation_payload["graph"],
            "semantic_layer": generation_payload["seed"],
        }
    )

    with pytest.raises(ValidationError):
        SemanticGenerationRequest.model_validate(
            {**generation_payload, "model": "caller-controlled"}
        )

    with pytest.raises(ValidationError, match="based on the supplied graph"):
        SemanticGenerationRequest.model_validate(
            {
                "graph": graph.model_dump(mode="json"),
                "provider_config": provider_config(),
                "seed": seed.model_copy(
                    update={"base_graph_hash": "f" * 64}
                ).model_dump(mode="json"),
            }
        )


def test_semantic_generate_endpoint_is_authenticated_and_uses_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    monkeypatch.setattr(app.state, "semantic_discovery_gateway", FakeGateway())
    payload = {
        "graph": adventureworks_graph().model_dump(mode="json"),
        "provider_config": provider_config(),
        "seed": semantic_seed().model_dump(mode="json"),
    }

    assert client.post("/semantic/generate", json=payload).status_code == 401

    response = client.post(
        "/semantic/generate",
        headers=AUTH_HEADERS,
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provenance"]["response_id"] == "resp_semantic_api"
    assert body["semantic_layer"]["ai_model_version"] == "fixture-model-v2"
    assert body["semantic_layer"]["validation_report"]["status"] == (
        "valid_with_warnings"
    )
    assert body["proposal"]["contract_version"] == "semantic_ai_draft.v1"


def test_semantic_generate_requires_provider_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    monkeypatch.setattr(app.state, "semantic_discovery_gateway", None)

    response = client.post(
        "/semantic/generate",
        headers=AUTH_HEADERS,
        json={
            "graph": adventureworks_graph().model_dump(mode="json"),
            "seed": semantic_seed().model_dump(mode="json"),
        },
    )

    assert response.status_code == 422


def test_semantic_generate_sanitizes_provider_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    monkeypatch.setattr(app.state, "semantic_discovery_gateway", FailingGateway())

    response = client.post(
        "/semantic/generate",
        headers=AUTH_HEADERS,
        json={
            "graph": adventureworks_graph().model_dump(mode="json"),
            "provider_config": provider_config(),
            "seed": semantic_seed().model_dump(mode="json"),
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Semantic discovery provider request failed."
    )


def test_semantic_validate_endpoint_returns_updated_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    invalid_metric = draft.metrics[0].model_copy(
        update={"measure_column_key": "f" * 64}
    )
    reviewed = draft.model_copy(
        update={"metrics": [invalid_metric, *draft.metrics[1:]]}
    )
    reviewed = reviewed.model_copy(
        update={"semantic_hash": compute_semantic_hash(reviewed)}
    )

    response = client.post(
        "/semantic/validate",
        headers=AUTH_HEADERS,
        json={
            "graph": graph.model_dump(mode="json"),
            "semantic_layer": reviewed.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["validation_report"]["status"] == "blocked"
    assert body["validation_report"]["validated_revision"] == reviewed.revision
    assert "METRIC_MEASURE_REQUIRED" in {
        issue["code"]
        for issue in body["validation_report"]["blocking_errors"]
    }


def test_semantic_review_endpoint_applies_patch_and_advances_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metric = draft.metrics[0]
    payload = {
        "graph": graph.model_dump(mode="json"),
        "source_layer": draft.model_dump(mode="json"),
        "patch": {
            "metrics": [
                {
                    "metric_key": str(metric.metric_key),
                    "name": "Reviewed metric",
                }
            ]
        },
    }

    SemanticReviewRequest.model_validate(payload)
    response = client.post(
        "/semantic/review",
        headers=AUTH_HEADERS,
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["revision"] == draft.revision + 1
    assert body["metrics"][0]["name"] == "Reviewed metric"
    assert body["metrics"][0]["status"] == metric.status
    assert body["metrics"][0]["provenance"] == "human"
    assert body["validation_report"]["validated_revision"] == body["revision"]


def test_semantic_review_endpoint_accepts_empty_patch_for_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    graph = adventureworks_graph()
    draft = semantic_draft(graph)

    response = client.post(
        "/semantic/review",
        headers=AUTH_HEADERS,
        json={
            "graph": graph.model_dump(mode="json"),
            "source_layer": draft.model_dump(mode="json"),
            "patch": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["revision"] == draft.revision + 1


def test_semantic_review_endpoint_rejects_unknown_stable_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    graph = adventureworks_graph()
    draft = semantic_draft(graph)

    response = client.post(
        "/semantic/review",
        headers=AUTH_HEADERS,
        json={
            "graph": graph.model_dump(mode="json"),
            "source_layer": draft.model_dump(mode="json"),
            "patch": {
                "metrics": [
                    {
                        "metric_key": "00000000-0000-4000-8000-000000000099",
                        "name": "Unknown",
                    }
                ]
            },
        },
    )

    assert response.status_code == 422
    assert "review target not found" in response.json()["detail"]


def test_semantic_review_enforces_disabled_metric_and_rehashes_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metric = draft.metrics[0]

    response = client.post(
        "/semantic/review",
        headers=AUTH_HEADERS,
        json={
            "graph": graph.model_dump(mode="json"),
            "source_layer": draft.model_dump(mode="json"),
            "patch": {
                "metrics": [
                    {
                        "metric_key": str(metric.metric_key),
                        "aggregation": "avg",
                        "enabled": True,
                        "status": "disabled",
                    }
                ]
            },
        },
    )

    assert response.status_code == 200
    reviewed = response.json()["metrics"][0]
    assert reviewed["enabled"] is False
    assert reviewed["status"] == "disabled"
    assert (
        reviewed["metric_definition_hash"]
        != metric.metric_definition_hash
    )


@pytest.mark.parametrize(
    "invalid_update",
    [
        {"format": None},
        {"source_table_key": None},
        {"synonyms": [""]},
    ],
)
def test_semantic_review_rejects_invalid_patch_output(
    monkeypatch: pytest.MonkeyPatch,
    invalid_update: dict[str, object],
) -> None:
    client = TestClient(app)
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")
    graph = adventureworks_graph()
    draft = semantic_draft(graph)

    response = client.post(
        "/semantic/review",
        headers=AUTH_HEADERS,
        json={
            "graph": graph.model_dump(mode="json"),
            "source_layer": draft.model_dump(mode="json"),
            "patch": {
                "metrics": [
                    {
                        "metric_key": str(draft.metrics[0].metric_key),
                        **invalid_update,
                    }
                ]
            },
        },
    )

    assert response.status_code == 422
