import json

import pytest
from pydantic import ValidationError

from app.models import SemanticLayer, SemanticMetric
from app.semantic import compute_metric_definition_hash, compute_semantic_hash
from tests.shared_fixtures import contract_fixture_path


FIXTURE_PATH = contract_fixture_path("semantic-layer-v1.json")


def semantic_fixture() -> dict:
    if FIXTURE_PATH is None:
        pytest.skip("Shared TypeScript contract fixtures are not in this image.")
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_shared_semantic_layer_fixture_matches_pydantic_contract() -> None:
    layer = SemanticLayer.model_validate(semantic_fixture())

    assert layer.contract_version == "semantic_layer.v1"
    assert layer.metrics[0].compiler_eligibility == "eligible_with_disclosure"
    assert layer.metrics[0].dimension_policy.child_one_to_many == "forbidden"
    assert layer.metrics[0].metric_definition_hash == (
        compute_metric_definition_hash(layer.metrics[0])
    )
    assert layer.semantic_hash == compute_semantic_hash(layer)


def test_semantic_contract_rejects_legacy_payload_and_unknown_fields() -> None:
    payload = semantic_fixture()
    payload["raw_sql"] = "select 1"
    with pytest.raises(ValidationError):
        SemanticLayer.model_validate(payload)

    with pytest.raises(ValidationError):
        SemanticLayer.model_validate(
            {
                "tenant_id": payload["tenant_id"],
                "version_id": payload["semantic_version_id"],
                "version": 1,
                "status": "draft",
                "engine": "sqlserver",
                "tables": [],
                "relationships": [],
                "metrics": [],
                "business_anchors": [],
            }
        )


def test_semantic_metric_requires_grain_and_opaque_metric_key() -> None:
    payload = semantic_fixture()["metrics"][0]
    payload.pop("grain_column_keys")
    with pytest.raises(ValidationError):
        SemanticMetric.model_validate(payload)


def test_semantic_contract_nullable_fields_and_wire_formats_match_zod() -> None:
    payload = semantic_fixture()
    payload["ai_model_version"] = None
    payload["ai_prompt_version"] = None
    payload["validation_report"]["validated_at"] = None
    payload["validation_report"]["validated_revision"] = None
    payload["metrics"][0]["description"] = None
    payload["metrics"][0]["default_date_column_key"] = None
    payload["metrics"][0]["measure_column_key"] = None
    payload["metrics"][0]["reasoning_summary"] = None
    payload["metrics"][0]["format"]["currency"] = None

    SemanticLayer.model_validate(payload)

    payload = semantic_fixture()
    payload["semantic_version_id"] = "88888888888848888888888888888888"
    with pytest.raises(ValidationError):
        SemanticLayer.model_validate(payload)

    payload = semantic_fixture()
    payload["semantic_version_id"] = "88888888-8888-0888-8888-888888888888"
    with pytest.raises(ValidationError):
        SemanticLayer.model_validate(payload)

    payload = semantic_fixture()
    payload["validation_report"]["validated_at"] = "2026-06-14 08:00:00+00:00"
    with pytest.raises(ValidationError):
        SemanticLayer.model_validate(payload)

    payload = semantic_fixture()
    payload["validation_report"]["validated_at"] = "2026-06-14T08:00Z"
    with pytest.raises(ValidationError):
        SemanticLayer.model_validate(payload)

    payload = semantic_fixture()
    payload["metrics"][0]["filters"] = [
        {
            "column_key": payload["metrics"][0]["grain_column_keys"][0],
            "operator": "gt",
            "value": float("nan"),
            "value_type": "decimal",
        }
    ]
    with pytest.raises(ValidationError):
        SemanticLayer.model_validate(payload)

    payload = semantic_fixture()["metrics"][0]
    payload["metric_key"] = "fatturato_netto"
    with pytest.raises(ValidationError):
        SemanticMetric.model_validate(payload)

    payload = semantic_fixture()["metrics"][0]
    payload["filters"] = [
        {
            "column_key": payload["grain_column_keys"][0],
            "operator": "in",
            "value": [],
            "value_type": "integer",
        }
    ]
    with pytest.raises(ValidationError):
        SemanticMetric.model_validate(payload)
