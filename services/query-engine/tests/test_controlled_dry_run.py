from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.controlled_dry_run import (
    SqlServerMetadataColumn,
    prepare_controlled_dry_run,
    validate_controlled_dry_run_metadata,
)
from app.query_compiler import compile_query_plan
from app.query_result_validator import validate_compiled_query_result_contract
from app.query_intent import resolve_query_intent
from tests.test_query_compiler import _preflight, _snapshot_from_graph
from tests.test_query_compiler_preflight import (
    _active_layer,
    _column_key,
    _composite_multischema_graph,
    _empty_layer_for,
    _intent,
    _layer_with_concept,
    _layer_with_metrics,
    _semantic_metric,
)
from tests.test_query_intent import active_adventureworks_layer, request_for
from tests.test_semantic_builder import adventureworks_graph


def test_prepare_scalar_date_range_metadata_request_and_validate_result_contract() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)
    validation = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)

    preparation = prepare_controlled_dry_run(
        intent,
        preflight,
        compiled,
        validation,
        layer,
        graph,
        schema_snapshot,
        tenant_id="tenant-1",
        user_id="user-1",
        connection_id="connection-1",
    )

    assert preparation.status == "ready"
    assert preparation.metadata_request is not None
    assert preparation.metadata_request.sqlserver_validation_method == "sp_describe_first_result_set"
    assert preparation.metadata_request.browse_information_mode == 0
    assert preparation.metadata_request.statement_template == (
        "EXEC sys.sp_describe_first_result_set @tsql = ?, @params = ?, @browse_information_mode = ?"
    )
    assert preparation.metadata_request.params_declaration == "@p0 date, @p1 date"
    assert len(preparation.compiled_sql_hash or "") == 64
    assert len(preparation.validator_report_hash or "") == 64
    assert [binding.name for binding in preparation.metadata_request.parameter_bindings] == ["@p0", "@p1"]
    assert all(binding.value_fingerprint for binding in preparation.metadata_request.parameter_bindings)

    report = validate_controlled_dry_run_metadata(
        preparation,
        [SqlServerMetadataColumn(name="metric_value", ordinal=1, sql_type="decimal(38,10)", nullable=False)],
        duration_ms=12,
        audit_ref="audit-1",
    )

    assert report.status in {"passed", "passed_with_warnings"}
    assert report.sqlserver_validation_method == "sp_describe_first_result_set"
    assert [column.name for column in report.result_columns] == ["metric_value"]
    assert report.result_columns[0].matches_result_contract is True
    assert len(report.dry_run_report_hash or "") == 64


def test_grouped_join_query_requires_join_predicates_and_validates_metadata_shape() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato per categoria prodotto", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)
    validation = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)

    preparation = _prepare(intent, preflight, compiled, validation, layer, graph, schema_snapshot)

    assert preparation.status == "ready"
    assert preparation.metadata_request is not None
    assert compiled.trace.join_predicates
    assert preparation.metadata_request.params_declaration == "@p0 int"

    report = validate_controlled_dry_run_metadata(
        preparation,
        [
            SqlServerMetadataColumn(name="dimension_0", ordinal=1, sql_type="nvarchar(50)", nullable=True),
            SqlServerMetadataColumn(name="metric_value", ordinal=2, sql_type="money", nullable=False),
        ],
        duration_ms=20,
        audit_ref="audit-2",
    )

    assert report.status in {"passed", "passed_with_warnings"}
    assert [column.expected_role for column in report.result_columns] == ["dimension_0", "metric_value"]
    assert all(column.matches_result_contract for column in report.result_columns)

    missing_predicates = replace(compiled, trace=replace(compiled.trace, join_predicates=[]))
    missing_preparation = _prepare(intent, preflight, missing_predicates, validation, layer, graph, schema_snapshot)

    assert missing_preparation.status == "blocked"
    assert "JOIN_PREDICATE_TRACE_MISSING" in _prep_codes(missing_preparation)


def test_metadata_mismatch_and_engine_error_are_reported_without_rewriting_sql() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)
    validation = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)
    preparation = _prepare(intent, preflight, compiled, validation, layer, graph, schema_snapshot)

    mismatch = validate_controlled_dry_run_metadata(
        preparation,
        [SqlServerMetadataColumn(name="wrong_metric", ordinal=1, sql_type="decimal(38,10)", nullable=False)],
        duration_ms=5,
        audit_ref="audit-3",
    )

    assert mismatch.status == "blocked"
    assert mismatch.decision_category == "metadata_shape_mismatch"
    assert "METADATA_SHAPE_MISMATCH" in _report_codes(mismatch)
    assert preparation.metadata_request is not None
    assert preparation.metadata_request.tsql == compiled.sql

    engine_error = validate_controlled_dry_run_metadata(
        preparation,
        None,
        duration_ms=5,
        audit_ref="audit-4",
        engine_error_category="permission_error",
        engine_error_message="metadata permission denied",
    )

    assert engine_error.status == "engine_error"
    assert engine_error.decision_category == "permission_error"
    assert "SQLSERVER_METADATA_ERROR" in _report_codes(engine_error)


