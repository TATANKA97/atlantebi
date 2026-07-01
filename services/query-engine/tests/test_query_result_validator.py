from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from app.models import QueryIntentGroupByDimension, SemanticFilter, SemanticMetricFormat
from app.query_compiler import CompiledSqlParameter, CompiledSqlReference, compile_query_plan
from app.query_result_validator import validate_compiled_query_result_contract
from app.query_intent import resolve_query_intent
from tests.test_query_compiler import _preflight, _snapshot_from_graph
from tests.test_query_compiler_preflight import (
    _active_layer,
    _bridge_graph,
    _column_key,
    _composite_multischema_graph,
    _edge_key,
    _empty_layer_for,
    _header_detail_graph,
    _intent,
    _layer_with_concept,
    _layer_with_metrics,
    _semantic_metric,
    _ugly_pmi_snapshot,
    _view_graph,
)
from tests.test_query_intent import active_adventureworks_layer, request_for
from tests.test_queryability_builder import build, column, foreign_key, snapshot, table
from tests.test_semantic_builder import adventureworks_graph


def test_scalar_metric_with_date_range_validates_contract_and_disclosures() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)

    assert report.status in {"valid", "valid_with_warnings"}
    assert report.decision_category in {"safe", "safe_with_disclosure"}
    assert report.result_contract is not None
    assert report.result_contract.shape == "scalar"
    assert [column.alias for column in report.result_contract.columns] == ["metric_value"]
    assert report.result_contract.date_range == {
        "start_date": "2008-01-01",
        "end_date": "2009-01-01",
        "date_column_key": intent.plan.effective_date_column_key,
    }
    assert "DROP" not in compiled.sql


def test_grouped_metric_by_dimension_validates_group_order_limit_contract() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato per categoria prodotto", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)

    assert report.status in {"valid", "valid_with_warnings"}
    assert report.result_contract is not None
    assert report.result_contract.shape == "grouped"
    assert [column.alias for column in report.result_contract.columns] == ["dimension_0", "metric_value"]
    assert report.result_contract.limit == 500
    assert "GROUP BY" in compiled.sql
    assert "ORDER BY [metric_value] DESC, [dimension_0] ASC" in compiled.sql


def test_structured_filters_validate_parameters_for_in_between_and_null() -> None:
    graph = _header_detail_graph(with_fk=True)
    schema_snapshot = _snapshot_from_graph(graph)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "revenue",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="line_detail",
        table_name="DORIG",
        measure_column="IMPORTO",
        grain_columns=["IDRIG"],
        date_column=("DOTES", "DATA_DOC"),
        required_edges=["FK_DORIG_DOTES"],
        value_type="currency",
        eligibility="eligible_with_disclosure",
    )
    layer = _layer_with_metrics(layer, [metric])
    filters = [
        SemanticFilter(column_key=_column_key(graph, "DORIG", "STATO"), operator="in", value=["A", "B"], value_type="string"),
        SemanticFilter(column_key=_column_key(graph, "DORIG", "IMPORTO"), operator="between", value=[10, 100], value_type="decimal"),
        SemanticFilter(column_key=_column_key(graph, "DORIG", "STATO"), operator="is_not_null", value=None, value_type="string"),
    ]
    intent = _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC"), filters=filters)
    preflight = _preflight(intent, layer, graph, schema_snapshot, policy={"status_scope": "include_all_with_disclosure"})
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)

    assert report.status in {"valid", "valid_with_warnings"}
    assert "IN (@p2, @p3)" in compiled.sql
    assert "BETWEEN @p4 AND @p5" in compiled.sql
    assert "IS NOT NULL" in compiled.sql
    assert [param.name for param in compiled.parameters] == [f"@p{index}" for index in range(len(compiled.parameters))]


