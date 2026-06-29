from fastapi.testclient import TestClient

from app.main import app
from app.models import QueryIntentTestSuiteRunRequest
from app.query_intent_suite import run_query_intent_test_suite
from tests.test_query_intent import AUTH_HEADERS, USER_ID, active_adventureworks_layer
from tests.test_semantic_builder import CONNECTION_ID, TENANT_ID, adventureworks_graph


def suite_request() -> QueryIntentTestSuiteRunRequest:
    return QueryIntentTestSuiteRunRequest(
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        user_id=USER_ID,
        connection_name="TEST - AdventureWorksLT",
        environment="test",
        suite_id="adventureworks_v1",
        ai_mode="disabled",
        semantic_layer=active_adventureworks_layer(),
        graph=adventureworks_graph(),
    )


def result_by_id(report, test_id: str):
    return next(result for result in report.results if result.id == test_id)


def test_query_intent_suite_report_passes_adventureworks_v1() -> None:
    request = suite_request()

    report = run_query_intent_test_suite(request)

    assert report.suite_id == "adventureworks_v1"
    assert report.ai_mode == "disabled"
    assert report.connection.name == "TEST - AdventureWorksLT"
    assert report.semantic_layer.version == f"v{request.semantic_layer.version}"
    assert report.semantic_layer.semantic_hash == request.semantic_layer.semantic_hash
    assert report.semantic_layer.base_graph_hash == request.semantic_layer.base_graph_hash
    assert report.semantic_layer.base_policy_hash == request.semantic_layer.base_policy_hash
    assert report.summary.total == 35
    assert report.summary.passed == 35
    assert report.summary.failed == 0
    assert report.summary.skipped == 0
    assert result_by_id(report, "core_fatturato_2008").passed
    assert result_by_id(report, "grain_totale_documento_categoria").passed
    assert result_by_id(report, "time_fatturato_gennaio_2008").passed
    assert result_by_id(report, "safety_cancella_dati_clienti").passed


def test_query_intent_suite_report_contains_no_sql_fields() -> None:
    report = run_query_intent_test_suite(suite_request())

    assert not _contains_key(report.model_dump(mode="json"), "sql")


def test_query_intent_suite_endpoint_returns_report(monkeypatch) -> None:
    monkeypatch.setenv("QUERY_ENGINE_API_TOKEN", "semantic-token")

    response = TestClient(app).post(
        "/query/intent/test-suite/run",
        headers=AUTH_HEADERS,
        json=suite_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["suite_id"] == "adventureworks_v1"
    assert payload["summary"]["total"] == 35
    assert "sql" not in payload


def _contains_key(value, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False