def test_pre_runtime_gates_block_context_method_browse_and_parameter_type_mismatches() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)
    validation = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)

    stale_trace = replace(compiled, trace=replace(compiled.trace, semantic_hash="0" * 64))
    stale = _prepare(intent, preflight, stale_trace, validation, layer, graph, schema_snapshot)
    assert stale.status == "blocked"
    assert "SEMANTIC_HASH_MISMATCH" in _prep_codes(stale)

    unsupported_method = prepare_controlled_dry_run(
        intent,
        preflight,
        compiled,
        validation,
        layer,
        graph,
        schema_snapshot,
        tenant_id="tenant-1",
        user_id="user-1",
        connection_id="connection-1",
        sqlserver_validation_method="showplan_xml",
    )
    assert unsupported_method.status == "blocked"
    assert "SQLSERVER_VALIDATION_METHOD_UNSUPPORTED" in _prep_codes(unsupported_method)

    unsupported_browse = prepare_controlled_dry_run(
        intent,
        preflight,
        compiled,
        validation,
        layer,
        graph,
        schema_snapshot,
        tenant_id="tenant-1",
        user_id="user-1",
        connection_id="connection-1",
        browse_information_mode=1,
    )
    assert unsupported_browse.status == "blocked"
    assert "BROWSE_INFORMATION_MODE_UNSUPPORTED" in _prep_codes(unsupported_browse)

    bad_parameter = replace(compiled, parameters=[replace(compiled.parameters[0], logical_type="xml"), *compiled.parameters[1:]])
    bad_parameter_preparation = _prepare(intent, preflight, bad_parameter, validation, layer, graph, schema_snapshot)
    assert bad_parameter_preparation.status == "blocked"
    assert "PARAMETER_TYPE_UNSUPPORTED" in _prep_codes(bad_parameter_preparation)


def test_composite_key_metadata_request_keeps_join_predicate_gate_strict() -> None:
    graph = _composite_multischema_graph()
    schema_snapshot = _snapshot_from_graph(graph)
    layer = _layer_with_concept(_active_layer(_empty_layer_for(graph)), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "quantity_sold")
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="quantity_sold",
        variant="line_quantity",
        table_name="DOC_LINE",
        measure_column="QTY",
        grain_columns=["COMPANY_ID", "DOC_ID", "LINE_NO"],
        date_column=("DOC_HEAD", "DOC_DATE"),
        required_edges=["FK_LINE_HEAD"],
        value_type="number",
    )
    layer = _layer_with_metrics(layer, [metric])
    intent = _intent(metric, concept_ref="quantity_sold", date_column=_column_key(graph, "DOC_HEAD", "DOC_DATE"))
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)
    validation = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)

    preparation = _prepare(intent, preflight, compiled, validation, layer, graph, schema_snapshot)

    assert preparation.status == "ready"
    assert compiled.trace.join_predicates[0].column_pairs[0].ordinal == 1
    assert compiled.trace.join_predicates[0].column_pairs[1].ordinal == 2
    assert preparation.metadata_request is not None
    assert preparation.metadata_request.params_declaration == "@p0 date, @p1 date"


def test_controlled_dry_run_module_has_no_demo_literals_or_db_driver_calls() -> None:
    source = Path("app/controlled_dry_run.py").read_text(encoding="utf-8")

    assert "SalesOrder" not in source
    assert "ProductCategory" not in source
    assert "DOTES" not in source
    assert "DORIG" not in source
    assert "ANACLI" not in source
    assert "ARTICO" not in source
    assert "CATART" not in source
    assert "cursor" not in source
    assert ".execute" not in source
    assert "app.drivers.sqlserver" not in source
    assert "pyodbc" not in source
    assert "sqlalchemy" not in source


def _prepare(intent, preflight, compiled, validation, layer, graph, schema_snapshot):
    return prepare_controlled_dry_run(
        intent,
        preflight,
        compiled,
        validation,
        layer,
        graph,
        schema_snapshot,
        tenant_id="tenant-1",
        user_id="user-1",
        connection_id="connection-1",
    )


def _prep_codes(report) -> set[str]:
    return {issue.code for issue in [*report.errors, *report.warnings, *report.infos]}


def _report_codes(report) -> set[str]:
    return {issue.code for issue in [*report.errors, *report.warnings, *report.infos]}