def test_ugly_erp_composite_multischema_weird_identifier_and_view_sources_validate() -> None:
    ugly_snapshot = _ugly_pmi_snapshot()
    ugly_graph = build(ugly_snapshot)
    ugly_layer = _layer_with_concept(
        _active_layer(_empty_layer_for(ugly_graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "quantity_sold",
    )
    ugly_metric = _semantic_metric(
        ugly_graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="quantity_sold",
        variant="line_quantity",
        table_name="DORIG",
        measure_column="QTA",
        grain_columns=["ID"],
        dimension_column=("CATART", "CAT"),
        dimension_edges=["FK_DORIG_ARTICO", "FK_ARTICO_CATART"],
        value_type="number",
    )
    ugly_layer = _layer_with_metrics(ugly_layer, [ugly_metric])
    ugly_intent = _intent(
        ugly_metric,
        concept_ref="quantity_sold",
        group_by=[
            QueryIntentGroupByDimension(
                column_key=_column_key(ugly_graph, "CATART", "CAT"),
                edge_path=[_edge_key(ugly_graph, "FK_DORIG_ARTICO"), _edge_key(ugly_graph, "FK_ARTICO_CATART")],
                safety="safe",
            )
        ],
        required_edges=[_edge_key(ugly_graph, "FK_DORIG_ARTICO"), _edge_key(ugly_graph, "FK_ARTICO_CATART")],
    )
    ugly_preflight = _preflight(ugly_intent, ugly_layer, ugly_graph, ugly_snapshot)
    ugly_compiled = compile_query_plan(ugly_intent, ugly_preflight, ugly_layer, ugly_graph, ugly_snapshot)
    ugly_report = validate_compiled_query_result_contract(ugly_compiled, ugly_intent, ugly_preflight, ugly_layer, ugly_graph, ugly_snapshot)
    assert ugly_report.status in {"valid", "valid_with_warnings"}

    composite_graph = _composite_multischema_graph()
    composite_snapshot = _snapshot_from_graph(composite_graph)
    composite_layer = _layer_with_concept(_active_layer(_empty_layer_for(composite_graph)), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "quantity_sold")
    composite_metric = _semantic_metric(
        composite_graph,
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
    composite_layer = _layer_with_metrics(composite_layer, [composite_metric])
    composite_intent = _intent(composite_metric, concept_ref="quantity_sold", date_column=_column_key(composite_graph, "DOC_HEAD", "DOC_DATE"))
    composite_preflight = _preflight(composite_intent, composite_layer, composite_graph, composite_snapshot)
    composite_compiled = compile_query_plan(composite_intent, composite_preflight, composite_layer, composite_graph, composite_snapshot)
    composite_report = validate_compiled_query_result_contract(composite_compiled, composite_intent, composite_preflight, composite_layer, composite_graph, composite_snapshot)
    assert composite_report.status in {"valid", "valid_with_warnings"}
    assert " AND " in composite_compiled.sql
    assert len(composite_compiled.trace.join_predicates) == 1
    assert [pair.ordinal for pair in composite_compiled.trace.join_predicates[0].column_pairs] == [1, 2]

    weird_graph = build(
        snapshot(
            tables=[
                table("Select Table]", [column("ID", 1), column("amount value]", 2, role="money_candidate", native_type="money")], primary_key=["ID"]),
            ]
        )
    )
    weird_snapshot = _snapshot_from_graph(weird_graph)
    weird_layer = _layer_with_concept(_active_layer(_empty_layer_for(weird_graph)), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "amount_metric")
    weird_metric = _semantic_metric(
        weird_graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="amount_metric",
        variant="base",
        table_name="Select Table]",
        measure_column="amount value]",
        grain_columns=["ID"],
        value_type="currency",
    )
    weird_layer = _layer_with_metrics(weird_layer, [weird_metric])
    weird_intent = _intent(weird_metric, concept_ref="amount_metric")
    weird_preflight = _preflight(weird_intent, weird_layer, weird_graph, weird_snapshot)
    weird_compiled = compile_query_plan(weird_intent, weird_preflight, weird_layer, weird_graph, weird_snapshot)
    weird_report = validate_compiled_query_result_contract(weird_compiled, weird_intent, weird_preflight, weird_layer, weird_graph, weird_snapshot)
    assert weird_report.status in {"valid", "valid_with_warnings"}
    assert "[Select Table]]]" in weird_compiled.sql

    view_graph = _view_graph()
    view_snapshot = _snapshot_from_graph(view_graph)
    view_layer = _layer_with_concept(_active_layer(_empty_layer_for(view_graph)), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "rows")
    view_metric = _semantic_metric(
        view_graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="rows",
        variant="view_count",
        table_name="VW_DOC",
        measure_column="ID",
        grain_columns=["ID"],
        value_type="count",
    )
    view_layer = _layer_with_metrics(view_layer, [view_metric])
    view_intent = _intent(view_metric, concept_ref="rows")
    view_preflight = _preflight(view_intent, view_layer, view_graph, view_snapshot, policy={"allow_view_backed_metrics": True})
    view_compiled = compile_query_plan(view_intent, view_preflight, view_layer, view_graph, view_snapshot)
    view_report = validate_compiled_query_result_contract(view_compiled, view_intent, view_preflight, view_layer, view_graph, view_snapshot)
    assert view_report.status in {"valid", "valid_with_warnings"}


def test_corrupted_sql_reports_clause_level_mismatches_and_collects_multiple_issues() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato per categoria prodotto", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    corrupted_sql = (
        compiled.sql.replace("LineTotal", "ProductID", 1)
        .replace("ORDER BY [metric_value] DESC, [dimension_0] ASC", "ORDER BY [dimension_0] DESC")
        .replace("GROUP BY", "WHERE [t0].[Injected] = 'A'\nGROUP BY")
    )
    corrupted = replace(
        compiled,
        sql=corrupted_sql,
        parameters=[
            replace(compiled.parameters[0], value=999),
            *compiled.parameters[1:],
            CompiledSqlParameter(name="@p99", value="A", logical_type="string", source="filter", operator="eq", context="manual"),
        ],
    )

    report = validate_compiled_query_result_contract(corrupted, intent, preflight, layer, graph, schema_snapshot)
    codes = _codes(report)

    assert report.status == "blocked"
    assert "CANONICAL_SELECT_MISMATCH" in codes
    assert "CANONICAL_ORDER_BY_MISMATCH" in codes
    assert "CANONICAL_WHERE_MISMATCH" in codes
    assert "CANONICAL_PARAMETER_MISMATCH" in codes
    assert len(report.errors) > 1


def test_corrupted_sql_and_trace_together_still_block_against_preflight_semantic_graph_snapshot() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato per categoria prodotto", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    wrong_column = next(
        ref
        for ref in compiled.trace.selected_columns
        if ref.key != compiled.trace.measure_column_key
    )
    wrong_table = next(ref for ref in compiled.trace.selected_tables if ref.key != compiled.trace.source_table_key)
    corrupted_trace = replace(
        compiled.trace,
        source_table_key=wrong_table.key,
        measure_column_key=wrong_column.key,
        selected_columns=[wrong_column],
        where_clauses_structured=[
            *compiled.trace.where_clauses_structured,
            {"column_key": wrong_column.key, "operator": "eq", "parameter": "@p999"},
        ],
        dimension_keys=[wrong_column.key],
    )
    corrupted = replace(
        compiled,
        sql=compiled.sql.replace("LineTotal", wrong_column.physical_label.split(".")[-1], 1)
        .replace("FROM ", f"FROM [{wrong_table.physical_label.split('.')[0]}].[{wrong_table.physical_label.split('.')[1]}] AS [t0]\nFROM ", 1)
        .replace("GROUP BY", "WHERE [t0].[Injected] = @p999\nGROUP BY"),
        trace=corrupted_trace,
        parameters=[
            *compiled.parameters,
            CompiledSqlParameter(name="@p999", value="X", logical_type="string", source="filter", operator="eq", context=wrong_column.key),
        ],
    )

    report = validate_compiled_query_result_contract(corrupted, intent, preflight, layer, graph, schema_snapshot)
    codes = _codes(report)

    assert report.status == "blocked"
    assert "VALIDATION_CONTEXT_MISMATCH" in codes
    assert "COMPILER_TRACE_MISMATCH" in codes
    assert "CANONICAL_SELECT_MISMATCH" in codes
    assert "CANONICAL_WHERE_MISMATCH" in codes


def test_sql_guardrails_block_dml_comments_and_multiple_statements() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)
    corrupted = replace(compiled, sql=f"{compiled.sql};\n-- DROP TABLE x\nDELETE FROM [x]")

    report = validate_compiled_query_result_contract(corrupted, intent, preflight, layer, graph, schema_snapshot)
    codes = _codes(report)

    assert report.status == "blocked"
    assert "SQL_MULTIPLE_STATEMENTS" in codes
    assert "SQL_COMMENT_PAYLOAD_FORBIDDEN" in codes
    assert "SQL_DDL_DML_FORBIDDEN" in codes


