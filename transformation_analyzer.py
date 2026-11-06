import json
import pandas as pd
from vertexai.generative_models import GenerativeModel
from source_classifier import resolve_mappings_with_llm, find_source_column

def get_table_creation_query(project_id: str, dataset_id: str, table_name: str) -> str:
    """Derives the query used to load or create a Silver/Gold table by checking BQ job history logs."""
    from google.cloud import bigquery
    client = bigquery.Client(project=project_id)
    regions = ["us", "asia-south1"]
    
    print(f"[Lineage Job Query] Fetching BQ creation SQL for {dataset_id}.{table_name}...")
    for region in regions:
        query = f"""
            SELECT query
            FROM `{project_id}.region-{region}.INFORMATION_SCHEMA.JOBS`
            WHERE destination_table.project_id = '{project_id}'
              AND destination_table.dataset_id = '{dataset_id}'
              AND destination_table.table_id = '{table_name}'
              AND statement_type IN ('MERGE', 'INSERT', 'CREATE_TABLE_AS_SELECT')
            ORDER BY creation_time DESC
            LIMIT 1
        """
        try:
            df = client.query(query).to_dataframe()
            if not df.empty:
                print(f"[Lineage Job Query] Creation query found in region {region}.")
                return df.iloc[0]["query"]
        except Exception:
            pass
    print(f"[Lineage Job Query] Creation query not found in any region.")
    return None

def parse_etl_query(creation_sql: str, dataset_name: str, table_name: str) -> list[dict]:
    """Uses Gemini to parse the historical ETL query and extract mappings for all target columns."""
    print(f"[Lineage Parser] Parsing ETL SQL for {table_name} using Gemini...")
    prompt = f"""
You are an expert BigQuery database engineer.

Given the following SQL query that created or updated the table `{dataset_name}.{table_name}`:
```sql
{creation_sql}
```

Identify how every column in the output table `{table_name}` was loaded from its source table(s) (usually in a bronze dataset).
Specifically, trace:
1. "target_column": the column name in the output table.
2. "source_dataset": the source dataset from which this column originates.
3. "source_table": the source table from which this column originates.
4. "source_column": the source column from which this column originates.
5. "transformation_type": must be one of:
   - "Direct Mapping" (simple column selection or simple rename)
   - "Join" (requires join condition)
   - "Filter" (row filter applied)
   - "Date Filter" (date-based row filter)
   - "Aggregation" (SUM, COUNT, etc.)
   - "Calculated Metric" (arithmetic formulas between columns)
   - "CASE Expression" (conditional logic using CASE WHEN)
   - "Data Cleansing" (COALESCE, TRIM, UPPER, date formatting, duplicate removal)
   - "Type Conversion" (CAST, SAFE_CAST)
6. "transformation_logic": a clear explanation of how the source column was transformed into the target column.
7. "sql_expression": the exact SQL snippet used to generate/calculate this column.
8. "derived_field": "Yes" if it is aggregated, calculated, casted, or conditional; "No" if it is a direct mapping.
9. "business_description": a simple explanation of what this field represents.

Return ONLY a JSON list of objects with these keys:
- "target_column"
- "source_dataset"
- "source_table"
- "source_column"
- "transformation_type"
- "transformation_logic"
- "sql_expression"
- "derived_field"
- "business_description"
"""
    model = GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    text = response.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception as e:
        print(f"[Error] Failed to parse ETL query: {e}. Text: {text}")
        return []

def make_default_mappings(metadata_df: pd.DataFrame, table_name: str) -> list[dict]:
    """Generates default direct mappings when creation SQL log cannot be retrieved."""
    records = []
    tbl_meta = metadata_df[metadata_df["table_name"].str.lower() == table_name.lower()]
    for _, row in tbl_meta.iterrows():
        records.append({
            "target_column": row["column_name"],
            "source_dataset": row["dataset_name"],
            "source_table": row["table_name"],
            "source_column": row["column_name"],
            "transformation_type": "Direct Mapping",
            "transformation_logic": f"Direct mapping of {row['column_name']} into the {table_name} table",
            "sql_expression": row["column_name"],
            "derived_field": "No",
            "business_description": row.get("description", "") or "No description available"
        })
    return records

