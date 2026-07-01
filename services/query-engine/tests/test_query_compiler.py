from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.drivers.base import (
    SchemaColumnMetadata,
    SchemaForeignKeyMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
)
from app.models import (
    Engine,
    QueryIntentGroupByDimension,
    QueryIntentResult,
    QueryIntentTimeRange,
    SemanticFilter,
    SemanticMetricFormat,
)
from app.query_compiler import compile_query_plan
from app.query_compiler_preflight import validate_query_compiler_preflight
from app.query_intent import resolve_query_intent
from tests.test_query_compiler_preflight import (
    _active_layer,
    _bridge_graph,
    _column_key,
    _composite_multischema_graph,
    _edge_key,
    _empty_layer_for,
    _graph_report,
    _header_detail_graph,
    _intent,
    _layer_with_concept,
    _layer_with_metrics,
    _semantic_invariant_report,
    _semantic_metric,
    _ugly_pmi_snapshot,
    _view_graph,
)
from tests.test_query_intent import active_adventureworks_layer, request_for
from tests.test_queryability_builder import build, column, foreign_key, snapshot, table
from tests.test_semantic_builder import adventureworks_graph


def test_header_metric_with_date_range_compiles_half_open_parameterized_sql() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    result = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(result, layer, graph, schema_snapshot)

    compiled = compile_query_plan(result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "compiled"
    assert compiled.sql is not None
    assert "SUM(" in compiled.sql
    assert " >= @p0" in compiled.sql
    assert " < @p1" in compiled.sql
    assert "TOP" not in compiled.sql
    assert [param.name for param in compiled.parameters] == ["@p0", "@p1"]
    assert [param.source for param in compiled.parameters] == ["date_range", "date_range"]
    assert "fatturato" not in compiled.sql.lower()


def test_line_metric_by_category_uses_trusted_path_group_shape_and_not_header_amount() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    result = resolve_query_intent(request_for("fatturato per categoria prodotto", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(result, layer, graph, schema_snapshot)

    compiled = compile_query_plan(result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "compiled"
    assert compiled.sql is not None
    assert "SELECT TOP (@p0)" in compiled.sql
    assert "AS [dimension_0]" in compiled.sql
    assert "AS [metric_value]" in compiled.sql
    assert "GROUP BY" in compiled.sql
    assert "ORDER BY [metric_value] DESC, [dimension_0] ASC" in compiled.sql
    assert "JOIN" in compiled.sql
    assert "LineTotal" in compiled.sql
    assert "SubTotal" not in compiled.sql
    assert "TotalDue" not in compiled.sql
    assert len(compiled.trace.join_predicates) == len(compiled.trace.join_paths)
    assert all(predicate.source == "graph_fk" for predicate in compiled.trace.join_predicates)
    assert all(predicate.join_type == "inner" for predicate in compiled.trace.join_predicates)
    assert compiled.parameters[0].source == "limit"
    assert compiled.parameters[0].value == 500


def test_ugly_schema_with_explicit_evidence_compiles_without_demo_hardcoding() -> None:
    schema_snapshot = _ugly_pmi_snapshot()
    graph = build(schema_snapshot)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "quantity_sold",
    )
    metric = _semantic_metric(
        graph,
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
    result = _intent(
        metric,
        concept_ref="quantity_sold",
        group_by=[
            QueryIntentGroupByDimension(
                column_key=_column_key(graph, "CATART", "CAT"),
                edge_path=[_edge_key(graph, "FK_DORIG_ARTICO"), _edge_key(graph, "FK_ARTICO_CATART")],
                safety="safe",
            )
        ],
        required_edges=[_edge_key(graph, "FK_DORIG_ARTICO"), _edge_key(graph, "FK_ARTICO_CATART")],
    )
    layer = _layer_with_metrics(layer, [metric])
    preflight = _preflight(result, layer, graph, schema_snapshot)

    compiled = compile_query_plan(result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "compiled"
    assert compiled.sql is not None
    assert "[SalesOrder" not in compiled.sql
    assert "ProductCategory" not in compiled.sql
    assert "[SalesLT].[DORIG]" in compiled.sql
    assert "[SalesLT].[CATART]" in compiled.sql
    assert [predicate.edge_key for predicate in compiled.trace.join_predicates] == [
        _edge_key(graph, "FK_DORIG_ARTICO"),
        _edge_key(graph, "FK_ARTICO_CATART"),
    ]


def test_structured_filters_expand_parameters_and_reject_invalid_shapes() -> None:
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
    status_filter = SemanticFilter(
        column_key=_column_key(graph, "DORIG", "STATO"),
        operator="in",
        value=["A", "B", "C"],
        value_type="string",
    )
    result = _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC"), filters=[status_filter])
    preflight = _preflight(result, layer, graph, schema_snapshot, policy={"status_scope": "include_all_with_disclosure"})

    compiled = compile_query_plan(result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "compiled"
    assert "IN (@p2, @p3, @p4)" in compiled.sql
    assert [param.value for param in compiled.parameters[2:]] == ["A", "B", "C"]
    assert len(compiled.trace.join_predicates) == 1
    predicate = compiled.trace.join_predicates[0]
    assert predicate.traversal_direction == "forward"
    assert predicate.constraint_name == "FK_DORIG_DOTES"
    assert len(predicate.column_pairs) == 1
    assert predicate.column_pairs[0].sql_left_identifier in compiled.sql
    assert predicate.column_pairs[0].sql_right_identifier in compiled.sql

    invalid_filter = status_filter.model_copy(update={"operator": "eq", "value": None})
    invalid_result = _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC"), filters=[invalid_filter])
    blocked_preflight = validate_query_compiler_preflight(
        invalid_result,
        layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        schema_snapshot=schema_snapshot,
        policy={"status_scope": "include_all_with_disclosure"},
    )
    corrupted_accepted_preflight = replace(
        blocked_preflight,
        status="ready",
        decision_category="safe",
        errors=[],
        warnings=[],
        blocking_codes=[],
    )
    invalid = compile_query_plan(invalid_result, corrupted_accepted_preflight, layer, graph, schema_snapshot)

    assert invalid.status == "blocked"
    assert "FILTER_NULL_OPERATOR_INVALID" in _compiler_codes(invalid)


def test_composite_multischema_fk_preserves_pair_order_and_schema_qualification() -> None:
    graph = _composite_multischema_graph()
    schema_snapshot = _snapshot_from_graph(graph)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "quantity_sold",
    )
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
    result = _intent(metric, concept_ref="quantity_sold", date_column=_column_key(graph, "DOC_HEAD", "DOC_DATE"))
    layer = _layer_with_metrics(layer, [metric])
    preflight = _preflight(result, layer, graph, schema_snapshot)

    compiled = compile_query_plan(result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "compiled"
    assert "[azienda].[DOC_LINE]" in compiled.sql
    assert "[azienda].[DOC_HEAD]" in compiled.sql
    assert "[t0].[COMPANY_ID] = [t1].[COMPANY_ID] AND [t0].[DOC_ID] = [t1].[DOC_ID]" in compiled.sql
    assert len(compiled.trace.join_predicates) == 1
    predicate = compiled.trace.join_predicates[0]
    assert predicate.from_schema == "azienda"
    assert predicate.to_schema == "azienda"
    assert predicate.from_table == "DOC_LINE"
    assert predicate.to_table == "DOC_HEAD"
    assert predicate.traversal_direction == "forward"
    assert [pair.ordinal for pair in predicate.column_pairs] == [1, 2]
    assert [pair.from_physical_column for pair in predicate.column_pairs] == ["COMPANY_ID", "DOC_ID"]
    assert [pair.to_physical_column for pair in predicate.column_pairs] == ["COMPANY_ID", "DOC_ID"]
    assert [pair.sql_left_identifier for pair in predicate.column_pairs] == ["[t0].[COMPANY_ID]", "[t0].[DOC_ID]"]
    assert [pair.sql_right_identifier for pair in predicate.column_pairs] == ["[t1].[COMPANY_ID]", "[t1].[DOC_ID]"]


def test_reverse_fk_traversal_materializes_join_predicate_direction() -> None:
    graph = _composite_multischema_graph()
    schema_snapshot = _snapshot_from_graph(graph)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "document_total",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="document_total",
        variant="header_total",
        table_name="DOC_HEAD",
        measure_column="DOC_ID",
        grain_columns=["COMPANY_ID", "DOC_ID"],
        dimension_column=("DOC_LINE", "LINE_NO"),
        dimension_edges=["FK_LINE_HEAD"],
        value_type="number",
    )
    result = _intent(
        metric,
        concept_ref="document_total",
        group_by=[
            QueryIntentGroupByDimension(
                column_key=_column_key(graph, "DOC_LINE", "LINE_NO"),
                edge_path=[_edge_key(graph, "FK_LINE_HEAD")],
                safety="safe",
            )
        ],
        required_edges=[_edge_key(graph, "FK_LINE_HEAD")],
    )
    layer = _layer_with_metrics(layer, [metric])
    blocked_preflight = validate_query_compiler_preflight(
        result,
        layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        schema_snapshot=schema_snapshot,
        policy={"status_scope": "include_all_with_disclosure"},
    )
    accepted_preflight = replace(
        blocked_preflight,
        status="ready",
        decision_category="safe",
        errors=[],
        warnings=[],
        blocking_codes=[],
    )

    compiled = compile_query_plan(result, accepted_preflight, layer, graph, schema_snapshot)

    assert compiled.status == "compiled"
    assert len(compiled.trace.join_predicates) == 1
    predicate = compiled.trace.join_predicates[0]
    assert predicate.traversal_direction == "reverse"
    assert predicate.from_table == "DOC_LINE"
    assert predicate.to_table == "DOC_HEAD"
    assert [pair.ordinal for pair in predicate.column_pairs] == [1, 2]
    assert "[t1].[COMPANY_ID] = [t0].[COMPANY_ID] AND [t1].[DOC_ID] = [t0].[DOC_ID]" in compiled.sql


def test_count_semantics_are_explicit_and_never_choose_grain_column_silently() -> None:
    source = snapshot(
        tables=[
            table(
                "COUNT_SRC",
                [
                    column("ID", 1),
                    column("COUNT_COL", 2),
                    column("NULLABLE_COUNT_COL", 3, nullable=True),
                ],
                primary_key=["ID"],
            )
        ]
    )
    graph = build(source)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "orders",
    )
    base_metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="orders",
        variant="header_count",
        table_name="COUNT_SRC",
        measure_column="COUNT_COL",
        grain_columns=["ID"],
        value_type="count",
    )
    count_column = base_metric.model_copy(update={"aggregation": "count"})
    row_count = count_column.model_copy(update={"measure_column_key": None, "aggregation": "count", "aggregation_level": "entity"})
    nullable_count = count_column.model_copy(update={"measure_column_key": _column_key(graph, "COUNT_SRC", "NULLABLE_COUNT_COL")})
    no_evidence = count_column.model_copy(
        update={
            "measure_column_key": None,
            "format": SemanticMetricFormat(value_type="number", currency=None, decimals=0),
        }
    )

    row_layer = _layer_with_metrics(layer, [row_count])
    row_result = _intent(row_count, concept_ref="orders")
    row_preflight = _preflight(row_result, row_layer, graph, source, policy={"status_scope": "include_all_with_disclosure"})
    row_compiled = compile_query_plan(row_result, row_preflight, row_layer, graph, source)

    column_layer = _layer_with_metrics(layer, [count_column])
    column_result = _intent(count_column, concept_ref="orders")
    column_preflight = _preflight(column_result, column_layer, graph, source, policy={"status_scope": "include_all_with_disclosure"})
    column_compiled = compile_query_plan(column_result, column_preflight, column_layer, graph, source)

    nullable_layer = _layer_with_metrics(layer, [nullable_count])
    nullable_result = _intent(nullable_count, concept_ref="orders")
    nullable_preflight = _preflight(nullable_result, nullable_layer, graph, source, policy={"status_scope": "include_all_with_disclosure"})
    nullable_compiled = compile_query_plan(nullable_result, nullable_preflight, nullable_layer, graph, source)

    no_evidence_layer = _layer_with_metrics(layer, [no_evidence])
    no_evidence_result = _intent(no_evidence, concept_ref="orders")
    no_evidence_preflight = _preflight(no_evidence_result, no_evidence_layer, graph, source, policy={"status_scope": "include_all_with_disclosure"})
    no_evidence_compiled = compile_query_plan(no_evidence_result, no_evidence_preflight, no_evidence_layer, graph, source)

    assert row_compiled.status == "compiled"
    assert "COUNT_BIG(*)" in row_compiled.sql
    assert column_compiled.status == "compiled"
    assert "COUNT([t0].[COUNT_COL])" in column_compiled.sql
    assert nullable_compiled.status == "blocked"
    assert "COUNT_COLUMN_NULLABLE" in _compiler_codes(nullable_compiled)
    assert no_evidence_compiled.status == "blocked"
    assert "COUNT_TARGET_NOT_DECLARED" in _compiler_codes(no_evidence_compiled)


def test_binding_replay_hash_and_reference_mismatches_block() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    result = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(result, layer, graph, schema_snapshot)

    other_result = resolve_query_intent(request_for("clienti in anagrafica", layer=layer))
    replay = compile_query_plan(other_result, preflight, layer, graph, schema_snapshot)

    stale_trace = replace(
        preflight.plan_trace,
        cache_key_inputs_preview={
            **preflight.plan_trace.cache_key_inputs_preview,
            "semantic_hash": "c" * 64,
        },
    )
    stale_preflight = replace(preflight, plan_trace=stale_trace)
    stale = compile_query_plan(result, stale_preflight, layer, graph, schema_snapshot)

    assert replay.status == "blocked"
    assert "PREFLIGHT_CONTEXT_MISMATCH" in _compiler_codes(replay)
    assert stale.status == "blocked"
    assert "PREFLIGHT_CONTEXT_MISMATCH" in _compiler_codes(stale)


def test_filter_value_replay_mismatch_blocks() -> None:
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
    original_filter = SemanticFilter(
        column_key=_column_key(graph, "DORIG", "STATO"),
        operator="eq",
        value="A",
        value_type="string",
    )
    changed_filter = original_filter.model_copy(update={"value": "B"})
    original_result = _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC"), filters=[original_filter])
    changed_result = _intent(metric, concept_ref="revenue", date_column=_column_key(graph, "DOTES", "DATA_DOC"), filters=[changed_filter])
    preflight = _preflight(original_result, layer, graph, schema_snapshot, policy={"status_scope": "include_all_with_disclosure"})

    compiled = compile_query_plan(changed_result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "blocked"
    assert "PREFLIGHT_CONTEXT_MISMATCH" in _compiler_codes(compiled)


def test_non_accepted_preflight_snapshot_missing_and_unknown_dialect_block() -> None:
    graph = adventureworks_graph()
    layer = active_adventureworks_layer()
    result = resolve_query_intent(request_for("fatturato 2008", layer=layer))
    schema_snapshot = _snapshot_from_graph(graph)
    preflight = _preflight(result, layer, graph, schema_snapshot)
    needs_policy = replace(preflight, decision_category="needs_policy")

    assert compile_query_plan(result, None, layer, graph, schema_snapshot).status == "blocked"
    assert compile_query_plan(result, preflight, layer, graph, None).status == "blocked"
    assert compile_query_plan(result, needs_policy, layer, graph, schema_snapshot).status == "blocked"
    unknown = compile_query_plan(result, preflight, layer, graph, schema_snapshot, dialect="postgres")
    assert unknown.status == "blocked"
    assert "UNKNOWN_DIALECT" in _compiler_codes(unknown)


def test_preflight_blocked_safety_cases_remain_blocked_at_compiler_boundary() -> None:
    bridge_graph = _bridge_graph()
    bridge_layer = _layer_with_concept(
        _active_layer(_empty_layer_for(bridge_graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "orders",
    )
    bridge_metric = _semantic_metric(
        bridge_graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="orders",
        variant="bridge_count",
        table_name="CUSTOMER_PRODUCT",
        measure_column="CUSTOMER_ID",
        grain_columns=["CUSTOMER_ID", "PRODUCT_ID"],
        dimension_column=("PRODUCT", "PRODUCT_ID"),
        dimension_edges=["FK_BRIDGE_PRODUCT"],
        value_type="count",
    )
    bridge_result = _intent(
        bridge_metric,
        concept_ref="orders",
        group_by=[
            QueryIntentGroupByDimension(
                column_key=_column_key(bridge_graph, "PRODUCT", "PRODUCT_ID"),
                edge_path=[_edge_key(bridge_graph, "FK_BRIDGE_PRODUCT")],
                safety="safe",
            )
        ],
        required_edges=[_edge_key(bridge_graph, "FK_BRIDGE_PRODUCT")],
    )
    bridge_preflight = validate_query_compiler_preflight(
        bridge_result,
        _layer_with_metrics(bridge_layer, [bridge_metric]),
        bridge_graph,
        _graph_report(),
        _semantic_invariant_report(),
        schema_snapshot=_snapshot_from_graph(bridge_graph),
    )

    compiled = compile_query_plan(bridge_result, bridge_preflight, _layer_with_metrics(bridge_layer, [bridge_metric]), bridge_graph, _snapshot_from_graph(bridge_graph))

    assert bridge_preflight.status == "blocked"
    assert compiled.status == "blocked"
    assert "PREFLIGHT_NOT_ACCEPTED" in _compiler_codes(compiled)
    assert compiled.trace.join_predicates == []


def test_cross_table_filter_without_selected_path_blocks() -> None:
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
        value_type="currency",
        eligibility="eligible_with_disclosure",
    )
    filter_item = SemanticFilter(
        column_key=_column_key(graph, "DOTES", "DATA_DOC"),
        operator="gte",
        value="2024-01-01",
        value_type="date",
    )
    result = _intent(metric, concept_ref="revenue", filters=[filter_item], required_edges=[])
    layer = _layer_with_metrics(layer, [metric])
    preflight = _preflight(result, layer, graph, schema_snapshot, policy={"status_scope": "include_all_with_disclosure"})

    compiled = compile_query_plan(result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "blocked"
    assert "FILTER_PATH_NOT_SELECTED" in _compiler_codes(compiled)


def test_identifier_escaping_handles_reserved_spaces_and_closing_brackets() -> None:
    source = SchemaIntrospectionResult(
        engine=Engine.sqlserver,
        database_name="ERP",
        engine_version="16.0",
        schema_hash="a" * 64,
        snapshot_hash="b" * 64,
        coverage_status="ok",
        tables=[
            SchemaTableMetadata(
                table_schema="odd schema",
                name="select table]x",
                table_type="base_table",
                columns=[
                    SchemaColumnMetadata(name="id key", data_type="int", native_type="int", normalized_type="int", ordinal_position=1, is_nullable=False, technical_role="identifier"),
                    SchemaColumnMetadata(name="gross amount]x", data_type="money", native_type="money", normalized_type="money", ordinal_position=2, is_nullable=False, technical_role="money_candidate"),
                ],
                primary_key=SchemaPrimaryKeyMetadata(name="PK odd", columns=["id key"]),
            )
        ],
        foreign_keys=[],
    )
    graph = build(source)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "revenue",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="revenue",
        variant="generic_revenue",
        table_name="select table]x",
        measure_column="gross amount]x",
        grain_columns=["id key"],
        value_type="currency",
        eligibility="eligible_with_disclosure",
    )
    result = _intent(metric, concept_ref="revenue")
    layer = _layer_with_metrics(layer, [metric])
    preflight = _preflight(result, layer, graph, source)

    compiled = compile_query_plan(result, preflight, layer, graph, source)

    assert compiled.status == "compiled"
    assert "[odd schema].[select table]]x]" in compiled.sql
    assert "[t0].[gross amount]]x]" in compiled.sql


def test_view_source_can_compile_but_lineage_path_cannot() -> None:
    graph = _view_graph()
    schema_snapshot = _snapshot_from_graph(graph)
    layer = _layer_with_concept(
        _active_layer(_empty_layer_for(graph)),
        "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "orders",
    )
    metric = _semantic_metric(
        graph,
        concept_key="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        concept_ref="orders",
        variant="view_count",
        table_name="VW_DOC",
        measure_column="ID",
        grain_columns=["ID"],
        value_type="count",
    )
    result = _intent(metric, concept_ref="orders")
    layer = _layer_with_metrics(layer, [metric])
    preflight = _preflight(result, layer, graph, schema_snapshot, policy={"status_scope": "include_all_with_disclosure"})

    compiled = compile_query_plan(result, preflight, layer, graph, schema_snapshot)

    assert compiled.status == "compiled"
    assert "[SalesLT].[VW_DOC]" in compiled.sql
    assert "JOIN" not in compiled.sql
    assert compiled.trace.join_predicates == []


def test_query_compiler_module_has_no_demo_literals_or_execution_calls() -> None:
    source = Path("app/query_compiler.py").read_text(encoding="utf-8")

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


def _preflight(
    result: QueryIntentResult,
    layer,
    graph,
    schema_snapshot,
    *,
    policy: dict[str, object] | None = None,
):
    report = validate_query_compiler_preflight(
        result,
        layer,
        graph,
        _graph_report(),
        _semantic_invariant_report(),
        schema_snapshot=schema_snapshot,
        policy=policy,
    )
    assert (report.status, report.decision_category) in {
        ("ready", "safe"),
        ("ready_with_warnings", "safe_with_disclosure"),
    }
    return report


def _snapshot_from_graph(graph):
    nodes_by_key = {node.node_key: node for node in graph.nodes}
    tables = []
    for node in graph.nodes:
        tables.append(
            SimpleNamespace(
                table_schema=node.schema_name,
                name=node.object_name,
                table_type="view" if node.object_type == "view" else "base_table",
                columns=[
                    SimpleNamespace(
                        name=column.name,
                        data_type=column.native_type or column.normalized_type or "unknown",
                        native_type=column.native_type,
                        normalized_type=column.normalized_type,
                        ordinal_position=column.ordinal_position,
                        is_nullable=column.nullable,
                        technical_role=column.technical_role,
                    )
                    for column in node.columns
                ],
                primary_key=SimpleNamespace(
                    name=f"PK_{node.object_name}",
                    columns=list(node.candidate_keys[0].columns),
                )
                if node.candidate_keys
                else None,
            )
        )
    foreign_keys = []
    for edge in graph.edges:
        if getattr(edge, "edge_type", None) != "fk_join":
            continue
        from_node = nodes_by_key[edge.from_node_key]
        to_node = nodes_by_key[edge.to_node_key]
        pairs = sorted(edge.column_pairs, key=lambda item: item.ordinal_position)
        foreign_keys.append(
            SimpleNamespace(
                constraint_name=edge.constraint_name,
                from_schema=from_node.schema_name,
                from_table=from_node.object_name,
                from_columns=[pair.from_column for pair in pairs],
                to_schema=to_node.schema_name,
                to_table=to_node.object_name,
                to_columns=[pair.to_column for pair in pairs],
                delete_rule="no_action",
                update_rule="no_action",
                is_disabled=edge.enforcement_status == "disabled",
                is_not_trusted=edge.validation_status != "trusted",
                verified_by_db=edge.verified_by_db,
            )
        )
    return SimpleNamespace(
        engine=Engine.sqlserver,
        database_name=graph.nodes[0].database_name if graph.nodes else "db",
        engine_version="16.0",
        schema_hash=graph.schema_hash,
        snapshot_hash=graph.snapshot_hash,
        coverage_status="ok",
        tables=tables,
        foreign_keys=foreign_keys,
    )


def _compiler_codes(result) -> set[str]:
    return {issue.code for issue in [*result.errors, *result.warnings]}
