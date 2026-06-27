import hashlib
from datetime import UTC, datetime
from uuid import UUID

from app.drivers.base import (
    SchemaColumnMetadata,
    SchemaForeignKeyMetadata,
    SchemaIntrospectionResult,
    SchemaPrimaryKeyMetadata,
    SchemaTableMetadata,
    SchemaViewLineageDependency,
)
from app.models import (
    Engine,
    QueryabilityCandidateKey,
    QueryabilityColumn,
    QueryabilityColumnPair,
    QueryabilityForeignKeyEdge,
    QueryabilityGraphArtifact,
    QueryabilityNode,
    SemanticAmbiguity,
    SemanticBusinessConcept,
    SemanticConceptPolicy,
    SemanticDimensionCompatibility,
    SemanticDimensionPolicy,
    SemanticFilter,
    SemanticLayer,
    SemanticMetric,
    SemanticMetricFormat,
    SemanticPolicySnapshot,
    SemanticRequiredMetricSpec,
    SemanticDimensionExpectation,
)
from app.queryability import build_queryability_graph
from app.semantic import (
    build_semantic_seed,
    compute_metric_definition_hash,
    compute_semantic_policy_hash,
    compute_semantic_hash,
    validate_semantic_layer,
)


TENANT_ID = "11111111-1111-4111-8111-111111111111"
CONNECTION_ID = "22222222-2222-4222-8222-222222222222"
SNAPSHOT_ID = "33333333-3333-4333-8333-333333333333"
GRAPH_VERSION_ID = "44444444-4444-4444-8444-444444444444"
SEMANTIC_VERSION_ID = "88888888-8888-4888-8888-888888888888"
VALIDATED_AT = datetime(2026, 6, 14, 8, 0, tzinfo=UTC)


def key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def node_key(name: str) -> str:
    return key(f"node:{name}")


def column_key(table: str, column: str) -> str:
    return key(f"column:{table}:{column}")


def edge_key(name: str) -> str:
    return key(f"edge:{name}")


def _node(
    name: str,
    count: int,
    named_columns: list[tuple[str, str, str, bool, str]],
    *,
    primary_key: list[str] | None = None,
    object_type: str = "table",
) -> QueryabilityNode:
    columns = [
        QueryabilityColumn(
            column_key=column_key(name, column_name),
            name=column_name,
            ordinal_position=index,
            native_type=native_type,
            normalized_type=native_type,
            technical_role=technical_role,
            nullable=False,
            queryability_status="excluded" if excluded else "queryable",
            sensitivity=sensitivity,
            reason_codes=["SECURITY_POLICY_EXCLUSION"] if excluded else [],
        )
        for index, (
            column_name,
            native_type,
            technical_role,
            excluded,
            sensitivity,
        ) in enumerate(named_columns, start=1)
    ]
    while len(columns) < count:
        filler_name = f"FixtureColumn{len(columns) + 1}"
        columns.append(
            QueryabilityColumn(
                column_key=column_key(name, filler_name),
                name=filler_name,
                ordinal_position=len(columns) + 1,
                native_type="nvarchar",
                normalized_type="nvarchar",
                technical_role="text",
                nullable=True,
                queryability_status="queryable",
                sensitivity="none",
                reason_codes=[],
            )
        )
    candidate_keys = (
        [
            QueryabilityCandidateKey(
                key_type="primary_key",
                name=f"PK_{name}",
                columns=primary_key,
                eligible_for_cardinality=True,
            )
        ]
        if primary_key
        else []
    )
    return QueryabilityNode(
        node_key=node_key(name),
        database_name="AdventureWorksLT",
        schema_name="SalesLT",
        object_name=name,
        object_type=object_type,
        queryability_status="queryable",
        reason_codes=[],
        bridge_candidate=name in {"CustomerAddress", "ProductModelProductDescription"},
        candidate_keys=candidate_keys,
        columns=columns,
        view_definition_available=True if object_type == "view" else None,
        view_lineage_status=(
            "partial"
            if name == "vProductModelCatalogDescription"
            else "complete" if object_type == "view" else None
        ),
        view_column_lineage_status=(
            "partial"
            if name == "vProductModelCatalogDescription"
            else "complete" if object_type == "view" else None
        ),
    )


def _fk(
    name: str,
    child: str,
    child_column: str,
    parent: str,
    parent_column: str,
    *,
    nullable: bool = False,
    self_reference: bool = False,
) -> QueryabilityForeignKeyEdge:
    return QueryabilityForeignKeyEdge(
        edge_key=edge_key(name),
        edge_type="fk_join",
        constraint_name=name,
        from_node_key=node_key(child),
        to_node_key=node_key(parent),
        column_pairs=[
            QueryabilityColumnPair(
                ordinal_position=1,
                from_column=child_column,
                from_column_key=column_key(child, child_column),
                to_column=parent_column,
                to_column_key=column_key(parent, parent_column),
            )
        ],
        relationship_shape="many_to_one",
        child_to_parent="zero_or_one" if nullable else "exactly_one",
        parent_to_child="zero_or_many",
        nullable_fk=nullable,
        self_reference=self_reference,
        verified_by_db=True,
        enforcement_status="enabled",
        validation_status="trusted",
        automatic_join_allowed=True,
        reason_codes=[],
    )


