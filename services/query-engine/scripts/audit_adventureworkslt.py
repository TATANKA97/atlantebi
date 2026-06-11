from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app.drivers.base import ConnectionMetadata, DatabaseCredentials  # noqa: E402
from app.drivers.sqlserver import (  # noqa: E402
    SqlServerDriver,
    _connection_string_parts,
)
from app.models import Engine, SchemaIntrospectionResponse  # noqa: E402


EXPECTED_COUNTS = {
    "objects_total": 13,
    "tables": 10,
    "views": 3,
    "columns": 129,
    "foreign_keys": 12,
    "indexes_total": 31,
    "table_indexes": 30,
    "view_indexes": 1,
    "view_definitions": 3,
    "view_lineage": 3,
}

EXPECTED_VIEW_COLUMNS = {
    "SalesLT.vGetAllCategories": [
        "ParentProductCategoryName",
        "ProductCategoryName",
        "ProductCategoryID",
    ],
    "SalesLT.vProductAndDescription": [
        "ProductID",
        "Name",
        "ProductModel",
        "Culture",
        "Description",
    ],
}

JOIN_AUDIT_QUERIES = {
    "sales_order_detail_header": """
select
  count_big(*) as detail_rows,
  count_big(header.SalesOrderID) as matched_rows,
  count_big(*) - count_big(header.SalesOrderID) as orphan_rows
from SalesLT.SalesOrderDetail detail
left join SalesLT.SalesOrderHeader header
  on header.SalesOrderID = detail.SalesOrderID
""",
    "sales_order_detail_product": """
select
  count_big(*) as detail_rows,
  count_big(product.ProductID) as matched_rows,
  count_big(*) - count_big(product.ProductID) as orphan_rows
from SalesLT.SalesOrderDetail detail
left join SalesLT.Product product
  on product.ProductID = detail.ProductID
""",
    "product_category": """
select
  count_big(*) as product_rows,
  count_big(category.ProductCategoryID) as matched_rows,
  count_big(*) - count_big(category.ProductCategoryID) as without_category
from SalesLT.Product product
left join SalesLT.ProductCategory category
  on category.ProductCategoryID = product.ProductCategoryID
""",
    "category_parent": """
select count_big(*) as orphan_parent_categories
from SalesLT.ProductCategory category
left join SalesLT.ProductCategory parent
  on parent.ProductCategoryID = category.ParentProductCategoryID
where category.ParentProductCategoryID is not null
  and parent.ProductCategoryID is null
""",
}

EXPECTED_JOIN_AUDITS = {
    "sales_order_detail_header": [542, 542, 0],
    "sales_order_detail_product": [542, 542, 0],
    "product_category": [295, 295, 0],
    "category_parent": [0],
}


def required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def build_connection() -> ConnectionMetadata:
    return ConnectionMetadata(
        tenant_id="00000000-0000-4000-8000-000000000001",
        connection_id="00000000-0000-4000-8000-000000000002",
        name="AdventureWorksLT audit",
        engine=Engine.sqlserver,
        network_mode="public_allowlist",
        host=required_environment("ADVENTUREWORKSLT_HOST"),
        port=int(os.getenv("ADVENTUREWORKSLT_PORT", "1433")),
        database_name=os.getenv("ADVENTUREWORKSLT_DATABASE", "AdventureWorksLT"),
        username=required_environment("ADVENTUREWORKSLT_USERNAME"),
        secret_ref="gcp-secret-manager://projects/audit/secrets/not-used",
        tls_required=os.getenv("ADVENTUREWORKSLT_TLS", "true").lower() == "true",
        trust_server_certificate=(
            os.getenv("ADVENTUREWORKSLT_TRUST_SERVER_CERTIFICATE", "false").lower()
            == "true"
        ),
        tls_server_name=os.getenv("ADVENTUREWORKSLT_TLS_SERVER_NAME"),
    )