def test_integrity_unknown_dialect_not_compiled_and_raw_sql_payload_block() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    unknown_dialect = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot, dialect="postgres")
    assert unknown_dialect.status == "blocked"
    assert "UNKNOWN_DIALECT" in _codes(unknown_dialect)

    not_compiled = replace(compiled, status="blocked", sql=None)
    not_compiled_report = validate_compiled_query_result_contract(not_compiled, intent, preflight, layer, graph, schema_snapshot)
    assert not_compiled_report.status == "blocked"
    assert {"COMPILER_NOT_COMPILED", "COMPILED_SQL_MISSING"}.issubset(_codes(not_compiled_report))

    raw_intent = intent.model_copy(update={"message": "-- DROP TABLE hidden"})
    raw_report = validate_compiled_query_result_contract(compiled, raw_intent, preflight, layer, graph, schema_snapshot)
    assert raw_report.status == "blocked"
    assert "RAW_SQL_LEAK" in _codes(raw_report)


def test_parameter_metadata_changes_and_literal_interpolation_block() -> None:
    graph = _header_detail_graph(with_fk=True)
    schema_snapshot = _snapshot_from_graph(graph)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "revenue",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="line_detail",
        table_name="DORIG",
        measure_column="IMPORTO",
        grain_columns=["IDRIG"],
        date_column=("DOTES", "DATA_DOC"),
        required_edges=["FK_DORIG_DOTES"],
        value_type="currency",
        eligibility="eligible_with_disclosure",
    )
    layer = _layer_with_metrics(layer, [metric])
    filters = [
        SemanticFilter(column_key=_column_key(graph, "DORIG", "STATO"), operator="eq", value="APPROVED", value_type="string"),
    ]
    intent = _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC"), filters=filters)
    preflight = _preflight(intent, layer, graph, schema_snapshot, policy={"status_scope": "include_all_with_disclosure"})
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    changed_metadata = replace(
        compiled,
        parameters=[
            replace(compiled.parameters[0], logical_type="string"),
            *compiled.parameters[1:],
        ],
    )
    metadata_report = validate_compiled_query_result_contract(changed_metadata, intent, preflight, layer, graph, schema_snapshot)
    assert metadata_report.status == "blocked"
    assert "CANONICAL_PARAMETER_MISMATCH" in _codes(metadata_report)

    interpolated = replace(compiled, sql=compiled.sql.replace("@p2", "'APPROVED'"))
    interpolated_report = validate_compiled_query_result_contract(interpolated, intent, preflight, layer, graph, schema_snapshot)
    assert interpolated_report.status == "blocked"
    assert "FILTER_VALUE_INTERPOLATED" in _codes(interpolated_report)