def adventureworks_graph() -> QueryabilityGraphArtifact:
    nodes = [
        _node(
            "Address",
            9,
            [("AddressID", "int", "identifier", False, "none")],
            primary_key=["AddressID"],
        ),
        _node(
            "Customer",
            15,
            [
                ("CustomerID", "int", "identifier", False, "none"),
                ("PasswordHash", "varchar", "text", True, "sensitive"),
                ("PasswordSalt", "varchar", "text", True, "sensitive"),
                ("ModifiedDate", "datetime", "date", False, "none"),
            ],
            primary_key=["CustomerID"],
        ),
        _node(
            "CustomerAddress",
            5,
            [
                ("CustomerID", "int", "identifier", False, "none"),
                ("AddressID", "int", "identifier", False, "none"),
            ],
            primary_key=["CustomerID", "AddressID"],
        ),
        _node(
            "Product",
            17,
            [
                ("ProductID", "int", "identifier", False, "none"),
                ("ProductCategoryID", "int", "identifier", False, "none"),
                ("ProductModelID", "int", "identifier", False, "none"),
                ("ThumbNailPhoto", "varbinary", "binary", True, "none"),
            ],
            primary_key=["ProductID"],
        ),
        _node(
            "ProductCategory",
            5,
            [
                ("ProductCategoryID", "int", "identifier", False, "none"),
                (
                    "ParentProductCategoryID",
                    "int",
                    "identifier",
                    False,
                    "none",
                ),
            ],
            primary_key=["ProductCategoryID"],
        ),
        _node(
            "ProductDescription",
            4,
            [("ProductDescriptionID", "int", "identifier", False, "none")],
            primary_key=["ProductDescriptionID"],
        ),
        _node(
            "ProductModel",
            5,
            [
                ("ProductModelID", "int", "identifier", False, "none"),
                ("CatalogDescription", "xml", "xml", True, "none"),
            ],
            primary_key=["ProductModelID"],
        ),
        _node(
            "ProductModelProductDescription",
            5,
            [
                ("ProductModelID", "int", "identifier", False, "none"),
                (
                    "ProductDescriptionID",
                    "int",
                    "identifier",
                    False,
                    "none",
                ),
                ("Culture", "nchar", "identifier", False, "none"),
            ],
            primary_key=["ProductModelID", "ProductDescriptionID", "Culture"],
        ),
        _node(
            "SalesOrderDetail",
            9,
            [
                ("SalesOrderID", "int", "identifier", False, "none"),
                ("SalesOrderDetailID", "int", "identifier", False, "none"),
                (
                    "OrderQty",
                    "smallint",
                    "quantity_candidate",
                    False,
                    "none",
                ),
                ("ProductID", "int", "identifier", False, "none"),
                ("LineTotal", "numeric", "money_candidate", False, "none"),
            ],
            primary_key=["SalesOrderID", "SalesOrderDetailID"],
        ),
        _node(
            "SalesOrderHeader",
            22,
            [
                ("SalesOrderID", "int", "identifier", False, "none"),
                ("OrderDate", "datetime", "date", False, "none"),
                ("CustomerID", "int", "identifier", False, "none"),
                ("ShipToAddressID", "int", "identifier", False, "none"),
                ("BillToAddressID", "int", "identifier", False, "none"),
                ("SubTotal", "money", "money_candidate", False, "none"),
                ("TotalDue", "money", "money_candidate", False, "none"),
                (
                    "CreditCardApprovalCode",
                    "varchar",
                    "text",
                    True,
                    "sensitive",
                ),
            ],
            primary_key=["SalesOrderID"],
        ),
        _node(
            "vGetAllCategories",
            3,
            [
                (
                    "ProductCategoryID",
                    "int",
                    "identifier",
                    False,
                    "none",
                )
            ],
            object_type="view",
        ),
        _node(
            "vProductAndDescription",
            5,
            [("ProductID", "int", "identifier", False, "none")],
            object_type="view",
        ),
        _node(
            "vProductModelCatalogDescription",
            25,
            [("ProductModelID", "int", "identifier", False, "none")],
            object_type="view",
        ),
    ]
    edges = [
        _fk(
            "FK_CustomerAddress_Customer",
            "CustomerAddress",
            "CustomerID",
            "Customer",
            "CustomerID",
        ),
        _fk(
            "FK_CustomerAddress_Address",
            "CustomerAddress",
            "AddressID",
            "Address",
            "AddressID",
        ),
        _fk(
            "FK_ProductCategory_Parent",
            "ProductCategory",
            "ParentProductCategoryID",
            "ProductCategory",
            "ProductCategoryID",
            nullable=True,
            self_reference=True,
        ),
        _fk(
            "FK_Product_ProductCategory",
            "Product",
            "ProductCategoryID",
            "ProductCategory",
            "ProductCategoryID",
            nullable=True,
        ),
        _fk(
            "FK_Product_ProductModel",
            "Product",
            "ProductModelID",
            "ProductModel",
            "ProductModelID",
            nullable=True,
        ),
        _fk(
            "FK_PMPD_ProductModel",
            "ProductModelProductDescription",
            "ProductModelID",
            "ProductModel",
            "ProductModelID",
        ),
        _fk(
            "FK_PMPD_ProductDescription",
            "ProductModelProductDescription",
            "ProductDescriptionID",
            "ProductDescription",
            "ProductDescriptionID",
        ),
        _fk(
            "FK_Detail_Header",
            "SalesOrderDetail",
            "SalesOrderID",
            "SalesOrderHeader",
            "SalesOrderID",
        ),
        _fk(
            "FK_Detail_Product",
            "SalesOrderDetail",
            "ProductID",
            "Product",
            "ProductID",
        ),
        _fk(
            "FK_Header_Customer",
            "SalesOrderHeader",
            "CustomerID",
            "Customer",
            "CustomerID",
        ),
        _fk(
            "FK_Header_ShipAddress",
            "SalesOrderHeader",
            "ShipToAddressID",
            "Address",
            "AddressID",
            nullable=True,
        ),
        _fk(
            "FK_Header_BillAddress",
            "SalesOrderHeader",
            "BillToAddressID",
            "Address",
            "AddressID",
            nullable=True,
        ),
    ]
    return QueryabilityGraphArtifact(
        contract_version="queryability_graph.v1",
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        schema_snapshot_id=SNAPSHOT_ID,
        engine="sqlserver",
        schema_hash="a" * 64,
        snapshot_hash="b" * 64,
        graph_input_hash="c" * 64,
        derivation_key="e" * 64,
        graph_hash="d" * 64,
        builder_version="1.1.0",
        policy_version="1.0.0",
        status="partial",
        status_reasons=["VIEW_LINEAGE_PARTIAL"],
        semantic_status="not_initialized",
        nodes=nodes,
        edges=edges,
    )