def analyze_transformations(generated_sql: str, metadata_df: pd.DataFrame, column_details: dict = None) -> pd.DataFrame:
    """Analyzes the transformations each report field went through to reach the final query output."""
    print("[Transformation Analyzer] Analyzing report-level query transformations using Gemini...")
    
    schema_text = metadata_df[["dataset_name", "table_name", "column_name", "data_type"]].drop_duplicates().to_string(index=False)
    column_details_text = json.dumps(column_details, indent=2) if column_details else "No explicit plan annotations."
    
    prompt = f"""
You are an expert BigQuery database analyst.
Given the following SQL query generated to compile a business report:
```sql
{generated_sql}
```

And the metadata schema of the tables involved:
{schema_text}

Business Query Plan Column Specifications (use these for Classification and Business Rules):
{column_details_text}

For each column selected in the final output select list of the query, trace and explain its transformation.
For each report column, provide:
1. "Report Column": the column name or alias in the final output.
2. "Column Type": must be "Direct Column", "Derived Column", or "Formula Column" based on specs.
3. "Business Rule": the business rule or formula description associated with this column.
4. "SQL Expression": the exact SELECT list expression (like a CASE statement or formula) used to produce it.
5. "Transformation Description": a clear, business-friendly explanation of how the column is computed/transformed.
6. "Source Dataset(s)": dataset(s) it originates from.
7. "Source Table(s)": table(s) it originates from.
8. "Source Column(s)": column(s) it originates from.

Return ONLY a JSON list of objects matching the schema below, with no markdown fences, no formatting, and no explanation:
[
  {{
    "Report Column": "",
    "Column Type": "",
    "Business Rule": "",
    "SQL Expression": "",
    "Transformation Description": "",
    "Source Dataset(s)": "",
    "Source Table(s)": "",
    "Source Column(s)": ""
  }}
]
"""
    model = GenerativeModel("gemini-2.5-flash")
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        records = json.loads(text)
    except Exception as e:
        print(f"[Error] Failed to analyze report transformations using LLM: {e}")
        records = []
        
    required_cols = [
        "Report Column", "Column Type", "Business Rule", "SQL Expression",
        "Transformation Description", "Source Dataset(s)", "Source Table(s)", "Source Column(s)"
    ]
    
    if not records:
        # Fallback to a basic structure
        records = []
        llm_mappings = resolve_mappings_with_llm(generated_sql, metadata_df)
        for m in llm_mappings:
            target_tbl = m.get("table_name", "Unknown")
            target_col = m.get("column_name", "Unknown")
            rep_field = m.get("report_field", "Unknown")
            
            # Simple fallback classification
            col_type = "Direct Column"
            rule = ""
            if column_details and rep_field in column_details:
                col_type = column_details[rep_field].get("column_type", "Direct Column")
                rule = column_details[rep_field].get("business_rule", "")
                
            records.append({
                "Report Column": rep_field,
                "Column Type": col_type,
                "Business Rule": rule,
                "SQL Expression": target_col,
                "Transformation Description": f"Mapped directly from {target_tbl}.{target_col}",
                "Source Dataset(s)": m.get("dataset_name", "Unknown"),
                "Source Table(s)": target_tbl,
                "Source Column(s)": target_col
            })
            
    df = pd.DataFrame(records)
    
    if df.empty:
        df = pd.DataFrame(columns=required_cols)
    else:
        for c in required_cols:
            if c not in df.columns:
                df[c] = "Not available"
        df = df[required_cols]
        
    print(f"[Transformation Analyzer] Done. Prepared {len(df)} report column transformation mappings.")
    return df