def snapshot_counts(snapshot: Any) -> dict[str, int]:
    views = [table for table in snapshot.tables if table.table_type == "view"]
    return {
        "objects_total": len(snapshot.tables),
        "tables": sum(table.table_type == "base_table" for table in snapshot.tables),
        "views": len(views),
        "columns": sum(len(table.columns) for table in snapshot.tables),
        "foreign_keys": len(snapshot.foreign_keys),
        "indexes_total": len(snapshot.indexes),
        "table_indexes": sum(index.object_type == "table" for index in snapshot.indexes),
        "view_indexes": sum(index.object_type == "view" for index in snapshot.indexes),
        "view_definitions": sum(
            view.view_definition_available is True for view in views
        ),
        "view_lineage": sum(view.lineage_available is True for view in views),
    }


def load_persisted_snapshot(path: Path) -> SchemaIntrospectionResponse:
    return SchemaIntrospectionResponse.model_validate_json(path.read_text("utf-8"))


def validate_views(snapshot: Any) -> list[str]:
    errors: list[str] = []
    by_name = {
        f"{table.table_schema}.{table.name}": table
        for table in snapshot.tables
        if table.table_type == "view"
    }
    for view_name, expected_columns in EXPECTED_VIEW_COLUMNS.items():
        view = by_name.get(view_name)
        if view is None:
            errors.append(f"missing view {view_name}")
        elif [column.name for column in view.columns] != expected_columns:
            errors.append(f"column mismatch for {view_name}")
    catalog_view = by_name.get("SalesLT.vProductModelCatalogDescription")
    if catalog_view is None or len(catalog_view.columns) != 25:
        errors.append("SalesLT.vProductModelCatalogDescription must have 25 columns")
    return errors


def run_join_audits(connection_string: str) -> dict[str, list[int]]:
    import pyodbc

    connection = pyodbc.connect(connection_string, autocommit=True, timeout=30)
    try:
        cursor = connection.cursor()
        return {
            name: [int(value) for value in cursor.execute(query).fetchone()]
            for name, query in JOIN_AUDIT_QUERIES.items()
        }
    finally:
        connection.close()


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-json", required=True, type=Path)
    arguments = parser.parse_args()
    connection = build_connection()
    credentials = DatabaseCredentials(
        password=required_environment("ADVENTUREWORKSLT_PASSWORD")
    )
    live = await SqlServerDriver().introspect_schema(
        connection=connection,
        credentials=credentials,
        timeout_ms=120_000,
    )
    persisted = load_persisted_snapshot(arguments.snapshot_json)
    live_counts = snapshot_counts(live)
    persisted_counts = snapshot_counts(persisted)

    connection_string = ";".join(
        _connection_string_parts(connection, credentials, 30)
    )
    join_audits = run_join_audits(connection_string)
    errors = [
        *(f"live {key}: expected {value}, got {live_counts.get(key)}"
          for key, value in EXPECTED_COUNTS.items()
          if live_counts.get(key) != value),
        *(f"persisted {key}: expected {value}, got {persisted_counts.get(key)}"
          for key, value in EXPECTED_COUNTS.items()
          if persisted_counts.get(key) != value),
        *validate_views(live),
        *validate_views(persisted),
    ]
    if live.schema_hash != persisted.schema_hash:
        errors.append("live and persisted schema_hash differ")
    if persisted.coverage_status != "partial":
        errors.append(
            f"persisted coverage_status: expected partial, got {persisted.coverage_status}"
        )
    if not any(
        index.schema_name == "SalesLT"
        and index.table_name == "vProductAndDescription"
        and index.name == "IX_vProductAndDescription"
        and index.object_type == "view"
        and index.is_unique
        for index in persisted.indexes
    ):
        errors.append("IX_vProductAndDescription is missing or invalid")
    for name, expected in EXPECTED_JOIN_AUDITS.items():
        if join_audits.get(name) != expected:
            errors.append(
                f"join audit {name}: expected {expected}, got {join_audits.get(name)}"
            )

    print(
        json.dumps(
            {
                "ok": not errors,
                "live_counts": live_counts,
                "persisted_counts": persisted_counts,
                "coverage_status": persisted.coverage_status,
                "schema_hash_match": live.schema_hash == persisted.schema_hash,
                "join_audits": join_audits,
                "errors": errors,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