def _concept(
    concept_key: str,
    canonical_name: str,
    display_name: str,
) -> SemanticBusinessConcept:
    return SemanticBusinessConcept(
        business_concept_key=UUID(concept_key),
        canonical_name=canonical_name,
        display_name=display_name,
        status="ai_proposed",
        provenance="ai",
    )


DIMENSION_POLICY = SemanticDimensionPolicy(
    same_grain="safe",
    parent_many_to_one="safe",
    child_one_to_many="forbidden",
    bridge_or_many_to_many="forbidden",
    self_reference="conditional",
)


def semantic_policy() -> SemanticPolicySnapshot:
    policy = SemanticPolicySnapshot(
        policy_version="1.0.0",
        policy_hash="0" * 64,
        default_currency="EUR",
        missing_currency_behavior="clarification_required",
        activation_policy="auto_validated",
        minimum_eligible_metrics=1,
        required_concepts=[
            SemanticConceptPolicy(
                concept_ref="revenue",
                preferred_variants=["net_header", "document_total", "line_detail"],
            ),
            SemanticConceptPolicy(
                concept_ref="quantity_sold",
                preferred_variants=["line_quantity"],
            ),
            SemanticConceptPolicy(
                concept_ref="orders",
                preferred_variants=["header_count"],
            ),
            SemanticConceptPolicy(
                concept_ref="customers",
                preferred_variants=["order_customers", "customer_master"],
            ),
        ],
        required_metric_specs=[],
    )
    return policy.model_copy(
        update={"policy_hash": compute_semantic_policy_hash(policy)}
    )


def adventureworks_quality_policy() -> SemanticPolicySnapshot:
    category = SemanticDimensionExpectation(
        dimension_column_key=column_key("ProductCategory", "ProductCategoryID"),
        expected_safety="safe",
    )
    forbidden_header_category = category.model_copy(
        update={"expected_safety": "forbidden"}
    )

    def spec(
        *,
        spec_key: str,
        concept: str,
        variant: str,
        canonical_name: str,
        source_table: str,
        aggregation: str,
        measure_column: str,
        grain_columns: list[str],
        value_type: str,
        default_date: tuple[str, str] | None = None,
        default_for_concept: bool = False,
        required_for_activation: bool = False,
        dimensions: list[SemanticDimensionExpectation] | None = None,
        allowed_eligibility: list[str] | None = None,
    ) -> SemanticRequiredMetricSpec:
        return SemanticRequiredMetricSpec(
            spec_key=spec_key,
            intent_key=canonical_name,
            business_concept_ref=concept,
            expected_variant=variant,
            canonical_name=canonical_name,
            name=canonical_name.replace("_", " ").title(),
            source_table_key=node_key(source_table),
            aggregation=aggregation,
            measure_column_key=column_key(source_table, measure_column),
            grain_column_keys=[
                column_key(source_table, column) for column in grain_columns
            ],
            default_date_column_key=(
                column_key(*default_date) if default_date else None
            ),
            value_type=value_type,
            default_for_concept=default_for_concept,
            required_for_activation=required_for_activation,
            allowed_eligibility=allowed_eligibility
            or ["eligible", "eligible_with_disclosure"],
            dimension_expectations=dimensions or [],
            synonyms=[],
        )

    base = semantic_policy()
    policy = base.model_copy(
        update={
            "required_concepts": [
                item.model_copy(
                    update={
                        "required": True,
                        "required_for_activation": item.concept_ref
                        in {"revenue", "quantity_sold", "orders"},
                    }
                )
                for item in base.required_concepts
            ],
            "minimum_eligible_metrics": 4,
            "required_metric_specs": [
                spec(
                    spec_key="adventureworks.revenue.net_header",
                    concept="revenue",
                    variant="net_header",
                    canonical_name="fatturato_netto",
                    source_table="SalesOrderHeader",
                    aggregation="sum",
                    measure_column="SubTotal",
                    grain_columns=["SalesOrderID"],
                    default_date=("SalesOrderHeader", "OrderDate"),
                    value_type="currency",
                    default_for_concept=True,
                    required_for_activation=True,
                    dimensions=[forbidden_header_category],
                ),
                spec(
                    spec_key="adventureworks.revenue.document_total",
                    concept="revenue",
                    variant="document_total",
                    canonical_name="totale_documento",
                    source_table="SalesOrderHeader",
                    aggregation="sum",
                    measure_column="TotalDue",
                    grain_columns=["SalesOrderID"],
                    default_date=("SalesOrderHeader", "OrderDate"),
                    value_type="currency",
                    required_for_activation=True,
                ),
                spec(
                    spec_key="adventureworks.revenue.line_detail",
                    concept="revenue",
                    variant="line_detail",
                    canonical_name="fatturato_righe",
                    source_table="SalesOrderDetail",
                    aggregation="sum",
                    measure_column="LineTotal",
                    grain_columns=["SalesOrderID", "SalesOrderDetailID"],
                    default_date=("SalesOrderHeader", "OrderDate"),
                    value_type="currency",
                    dimensions=[category],
                ),
                spec(
                    spec_key="adventureworks.quantity.line_quantity",
                    concept="quantity_sold",
                    variant="line_quantity",
                    canonical_name="quantita_venduta",
                    source_table="SalesOrderDetail",
                    aggregation="sum",
                    measure_column="OrderQty",
                    grain_columns=["SalesOrderID", "SalesOrderDetailID"],
                    default_date=("SalesOrderHeader", "OrderDate"),
                    value_type="number",
                    required_for_activation=True,
                    dimensions=[category],
                ),
                spec(
                    spec_key="adventureworks.orders.header_count",
                    concept="orders",
                    variant="header_count",
                    canonical_name="ordini",
                    source_table="SalesOrderHeader",
                    aggregation="count",
                    measure_column="SalesOrderID",
                    grain_columns=["SalesOrderID"],
                    default_date=("SalesOrderHeader", "OrderDate"),
                    value_type="count",
                    required_for_activation=True,
                ),
                spec(
                    spec_key="adventureworks.customers.order_customers",
                    concept="customers",
                    variant="order_customers",
                    canonical_name="clienti_ordini",
                    source_table="SalesOrderHeader",
                    aggregation="count_distinct",
                    measure_column="CustomerID",
                    grain_columns=["SalesOrderID"],
                    default_date=("SalesOrderHeader", "OrderDate"),
                    value_type="count",
                    allowed_eligibility=[
                        "eligible",
                        "eligible_with_disclosure",
                        "clarification_required",
                    ],
                ),
                spec(
                    spec_key="adventureworks.customers.customer_master",
                    concept="customers",
                    variant="customer_master",
                    canonical_name="clienti_anagrafica",
                    source_table="Customer",
                    aggregation="count",
                    measure_column="CustomerID",
                    grain_columns=["CustomerID"],
                    value_type="count",
                    allowed_eligibility=[
                        "eligible",
                        "eligible_with_disclosure",
                        "clarification_required",
                    ],
                ),
            ],
        }
    )
    return policy.model_copy(
        update={"policy_hash": compute_semantic_policy_hash(policy)}
    )


