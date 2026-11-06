from vertexai.generative_models import GenerativeModel
import json


class SQLGenerator:

    def __init__(self):
        self.model = GenerativeModel(
            "gemini-2.5-flash"
        )

    def identify_assets(
        self,
        user_request,
        metadata_df
    ):

        # Send only the columns needed for table/dataset identification.
        # Sending all metadata columns (data_type, description, etc.) is wasteful here;
        # those are only needed for SQL generation.
        slim_cols = [c for c in ["dataset_name", "table_name", "column_name"] if c in metadata_df.columns]
        schema_text = metadata_df[slim_cols].drop_duplicates().to_string(index=False)

        prompt = f"""
You are a BigQuery metadata expert.

Available Assets:

{schema_text}

User Request:
{user_request}

Return ONLY JSON.

Example:

{{
  "datasets":["gold_insurance_layer"],
  "tables":["policy_master"]
}}
"""

        print(f"[Asset Selection] Sending {len(schema_text):,} chars to Gemini for asset identification...")
        response = self.model.generate_content(
            prompt
        )
        print("[Asset Selection] Gemini response received.")

        text = response.text.strip()

        text = text.replace(
            "```json",
            ""
        ).replace(
            "```",
            ""
        )

        return json.loads(text)

    def generate_sql(
        self,
        user_request,
        metadata_df,
        selected_tables,
        relationship_df=None,
        lineage_df=None,
        date_range=None,
        optional_filters=None
    ):

        schema_rows = metadata_df[
            metadata_df["table_name"].isin(
                selected_tables
            )
        ]

        schema_text = schema_rows.to_string(
            index=False
        )

        relationship_text = self._format_relationship_allowlist(relationship_df)

        lineage_text = "No lineage evidence available."
        if lineage_df is not None and not lineage_df.empty:
            lineage_text = lineage_df.to_string(index=False)

        prompt = f"""
You are a senior BigQuery engineer.

Generate VALID BigQuery SQL.

User Request:
{user_request}

Available Schema:

{schema_text}

APPROVED JOIN PATHS — use ONLY these. Do NOT invent joins on columns not listed below.
If a required join cannot be satisfied by this list, add a SQL comment explaining why
and do not guess at alternative columns.

{relationship_text}

Lineage Evidence:

{lineage_text}

Date Range:
{date_range or "All Time"}

Optional Filters:
{optional_filters or "None"}

Rules:

1. Use only listed tables and columns.
2. Only join tables using the APPROVED JOIN PATHS above. Do not use any other columns as join keys.
3. Do not invent date filters when Date Range is All Time.
4. Support requested aggregations only when required by the user.
5. Generate one read-only SELECT statement in BigQuery Standard SQL.
6. Do not generate DDL, DML, temporary functions, exports, or wildcard table scans.
7. Return SQL only, with no markdown fences.
"""

        response = self.model.generate_content(
            prompt
        )

        sql = response.text.strip()

        sql = sql.replace(
            "```sql",
            ""
        ).replace(
            "```",
            ""
        )

        return sql

    def generate_sql_from_plan(
        self,
        plan: dict,
        resolved_columns: dict,
        joins: list,
        filters: list,
        metadata_df
    ) -> str:
        """Generates standard BigQuery SQL using the resolved Business Query Plan elements."""
        
        # Format resolved columns mapping and column details for prompt
        columns_text = json.dumps(resolved_columns, indent=2)
        column_details_text = json.dumps(plan.get("column_details", {}), indent=2)
        joins_text = json.dumps(joins, indent=2)
        filters_text = json.dumps(filters, indent=2)
        aggregations_text = json.dumps(plan.get("aggregations", []), indent=2)
        sorting_text = json.dumps(plan.get("sorting", []), indent=2)
        grouping_text = json.dumps(plan.get("grouping", []), indent=2)
        
        # Dynamically build a table-to-dataset mapping from metadata
        table_to_dataset = {}
        if metadata_df is not None and not metadata_df.empty:
            for _, row in metadata_df.iterrows():
                tbl = row.get("table_name")
                ds = row.get("dataset_name")
                if tbl and ds:
                    table_to_dataset[tbl] = ds
        table_to_dataset_text = json.dumps(table_to_dataset, indent=2)

        prompt = f"""
You are a senior BigQuery database engineer.
Generate a VALID, highly optimized Standard SQL query using the following verified plan components.

Report Name: {plan.get('report_name')}

Report Column Specifications (includes types, business rules, and dependencies):
{column_details_text}

Resolved Physical Columns (mappings of constituent dependency concepts to database columns):
{columns_text}

Tables and Approved JOINS (INNER/LEFT):
{joins_text}

Filters (WHERE conditions):
{filters_text}

Aggregations:
{aggregations_text}

Grouping:
{grouping_text}

Sorting:
{sorting_text}

Table to Dataset Mapping (Use these datasets to qualify each table):
{table_to_dataset_text}

Rules:
1. SELECT exactly the columns specified in "Report Column Specifications". The select list aliases MUST match the report column names exactly.
2. For each report column:
   - If "column_type" is "Direct Column", select its physical column from "Resolved Physical Columns".
   - If "column_type" is "Derived Column", construct the SQL CASE WHEN or conditional expression using the physical column(s) of its dependencies.
   - If "column_type" is "Formula Column", construct the mathematical formula, arithmetic expression, or aggregate calculation (like SAFE_DIVIDE, SUM, COUNT, etc.) using the physical column(s) of its dependencies.
3. Join the tables exactly as specified in the JOINS list. Do not use any other columns or tables for joins.
4. Apply all filters in 'Filters (WHERE conditions)'. Do not hardcode values that are not in the filter spec.
5. Support SELECT, WHERE, INNER JOIN, LEFT JOIN, GROUP BY, HAVING, ORDER BY, DISTINCT, CASE, COUNT, SUM, AVG, MIN, MAX, and Window Functions where applicable.
6. Do not generate DDL, DML, temporary functions, or wildcard table scans.
7. For each table referenced in the query, you MUST qualify it fully using the project ID 'anz-cloud-migration' and its correct dataset name from the 'Table to Dataset Mapping' above in backticks.
   Format: `anz-cloud-migration.dataset_name.table_name`
   Never reference a table as just `table` or `dataset.table` without the project prefix.
8. Return ONLY the valid BigQuery SQL query with no markdown formatting and no explanations.
"""
        print("[SQL Generator] Sending plan components to Gemini for SQL compilation...")
        response = self.model.generate_content(prompt)
        sql = response.text.strip()
        sql = sql.replace("```sql", "").replace("```", "").strip()
        return sql

    def _format_relationship_allowlist(self, relationship_df) -> str:
        """Format the relationship DataFrame as a human-readable allowlist block.

        Each edge is rendered as:
          [HIGH]   left_table.left_col  →  right_table.right_col  (evidence | confidence: X.XX | join: TYPE)

        If no relationships are available, a clear warning is returned so the
        LLM knows not to attempt any joins.
        """
        import pandas as pd

        if relationship_df is None or (
            isinstance(relationship_df, pd.DataFrame) and relationship_df.empty
        ):
            return (
                "No approved join paths available. "
                "Do NOT join any tables — query each table independently or use subqueries."
            )

        lines = []
        for _, row in relationship_df.iterrows():
            confidence = float(row.get("confidence", 0))
            label = "HIGH" if confidence >= 0.85 else ("MEDIUM" if confidence >= 0.70 else "LOW")
            evidence = row.get("evidence", "")
            join_type = row.get("join_type", "LEFT")
            lines.append(
                f"  [{label:6}] "
                f"{row['left_table']}.{row['left_column']}  →  "
                f"{row['right_table']}.{row['right_column']}  "
                f"(evidence: {evidence} | confidence: {confidence:.2f} | join: {join_type})"
            )

        return "\n".join(lines) if lines else (
            "No approved join paths available. "
            "Do NOT join any tables — query each table independently."
        )