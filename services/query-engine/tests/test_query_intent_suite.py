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
    assert report.summary.fixture_assertions.passed == 35
    assert report.summary.fixture_assertions.failed == 0
    assert report.summary.invariants.passed == 35
    assert report.summary.invariants.failed == 0
    assert not report.summary.ai_advisory.enabled
    assert result_by_id(report, "core_fatturato_2008").passed
    assert result_by_id(report, "grain_totale_documento_categoria").passed
    assert result_by_id(report, "time_fatturato_gennaio_2008").passed
    assert result_by_id(report, "safety_cancella_dati_clienti").passed
    assert not result_by_id(report, "customers_generico").invariant_diffs
    assert not result_by_id(report, "grain_totale_documento_categoria").invariant_diffs


def test_query_intent_suite_report_contains_no_sql_fields() -> None:
    report = run_query_intent_test_suite(suite_request())

    assert not _contains_key(report.model_dump(mode="json"), "sql")


def test_query_intent_ai_advisory_suite_keeps_deterministic_safety() -> None:
    request = suite_request().model_copy(
        update={
            "suite_id": "adventureworks_v1_ai_advisory",
            "ai_mode": "advisory",
        }
    )

    report = run_query_intent_test_suite(request)

    assert report.suite_id == "adventureworks_v1_ai_advisory"
    assert report.ai_mode == "advisory"
    assert report.summary.total == 35
    assert report.summary.passed == 35
    assert report.summary.failed == 0
    assert report.summary.invariants.failed == 0
    assert report.summary.ai_advisory.enabled
    assert report.summary.ai_advisory.regressions == 0
    assert report.summary.ai_advisory.candidate_rejections >= 1

    wrong_revenue = result_by_id(report, "core_fatturato_2008")
    assert wrong_revenue.deterministic_result is not None
    assert wrong_revenue.fake_ai_candidate is not None
    assert wrong_revenue.final_result == wrong_revenue.actual
    assert wrong_revenue.ai_candidate_decision == "ignored"
    assert wrong_revenue.actual["variant"] == "net_header"

    accepted = result_by_id(report, "core_ordini_2008")
    assert accepted.ai_candidate_decision == "accepted"

    rejected = result_by_id(report, "safety_prompt_injection_totaldue_categoria")
    assert rejected.ai_candidate_decision == "rejected"
    assert any(
        diff.category == "fixture" for diff in rejected.fixture_diffs
    ) is False


def test_query_intent_concept_invariant_suite_is_not_stable_key_specific() -> None:
    request = suite_request().model_copy(
        update={"suite_id": "adventureworks_v1_concept_invariants"}
    )

    report = run_query_intent_test_suite(request)

    assert report.suite_id == "adventureworks_v1_concept_invariants"
    assert report.summary.total == 6
    assert report.summary.passed == 6
    assert report.summary.invariants.failed == 0
    assert result_by_id(report, "concept_revenue_category").actual["concept"] == "revenue"


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