def _metric(
    *,
    metric_key: str,
    canonical_name: str,
    concept_key: str,
    variant: str,
    source_table: str,
    aggregation: str,
    measure_column: str | None,
    grain_columns: list[str],
    default_date: tuple[str, str] | None = None,
    compatibilities: list[SemanticDimensionCompatibility] | None = None,
    required_edges: list[str] | None = None,
    value_type: str = "number",
    synonyms: list[str] | None = None,
) -> SemanticMetric:
    metric = SemanticMetric(
        metric_key=UUID(metric_key),
        canonical_name=canonical_name,
        metric_definition_hash="0" * 64,
        business_concept_key=UUID(concept_key),
        metric_variant=variant,
        name=canonical_name.replace("_", " ").title(),
        status="ai_proposed",
        source_table_key=node_key(source_table),
        aggregation=aggregation,
        measure_column_key=(
            column_key(source_table, measure_column) if measure_column else None
        ),
        grain_table_key=node_key(source_table),
        grain_column_keys=[
            column_key(source_table, column_name)
            for column_name in grain_columns
        ],
        aggregation_level="entity",
        additivity="additive",
        default_date_column_key=(
            column_key(*default_date) if default_date else None
        ),
        required_join_edge_keys=[
            edge_key(edge_name) for edge_name in required_edges or []
        ],
        common_dimension_compatibility=compatibilities or [],
        dimension_policy=DIMENSION_POLICY,
        preferred_for_grains=[],
        preferred_for_dimensions=[],
        filters=[],
        format=SemanticMetricFormat(
            value_type=value_type,
            currency="EUR" if value_type == "currency" else None,
            decimals=0 if value_type == "count" else 2,
        ),
        synonyms=synonyms or [],
        confidence_score=0.5,
        confidence_label="medium",
        compiler_eligibility="clarification_required",
        eligibility_reasons=["NOT_VALIDATED"],
        validation_warnings=[],
        provenance="ai",
        provenance_detail="ai_generation",
        enabled=True,
    )
    return metric.model_copy(
        update={"metric_definition_hash": compute_metric_definition_hash(metric)}
    )


def semantic_draft(graph: QueryabilityGraphArtifact) -> SemanticLayer:
    layer = build_semantic_seed(
        graph=graph,
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=semantic_policy(),
    )
    revenue = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    quantity = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    orders = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    customers = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    category_path = [
        edge_key("FK_Detail_Header"),
        edge_key("FK_Detail_Product"),
        edge_key("FK_Product_ProductCategory"),
    ]
    detail_category_path = [
        edge_key("FK_Detail_Product"),
        edge_key("FK_Product_ProductCategory"),
    ]
    concepts = [
        _concept(revenue, "revenue", "Fatturato"),
        _concept(quantity, "quantity_sold", "Quantità venduta"),
        _concept(orders, "orders", "Ordini"),
        _concept(customers, "customers", "Clienti"),
    ]
    metrics = [
        _metric(
            metric_key="10000000-0000-4000-8000-000000000001",
            canonical_name="fatturato_netto",
            concept_key=revenue,
            variant="net_header",
            source_table="SalesOrderHeader",
            aggregation="sum",
            measure_column="SubTotal",
            grain_columns=["SalesOrderID"],
            default_date=("SalesOrderHeader", "OrderDate"),
            compatibilities=[
                SemanticDimensionCompatibility(
                    dimension_column_key=column_key(
                        "SalesOrderHeader",
                        "CustomerID",
                    ),
                    edge_path=[],
                    safety="safe",
                    reason_code="SAME_GRAIN",
                ),
                SemanticDimensionCompatibility(
                    dimension_column_key=column_key(
                        "ProductCategory",
                        "ProductCategoryID",
                    ),
                    edge_path=category_path,
                    safety="forbidden",
                    reason_code="CHILD_ONE_TO_MANY",
                ),
            ],
            value_type="currency",
            synonyms=["fatturato", "vendite"],
        ),
        _metric(
            metric_key="10000000-0000-4000-8000-000000000002",
            canonical_name="totale_documento",
            concept_key=revenue,
            variant="document_total",
            source_table="SalesOrderHeader",
            aggregation="sum",
            measure_column="TotalDue",
            grain_columns=["SalesOrderID"],
            default_date=("SalesOrderHeader", "OrderDate"),
            value_type="currency",
            synonyms=["totale ordine"],
        ),
        _metric(
            metric_key="10000000-0000-4000-8000-000000000003",
            canonical_name="fatturato_righe",
            concept_key=revenue,
            variant="line_detail",
            source_table="SalesOrderDetail",
            aggregation="sum",
            measure_column="LineTotal",
            grain_columns=["SalesOrderID", "SalesOrderDetailID"],
            compatibilities=[
                SemanticDimensionCompatibility(
                    dimension_column_key=column_key(
                        "ProductCategory",
                        "ProductCategoryID",
                    ),
                    edge_path=detail_category_path,
                    safety="safe",
                    reason_code="TRUSTED_PARENT_PATH",
                )
            ],
            required_edges=[
                "FK_Detail_Product",
                "FK_Product_ProductCategory",
            ],
            value_type="currency",
            synonyms=["vendite per prodotto"],
        ),
        _metric(
            metric_key="10000000-0000-4000-8000-000000000004",
            canonical_name="quantita_venduta",
            concept_key=quantity,
            variant="line_quantity",
            source_table="SalesOrderDetail",
            aggregation="sum",
            measure_column="OrderQty",
            grain_columns=["SalesOrderID", "SalesOrderDetailID"],
            compatibilities=[
                SemanticDimensionCompatibility(
                    dimension_column_key=column_key(
                        "ProductCategory",
                        "ProductCategoryID",
                    ),
                    edge_path=detail_category_path,
                    safety="safe",
                    reason_code="TRUSTED_PARENT_PATH",
                )
            ],
            required_edges=[
                "FK_Detail_Product",
                "FK_Product_ProductCategory",
            ],
        ),
        _metric(
            metric_key="10000000-0000-4000-8000-000000000005",
            canonical_name="ordini",
            concept_key=orders,
            variant="header_count",
            source_table="SalesOrderHeader",
            aggregation="count",
            measure_column="SalesOrderID",
            grain_columns=["SalesOrderID"],
            default_date=("SalesOrderHeader", "OrderDate"),
            value_type="count",
        ),
        _metric(
            metric_key="10000000-0000-4000-8000-000000000006",
            canonical_name="clienti_ordini",
            concept_key=customers,
            variant="order_customers",
            source_table="SalesOrderHeader",
            aggregation="count_distinct",
            measure_column="CustomerID",
            grain_columns=["SalesOrderID"],
            default_date=("SalesOrderHeader", "OrderDate"),
            value_type="count",
            synonyms=["clienti"],
        ),
        _metric(
            metric_key="10000000-0000-4000-8000-000000000007",
            canonical_name="clienti_anagrafica",
            concept_key=customers,
            variant="customer_master",
            source_table="Customer",
            aggregation="count",
            measure_column="CustomerID",
            grain_columns=["CustomerID"],
            value_type="count",
            synonyms=["clienti"],
        ),
    ]
    ambiguities = [
        SemanticAmbiguity(
            ambiguity_key="20000000-0000-4000-8000-000000000001",
            code="CUSTOMER_POPULATION_AMBIGUOUS",
            target_type="business_concept",
            target_key=customers,
            summary=(
                "Client count can refer to customers in orders or the customer master."
            ),
            clarification_question=(
                "Use customers with orders or all customers in the master table?"
            ),
            status="open",
            provenance="system",
            severity="material_ambiguity",
        )
    ]
    updated = layer.model_copy(
        update={
            "revision": 2,
            "ai_model_version": "fixture-model-v1",
            "ai_prompt_version": "semantic-discovery.v1",
            "business_concepts": concepts,
            "metrics": metrics,
            "ambiguities": ambiguities,
        }
    )
    return updated.model_copy(
        update={"semantic_hash": compute_semantic_hash(updated)}
    )