def test_trace_join_and_snapshot_fk_corruption_blocks() -> None:
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
    corrupted_sql = compiled.sql.replace(" AND [t0].[DOC_ID] = [t1].[DOC_ID]", "")
    corrupted = replace(compiled, sql=corrupted_sql)

    report = validate_compiled_query_result_contract(corrupted, intent, preflight, layer, graph, schema_snapshot)
    assert "CANONICAL_JOIN_MISMATCH" in _codes(report)

    dropped_pair_predicate = replace(
        compiled.trace.join_predicates[0],
        column_pairs=compiled.trace.join_predicates[0].column_pairs[:1],
    )
    dropped_pair_trace = replace(compiled.trace, join_predicates=[dropped_pair_predicate])
    dropped_pair_report = validate_compiled_query_result_contract(
        replace(compiled, sql=corrupted_sql, trace=dropped_pair_trace),
        intent,
        preflight,
        layer,
        graph,
        schema_snapshot,
    )
    dropped_pair_codes = _codes(dropped_pair_report)
    assert "CANONICAL_JOIN_MISMATCH" in dropped_pair_codes
    assert "JOIN_PAIR_ORDER_INVALID" in dropped_pair_codes

    no_predicate_trace = replace(compiled.trace, join_predicates=[])
    no_predicate_report = validate_compiled_query_result_contract(
        replace(compiled, trace=no_predicate_trace),
        intent,
        preflight,
        layer,
        graph,
        schema_snapshot,
    )
    assert "JOIN_PREDICATE_TRACE_MISSING" in _codes(no_predicate_report)

    extra_sql_predicate = replace(
        compiled,
        sql=compiled.sql.replace(
            "[t0].[DOC_ID] = [t1].[DOC_ID]",
            "[t0].[DOC_ID] = [t1].[DOC_ID] AND [t0].[LINE_NO] = [t1].[DOC_ID]",
        ),
    )
    extra_sql_report = validate_compiled_query_result_contract(extra_sql_predicate, intent, preflight, layer, graph, schema_snapshot)
    assert "CANONICAL_JOIN_MISMATCH" in _codes(extra_sql_report)

    extra_trace_predicate = replace(
        compiled,
        trace=replace(
            compiled.trace,
            join_predicates=[
                *compiled.trace.join_predicates,
                compiled.trace.join_predicates[0],
            ],
        ),
    )
    extra_trace_report = validate_compiled_query_result_contract(extra_trace_predicate, intent, preflight, layer, graph, schema_snapshot)
    assert "TRACE_JOIN_MISMATCH" in _codes(extra_trace_report)

    swapped_pair_predicate = replace(
        compiled.trace.join_predicates[0],
        column_pairs=list(reversed(compiled.trace.join_predicates[0].column_pairs)),
    )
    swapped_pair_report = validate_compiled_query_result_contract(
        replace(compiled, trace=replace(compiled.trace, join_predicates=[swapped_pair_predicate])),
        intent,
        preflight,
        layer,
        graph,
        schema_snapshot,
    )
    assert "JOIN_PAIR_ORDER_INVALID" in _codes(swapped_pair_report)

    alias_mismatch_predicate = replace(compiled.trace.join_predicates[0], from_alias="tx")
    alias_mismatch_report = validate_compiled_query_result_contract(
        replace(compiled, trace=replace(compiled.trace, join_predicates=[alias_mismatch_predicate])),
        intent,
        preflight,
        layer,
        graph,
        schema_snapshot,
    )
    assert "ALIAS_REFERENCE_INVALID" in _codes(alias_mismatch_report)

    bad_snapshot = deepcopy(schema_snapshot)
    bad_snapshot.foreign_keys[0].from_columns = ["DOC_ID"]
    bad_report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, bad_snapshot)
    assert "JOIN_PAIR_ORDER_INVALID" in _codes(bad_report)