def test_adventureworks_seed_preserves_graph_authority_and_expected_counts() -> None:
    graph = adventureworks_graph()
    seed = build_semantic_seed(
        graph=graph,
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=semantic_policy(),
    )

    assert len(seed.tables) == 13
    assert len(seed.columns) == 129
    assert len(seed.relationships) == 12
    assert sum(column.included for column in seed.columns) == 124
    assert sum(not column.included for column in seed.columns) == 5
    assert seed.business_concepts == []
    assert seed.metrics == []
    assert all(
        relationship.edge_key
        not in {
            edge.edge_key
            for edge in graph.edges
            if not edge.automatic_join_allowed
        }
        for relationship in seed.relationships
    )


def test_snapshot_to_graph_to_semantic_seed_preserves_only_trusted_fks() -> None:
    parent = SchemaTableMetadata(
        table_schema="SalesLT",
        name="Parent",
        table_type="base_table",
        columns=[
            SchemaColumnMetadata(
                name="ParentID",
                data_type="int",
                native_type="int",
                normalized_type="int",
                technical_role="identifier",
                ordinal_position=1,
                is_nullable=False,
            )
        ],
        primary_key=SchemaPrimaryKeyMetadata(
            name="PK_Parent",
            columns=["ParentID"],
        ),
    )
    child = SchemaTableMetadata(
        table_schema="SalesLT",
        name="Child",
        table_type="base_table",
        columns=[
            SchemaColumnMetadata(
                name="ChildID",
                data_type="int",
                native_type="int",
                normalized_type="int",
                technical_role="identifier",
                ordinal_position=1,
                is_nullable=False,
            ),
            SchemaColumnMetadata(
                name="ParentID",
                data_type="int",
                native_type="int",
                normalized_type="int",
                technical_role="identifier",
                ordinal_position=2,
                is_nullable=False,
            ),
        ],
        primary_key=SchemaPrimaryKeyMetadata(
            name="PK_Child",
            columns=["ChildID"],
        ),
    )
    view = SchemaTableMetadata(
        table_schema="SalesLT",
        name="vChild",
        table_type="view",
        columns=[
            SchemaColumnMetadata(
                name="ChildID",
                data_type="int",
                native_type="int",
                normalized_type="int",
                technical_role="identifier",
                ordinal_position=1,
                is_nullable=False,
            )
        ],
        view_definition_available=True,
        lineage_available=True,
        view_lineage=[
            SchemaViewLineageDependency(
                source="dm_sql_referenced_entities",
                referenced_class="OBJECT_OR_COLUMN",
                referenced_schema_name="SalesLT",
                referenced_entity_name="Child",
                referenced_column_name="ChildID",
                referencing_column="ChildID",
                is_incomplete=False,
            )
        ],
    )
    snapshot = SchemaIntrospectionResult(
        engine=Engine.sqlserver,
        database_name="AdventureWorksLT",
        engine_version="12.0.2000.8",
        schema_hash="a" * 64,
        snapshot_hash="b" * 64,
        coverage_status="ok",
        tables=[parent, child, view],
        foreign_keys=[
            SchemaForeignKeyMetadata(
                constraint_name="FK_Child_Parent",
                from_schema="SalesLT",
                from_table="Child",
                from_columns=["ParentID"],
                to_schema="SalesLT",
                to_table="Parent",
                to_columns=["ParentID"],
                delete_rule="no_action",
                update_rule="no_action",
                verified_by_db=True,
            ),
            SchemaForeignKeyMetadata(
                constraint_name="FK_Child_Parent_Untrusted",
                from_schema="SalesLT",
                from_table="Child",
                from_columns=["ParentID"],
                to_schema="SalesLT",
                to_table="Parent",
                to_columns=["ParentID"],
                delete_rule="no_action",
                update_rule="no_action",
                is_not_trusted=True,
                verified_by_db=True,
            ),
        ],
    )

    graph = build_queryability_graph(
        snapshot=snapshot,
        tenant_id=TENANT_ID,
        connection_id=CONNECTION_ID,
        schema_snapshot_id=SNAPSHOT_ID,
    )
    seed = build_semantic_seed(
        graph=graph,
        semantic_version_id=SEMANTIC_VERSION_ID,
        queryability_graph_version_id=GRAPH_VERSION_ID,
        version=1,
        semantic_policy=semantic_policy(),
    )

    assert len(seed.tables) == 3
    assert len(seed.columns) == 4
    assert len(seed.relationships) == 1
    assert seed.relationships[0].edge_key == next(
        edge.edge_key
        for edge in graph.edges
        if isinstance(edge, QueryabilityForeignKeyEdge)
        and edge.constraint_name == "FK_Child_Parent"
    )


def test_validator_accepts_safe_variants_and_marks_customer_ambiguity() -> None:
    graph = adventureworks_graph()
    validated = validate_semantic_layer(
        layer=semantic_draft(graph),
        graph=graph,
        validated_at=VALIDATED_AT,
    )
    metrics = {metric.canonical_name: metric for metric in validated.metrics}

    assert validated.status == "proposed"
    assert validated.validation_report.status == "valid_with_warnings"
    assert validated.validation_report.blocking_errors == []
    assert metrics["fatturato_netto"].compiler_eligibility == (
        "eligible_with_disclosure"
    )
    assert metrics["fatturato_righe"].compiler_eligibility == (
        "eligible_with_disclosure"
    )
    assert metrics["quantita_venduta"].compiler_eligibility == (
        "eligible_with_disclosure"
    )
    assert metrics["clienti_ordini"].compiler_eligibility == (
        "clarification_required"
    )
    assert "DUPLICATE_METRIC_SYNONYM" in (
        metrics["clienti_ordini"].validation_warnings
    )


def test_header_metric_cannot_claim_detail_dimension_is_safe() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metrics = list(draft.metrics)
    revenue = metrics[0]
    compatibilities = list(revenue.common_dimension_compatibility)
    compatibilities[1] = compatibilities[1].model_copy(
        update={"safety": "safe"}
    )
    unsafe_revenue = revenue.model_copy(
        update={"common_dimension_compatibility": compatibilities}
    )
    unsafe_revenue = unsafe_revenue.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(
                unsafe_revenue
            )
        }
    )
    metrics[0] = unsafe_revenue
    draft = draft.model_copy(update={"metrics": metrics})
    draft = draft.model_copy(
        update={"semantic_hash": compute_semantic_hash(draft)}
    )

    validated = validate_semantic_layer(
        layer=draft,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert validated.validation_report.status == "blocked"
    assert "HEADER_DETAIL_DIMENSION_FORBIDDEN" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }
    metric = next(
        item for item in validated.metrics if item.canonical_name == "fatturato_netto"
    )
    assert metric.compiler_eligibility == "not_eligible"


def test_metric_identity_is_stable_while_definition_hash_changes() -> None:
    graph = adventureworks_graph()
    metric = semantic_draft(graph).metrics[0]
    changed = metric.model_copy(update={"aggregation": "avg"})
    changed = changed.model_copy(
        update={"metric_definition_hash": compute_metric_definition_hash(changed)}
    )

    assert changed.metric_key == metric.metric_key
    assert changed.metric_definition_hash != metric.metric_definition_hash


def test_metric_format_does_not_change_definition_hash() -> None:
    graph = adventureworks_graph()
    metric = semantic_draft(graph).metrics[0]
    changed = metric.model_copy(
        update={
            "format": metric.format.model_copy(update={"decimals": 0}),
        }
    )

    assert compute_metric_definition_hash(changed) == (
        metric.metric_definition_hash
    )


def test_semantic_hash_canonicalizes_unordered_business_labels() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    concepts = list(draft.business_concepts)
    concepts[0] = concepts[0].model_copy(
        update={"synonyms": ["vendite", "ricavi"]}
    )
    first = draft.model_copy(update={"business_concepts": concepts})
    concepts[0] = concepts[0].model_copy(
        update={"synonyms": ["ricavi", "vendite"]}
    )
    second = draft.model_copy(update={"business_concepts": concepts})

    assert compute_semantic_hash(first) == compute_semantic_hash(second)