def test_join_contract_blocks_missing_fk_untrusted_fk_lineage_and_bridge_paths() -> None:
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

    missing_fk_snapshot = deepcopy(schema_snapshot)
    missing_fk_snapshot.foreign_keys = []
    missing_fk_report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, missing_fk_snapshot)
    assert "JOIN_FK_NOT_IN_SNAPSHOT" in _codes(missing_fk_report)

    untrusted_graph = graph.model_copy(
        update={
            "edges": [
                edge.model_copy(update={"validation_status": "untrusted"})
                if getattr(edge, "edge_type", None) == "fk_join"
                else edge
                for edge in graph.edges
            ]
        }
    )
    untrusted_report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, untrusted_graph, schema_snapshot)
    assert "JOIN_FK_UNTRUSTED" in _codes(untrusted_report)

    bridge_graph = graph.model_copy(
        update={
            "nodes": [
                node.model_copy(update={"bridge_candidate": True})
                if node.object_name == "DOC_HEAD"
                else node
                for node in graph.nodes
            ]
        }
    )
    bridge_report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, bridge_graph, schema_snapshot)
    assert "JOIN_BRIDGE_M2M_FORBIDDEN" in _codes(bridge_report)

    view_graph = _view_graph()
    view_snapshot = _snapshot_from_graph(view_graph)
    view_layer = _layer_with_concept(_active_layer(_empty_layer_for(view_graph)), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "rows")
    view_metric = _semantic_metric(
        view_graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="rows",
        variant="view_count",
        table_name="VW_DOC",
        measure_column="ID",
        grain_columns=["ID"],
        value_type="count",
    )
    view_layer = _layer_with_metrics(view_layer, [view_metric])
    view_intent = _intent(view_metric, concept_ref="rows")
    view_preflight = _preflight(view_intent, view_layer, view_graph, view_snapshot, policy={"allow_view_backed_metrics": True})
    view_compiled = compile_query_plan(view_intent, view_preflight, view_layer, view_graph, view_snapshot)
    lineage_edge_key = next(edge.edge_key for edge in view_graph.edges)
    lineage_intent = _intent(view_metric, concept_ref="rows", required_edges=[lineage_edge_key])
    lineage_report = validate_compiled_query_result_contract(view_compiled, lineage_intent, view_preflight, view_layer, view_graph, view_snapshot)
    assert "JOIN_USES_LINEAGE" in _codes(lineage_report)