def test_required_join_path_cannot_cross_from_header_to_detail() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metrics = list(draft.metrics)
    revenue = metrics[0].model_copy(
        update={
            "required_join_edge_keys": [edge_key("FK_Detail_Header")],
            "common_dimension_compatibility": [],
        }
    )
    revenue = revenue.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(revenue)
        }
    )
    metrics[0] = revenue
    draft = draft.model_copy(update={"metrics": metrics})

    validated = validate_semantic_layer(
        layer=draft,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "METRIC_REQUIRED_JOIN_MULTIPLICATION" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_validator_requires_complete_graph_projection() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    missing_table = draft.tables[0]
    missing_column = next(
        column
        for column in draft.columns
        if column.node_key == missing_table.node_key
    )
    missing_relationship = draft.relationships[0]
    incomplete = draft.model_copy(
        update={
            "tables": [
                table
                for table in draft.tables
                if table.node_key != missing_table.node_key
            ],
            "columns": [
                column
                for column in draft.columns
                if column.column_key != missing_column.column_key
            ],
            "relationships": [
                relationship
                for relationship in draft.relationships
                if relationship.edge_key != missing_relationship.edge_key
            ],
        }
    )

    validated = validate_semantic_layer(
        layer=incomplete,
        graph=graph,
        validated_at=VALIDATED_AT,
    )
    codes = {
        issue.code for issue in validated.validation_report.blocking_errors
    }

    assert "SEMANTIC_TABLE_MISSING" in codes
    assert "SEMANTIC_COLUMN_MISSING" in codes
    assert "SEMANTIC_RELATIONSHIP_MISSING" in codes


def test_validator_requires_graph_candidate_key_grain() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metrics = list(draft.metrics)
    revenue = metrics[0].model_copy(
        update={
            "grain_column_keys": [
                column_key("SalesOrderHeader", "CustomerID")
            ]
        }
    )
    revenue = revenue.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(revenue)
        }
    )
    metrics[0] = revenue

    validated = validate_semantic_layer(
        layer=draft.model_copy(update={"metrics": metrics}),
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "METRIC_GRAIN_NOT_CANDIDATE_KEY" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_count_measure_must_be_included_and_belong_to_source() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metrics = list(draft.metrics)
    orders = next(metric for metric in metrics if metric.canonical_name == "ordini")
    unsafe = orders.model_copy(
        update={
            "measure_column_key": column_key(
                "SalesOrderHeader",
                "CreditCardApprovalCode",
            )
        }
    )
    unsafe = unsafe.model_copy(
        update={"metric_definition_hash": compute_metric_definition_hash(unsafe)}
    )
    metrics[metrics.index(orders)] = unsafe

    validated = validate_semantic_layer(
        layer=draft.model_copy(update={"metrics": metrics}),
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "METRIC_MEASURE_EXCLUDED" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }

    wrong_source = orders.model_copy(
        update={
            "measure_column_key": column_key("Customer", "CustomerID"),
        }
    )
    wrong_source = wrong_source.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(
                wrong_source
            )
        }
    )
    metrics[metrics.index(unsafe)] = wrong_source
    validated = validate_semantic_layer(
        layer=draft.model_copy(update={"metrics": metrics}),
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "METRIC_MEASURE_SOURCE_MISMATCH" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_metric_date_and_filter_must_be_on_required_join_path() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metrics = list(draft.metrics)
    revenue = metrics[0].model_copy(
        update={
            "default_date_column_key": column_key(
                "Customer",
                "ModifiedDate",
            ),
            "filters": [
                SemanticFilter(
                    column_key=column_key("Product", "ProductID"),
                    operator="gt",
                    value=0,
                    value_type="integer",
                )
            ],
        }
    )
    revenue = revenue.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(revenue)
        }
    )
    metrics[0] = revenue

    validated = validate_semantic_layer(
        layer=draft.model_copy(update={"metrics": metrics}),
        graph=graph,
        validated_at=VALIDATED_AT,
    )
    codes = {
        issue.code for issue in validated.validation_report.blocking_errors
    }

    assert "METRIC_DEFAULT_DATE_INVALID" in codes
    assert "METRIC_FILTER_COLUMN_INVALID" in codes


def test_disabled_semantic_relationship_cannot_route_metric() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    relationships = [
        relationship.model_copy(update={"enabled": False})
        if relationship.edge_key == edge_key("FK_Detail_Product")
        else relationship
        for relationship in draft.relationships
    ]
    disabled = draft.model_copy(update={"relationships": relationships})
    disabled = disabled.model_copy(
        update={"semantic_hash": compute_semantic_hash(disabled)}
    )

    validated = validate_semantic_layer(
        layer=disabled,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "METRIC_JOIN_EDGE_INVALID" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_untrusted_fk_cannot_be_added_as_disabled_semantic_relationship() -> None:
    graph = adventureworks_graph()
    trusted_edge = next(
        edge
        for edge in graph.edges
        if isinstance(edge, QueryabilityForeignKeyEdge)
        and edge.constraint_name == "FK_Header_Customer"
    )
    untrusted_edge = trusted_edge.model_copy(
        update={
            "edge_key": edge_key("FK_Header_Customer_Untrusted"),
            "validation_status": "untrusted",
            "automatic_join_allowed": False,
        }
    )
    graph = graph.model_copy(update={"edges": [*graph.edges, untrusted_edge]})
    draft = semantic_draft(graph)
    relationship = draft.relationships[0].model_copy(
        update={
            "edge_key": untrusted_edge.edge_key,
            "from_node_key": untrusted_edge.from_node_key,
            "to_node_key": untrusted_edge.to_node_key,
            "enabled": False,
        }
    )
    invalid = draft.model_copy(
        update={"relationships": [*draft.relationships, relationship]}
    )
    invalid = invalid.model_copy(
        update={"semantic_hash": compute_semantic_hash(invalid)}
    )

    validated = validate_semantic_layer(
        layer=invalid,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "RELATIONSHIP_NOT_TRUSTED" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_excluded_table_makes_its_columns_and_all_metrics_ineligible() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    tables = [
        table.model_copy(update={"included": False})
        if table.object_name == "ProductCategory"
        else table
        for table in draft.tables
    ]
    excluded = draft.model_copy(update={"tables": tables})
    excluded = excluded.model_copy(
        update={"semantic_hash": compute_semantic_hash(excluded)}
    )

    validated = validate_semantic_layer(
        layer=excluded,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "COLUMN_INCLUDED_IN_EXCLUDED_TABLE" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }
    assert all(
        metric.compiler_eligibility == "not_eligible"
        for metric in validated.metrics
    )


def test_validator_rejects_stale_semantic_hash() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    tampered = draft.model_copy(
        update={
            "tables": [
                draft.tables[0].model_copy(update={"display_name": "Tampered"}),
                *draft.tables[1:],
            ]
        }
    )

    validated = validate_semantic_layer(
        layer=tampered,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "SEMANTIC_HASH_MISMATCH" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }
    assert all(
        metric.compiler_eligibility == "not_eligible"
        for metric in validated.metrics
    )


def test_duplicate_business_concept_key_is_blocking() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    duplicate = draft.business_concepts[0].model_copy(
        update={"canonical_name": "duplicate_revenue"}
    )
    invalid = draft.model_copy(
        update={"business_concepts": [*draft.business_concepts, duplicate]}
    )
    invalid = invalid.model_copy(
        update={"semantic_hash": compute_semantic_hash(invalid)}
    )

    validated = validate_semantic_layer(
        layer=invalid,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "DUPLICATE_BUSINESS_CONCEPT" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_disabled_concept_and_missing_filter_value_are_blocking() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    concepts = list(draft.business_concepts)
    concepts[0] = concepts[0].model_copy(update={"status": "disabled"})
    metrics = list(draft.metrics)
    revenue = metrics[0].model_copy(
        update={
            "filters": [
                SemanticFilter(
                    column_key=column_key(
                        "SalesOrderHeader",
                        "CustomerID",
                    ),
                    operator="eq",
                    value_type="integer",
                )
            ]
        }
    )
    revenue = revenue.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(revenue)
        }
    )
    metrics[0] = revenue
    invalid = draft.model_copy(
        update={
            "business_concepts": concepts,
            "metrics": metrics,
        }
    )
    invalid = invalid.model_copy(
        update={"semantic_hash": compute_semantic_hash(invalid)}
    )

    validated = validate_semantic_layer(
        layer=invalid,
        graph=graph,
        validated_at=VALIDATED_AT,
    )
    codes = {
        issue.code for issue in validated.validation_report.blocking_errors
    }

    assert "METRIC_BUSINESS_CONCEPT_DISABLED" in codes
    assert "METRIC_FILTER_VALUE_REQUIRED" in codes


def test_forbidden_dimension_path_still_requires_correct_endpoint() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metrics = list(draft.metrics)
    revenue = metrics[0]
    compatibilities = list(revenue.common_dimension_compatibility)
    compatibilities[1] = compatibilities[1].model_copy(
        update={
            "dimension_column_key": column_key("Customer", "CustomerID"),
        }
    )
    revenue = revenue.model_copy(
        update={"common_dimension_compatibility": compatibilities}
    )
    revenue = revenue.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(revenue)
        }
    )
    metrics[0] = revenue
    invalid = draft.model_copy(update={"metrics": metrics})
    invalid = invalid.model_copy(
        update={"semantic_hash": compute_semantic_hash(invalid)}
    )

    validated = validate_semantic_layer(
        layer=invalid,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "DIMENSION_PATH_INVALID" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_safe_dimension_path_cannot_be_declared_forbidden() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    metrics = list(draft.metrics)
    revenue = metrics[0]
    compatibilities = list(revenue.common_dimension_compatibility)
    compatibilities[0] = compatibilities[0].model_copy(
        update={"safety": "forbidden"}
    )
    revenue = revenue.model_copy(
        update={"common_dimension_compatibility": compatibilities}
    )
    revenue = revenue.model_copy(
        update={
            "metric_definition_hash": compute_metric_definition_hash(revenue)
        }
    )
    metrics[0] = revenue
    invalid = draft.model_copy(update={"metrics": metrics})
    invalid = invalid.model_copy(
        update={"semantic_hash": compute_semantic_hash(invalid)}
    )

    validated = validate_semantic_layer(
        layer=invalid,
        graph=graph,
        validated_at=VALIDATED_AT,
    )

    assert "DIMENSION_SAFETY_DECLARATION_MISMATCH" in {
        issue.code for issue in validated.validation_report.blocking_errors
    }


def test_concept_variant_mismatch_is_not_compiler_eligible() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    concepts = list(draft.business_concepts)
    concepts[1] = concepts[1].model_copy(
        update={"canonical_name": concepts[0].canonical_name}
    )
    ambiguous = draft.model_copy(update={"business_concepts": concepts})
    ambiguous = ambiguous.model_copy(
        update={"semantic_hash": compute_semantic_hash(ambiguous)}
    )

    validated = validate_semantic_layer(
        layer=ambiguous,
        graph=graph,
        validated_at=VALIDATED_AT,
    )
    quantity = next(
        metric
        for metric in validated.metrics
        if metric.canonical_name == "quantita_venduta"
    )

    assert quantity.compiler_eligibility == "not_eligible"
    assert "METRIC_VARIANT_NOT_ALLOWLISTED" in quantity.eligibility_reasons
    assert "AMBIGUOUS_BUSINESS_CONCEPT" in quantity.validation_warnings


def test_validator_blocks_reenabled_sensitive_column_and_stale_graph() -> None:
    graph = adventureworks_graph()
    draft = semantic_draft(graph)
    columns = list(draft.columns)
    sensitive_index = next(
        index
        for index, column in enumerate(columns)
        if column.physical_name == "CreditCardApprovalCode"
    )
    columns[sensitive_index] = columns[sensitive_index].model_copy(
        update={
            "included": True,
            "sensitivity": "none",
            "inherited_sensitivity": "none",
            "physical_name": "TamperedApprovalCode",
        }
    )
    stale = draft.model_copy(
        update={
            "base_graph_hash": "f" * 64,
            "columns": columns,
        }
    )

    validated = validate_semantic_layer(
        layer=stale,
        graph=graph,
        validated_at=VALIDATED_AT,
    )
    codes = {
        issue.code for issue in validated.validation_report.blocking_errors
    }

    assert validated.freshness == "stale"
    assert "BASE_GRAPH_HASH_MISMATCH" in codes
    assert "EXCLUDED_COLUMN_REENABLED" in codes
    assert "SENSITIVITY_WEAKENED" in codes
    assert all(
        metric.compiler_eligibility == "not_eligible"
        for metric in validated.metrics
    )
    assert "SEMANTIC_COLUMN_TECHNICAL_METADATA_MISMATCH" in codes


def test_policy_change_marks_semantic_layer_stale_without_graph_change() -> None:
    graph = adventureworks_graph()
    layer = semantic_draft(graph)
    current_policy = semantic_policy().model_copy(
        update={"default_currency": "USD", "policy_hash": "0" * 64}
    )
    current_policy = current_policy.model_copy(
        update={
            "policy_hash": compute_semantic_policy_hash(current_policy)
        }
    )

    validated = validate_semantic_layer(
        layer=layer,
        graph=graph,
        semantic_policy=current_policy,
        validated_at=VALIDATED_AT,
    )

    assert validated.freshness == "stale"