def test_invalid_count_contract_blocks_without_compiler_tautology() -> None:
    source = snapshot(
        tables=[
            table(
                "COUNT_SRC",
                [
                    column("ID", 1),
                    column("COUNT_COL", 2),
                ],
                primary_key=["ID"],
            )
        ]
    )
    graph = build(source)
    base_layer = _layer_with_concept(_active_layer(_empty_layer_for(graph)), "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "orders")
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="orders",
        variant="header_count",
        table_name="COUNT_SRC",
        measure_column="COUNT_COL",
        grain_columns=["ID"],
        value_type="count",
    )
    row_count = metric.model_copy(update={"aggregation": "count", "measure_column_key": None, "aggregation_level": "entity"})
    row_layer = _layer_with_metrics(base_layer, [row_count])
    row_intent = _intent(row_count, concept_ref="orders")
    row_preflight = _preflight(row_intent, row_layer, graph, source, policy={"status_scope": "include_all_with_disclosure"})
    row_compiled = compile_query_plan(row_intent, row_preflight, row_layer, graph, source)

    invalid_count = row_count.model_copy(update={"format": SemanticMetricFormat(value_type="number", currency=None, decimals=0)})
    invalid_layer = _layer_with_metrics(base_layer, [invalid_count])
    invalid_intent = _intent(invalid_count, concept_ref="orders")
    report = validate_compiled_query_result_contract(row_compiled, invalid_intent, row_preflight, invalid_layer, graph, source)

    assert report.status == "blocked"
    assert "COUNT_BIG_NOT_ALLOWED" in _codes(report)


def test_grouped_result_alias_group_order_and_limit_contract_are_enforced() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato per categoria prodotto", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    missing_dimension_alias = replace(compiled, sql=compiled.sql.replace(" AS [dimension_0]", " AS [wrong_dimension]", 1))
    alias_report = validate_compiled_query_result_contract(missing_dimension_alias, intent, preflight, layer, graph, schema_snapshot)
    assert "CANONICAL_SELECT_MISMATCH" in _codes(alias_report)

    missing_limit = replace(
        compiled,
        sql=compiled.sql.replace("SELECT TOP (@p0)\n", "SELECT\n", 1),
        parameters=compiled.parameters[1:],
    )
    limit_report = validate_compiled_query_result_contract(missing_limit, intent, preflight, layer, graph, schema_snapshot)
    assert "CANONICAL_SELECT_MISMATCH" in _codes(limit_report)
    assert "LIMIT_PARAMETER_MISSING" in _codes(limit_report)


def test_missing_core_objects_and_side_effect_free_validation() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    intent = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(intent, layer, graph, schema_snapshot)
    compiled = compile_query_plan(intent, preflight, layer, graph, schema_snapshot)

    before = (
        deepcopy(compiled),
        deepcopy(intent),
        deepcopy(preflight),
        deepcopy(layer),
        deepcopy(graph),
        deepcopy(schema_snapshot),
    )
    report = validate_compiled_query_result_contract(compiled, intent, preflight, layer, graph, schema_snapshot)
    after = (compiled, intent, preflight, layer, graph, schema_snapshot)

    assert report.status in {"valid", "valid_with_warnings"}
    assert before == after

    missing_report = validate_compiled_query_result_contract(None, intent, preflight, layer, graph, schema_snapshot)
    assert missing_report.status == "blocked"
    assert "COMPILER_RESULT_MISSING" in _codes(missing_report)


def test_result_validator_module_has_no_demo_literals_execution_or_compiler_reentry() -> None:
    source = Path("app/query_result_validator.py").read_text(encoding="utf-8")

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
    assert "compile_query_plan(" not in source


def _codes(report) -> set[str]:
    return {issue.code for issue in [*report.errors, *report.warnings, *report.infos]}
