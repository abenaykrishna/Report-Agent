import pandas as pd
import json
from vertexai.generative_models import GenerativeModel

def classify_source(table_metadata: dict) -> str:
    """Classifies a table source as PAS, CRM, or UNKNOWN.
    
    table_metadata can contain keys like:
      - table_name
      - dataset_name
      - description / Business Description
    """
    table_name = str(table_metadata.get("table_name", "")).lower()
    dataset_name = str(table_metadata.get("dataset_name", "")).lower()
    description = str(table_metadata.get("description", table_metadata.get("Business Description", ""))).lower()

    # Rule 1: CRM keywords in table name or dataset
    if any(k in table_name or k in dataset_name for k in ["crm", "agent"]):
        return "CRM"

    # Rule 2: PAS keywords (policy, claim, customer, renewal, sales, provider, hospital)
    pas_keywords = [
        "policy", "claim", "customer", "renewal", "sales", 
        "provider", "hospital", "lapse", "financial"
    ]
    if any(k in table_name or k in dataset_name for k in pas_keywords):
        return "PAS"

    # Rule 3: Description checks
    if "crm" in description or "agent" in description:
        return "CRM"
    if any(k in description for k in pas_keywords):
        return "PAS"

    return "UNKNOWN"

def find_source_column(report_field: str, metadata_df: pd.DataFrame) -> dict:
    """Finds the best matching source column for a report field from metadata_df using similarity scoring."""
    best_score = 0
    best_match = None
    
    rf_lower = report_field.lower()
    
    for _, row in metadata_df.iterrows():
        col_name = str(row["column_name"])
        col_lower = col_name.lower()
        
        score = 0
        if col_lower == rf_lower:
            score = 100
        elif rf_lower.startswith(col_lower) or rf_lower.endswith(col_lower):
            score = 80
        elif col_lower in rf_lower:
            # Score proportional to length to favor more specific matches
            score = 50 + len(col_lower)
        elif rf_lower in col_lower:
            score = 30 + len(rf_lower)
            
        if score > best_score:
            best_score = score
            best_match = row
            
    if best_match is not None:
        desc_val = best_match.get("description", best_match.get("Business Description", ""))
        # Handle cases where description might be pd.NA or NaN
        if pd.isna(desc_val):
            desc_val = ""
        return {
            "dataset_name": best_match["dataset_name"],
            "table_name": best_match["table_name"],
            "column_name": best_match["column_name"],
            "data_type": best_match["data_type"],
            "description": desc_val
        }
    return None

def find_upstream_source(table_name: str, lineage_df: pd.DataFrame) -> str:
    """Finds upstream lineage sources for a given table name from lineage_df."""
    if lineage_df is None or lineage_df.empty:
        return "Not available"
        
    upstreams = []
    
    # Standardize column search
    target_col = None
    for col in ["Target Table", "Target_Table"]:
        if col in lineage_df.columns:
            target_col = col
            break
            
    if not target_col:
        return "Not available"
        
    matches = lineage_df[lineage_df[target_col].str.lower() == table_name.lower()]
    
    for _, row in matches.iterrows():
        if "Source FQN" in lineage_df.columns and pd.notna(row["Source FQN"]):
            upstreams.append(str(row["Source FQN"]))
        elif "Source Table" in lineage_df.columns and pd.notna(row["Source Table"]):
            src_ds = row.get("Source Dataset", row.get("Source_Dataset", ""))
            src_tbl = row["Source Table"]
            if src_ds:
                upstreams.append(f"{src_ds}.{src_tbl}")
            else:
                upstreams.append(str(src_tbl))
        elif "Source_Table" in lineage_df.columns and pd.notna(row["Source_Table"]):
            src_ds = row.get("Source_Dataset", "")
            src_tbl = row["Source_Table"]
            if src_ds:
                upstreams.append(f"{src_ds}.{src_tbl}")
            else:
                upstreams.append(str(src_tbl))
                
    if upstreams:
        # Deduplicate and format
        return ", ".join(list(set(upstreams)))
    return "No upstream lineage found"

def resolve_mappings_with_llm(generated_sql: str, metadata_df: pd.DataFrame) -> list[dict]:
    """Uses Gemini to resolve each query output column back to its original source dataset, table, and column."""
    schema_text = metadata_df[["dataset_name", "table_name", "column_name", "data_type"]].drop_duplicates().to_string(index=False)
    
    prompt = f"""
You are an expert BigQuery database engineer.

Given the following BigQuery SQL query:
```sql
{generated_sql}
```

And the schemas of the tables referenced:
{schema_text}

For each column/alias in the final SELECT list of the query, identify the original source dataset, table, and column it originates from. If a column is an aggregation (like SUM or AVG) or expression (like COALESCE or SAFE_DIVIDE), map it to the primary column being aggregated or evaluated. For calculated ratios or formulas involving multiple columns, map to the main column representing the numerator or the first column.

Return ONLY a JSON list of objects with the following keys:
- "report_field": the alias or column name in the output query
- "dataset_name": the source dataset name
- "table_name": the source table name
- "column_name": the source column name

Example:
[
  {{
    "report_field": "total_claimed_amount",
    "dataset_name": "phi_silver_raw_us",
    "table_name": "both_claims_data_primary_raw_raw",
    "column_name": "Claim_total"
  }}
]
"""
    model = GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(prompt)
    
    text = response.text.strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except Exception as e:
        print(f"[Error] Failed to parse LLM mapping resolution: {e}. Text: {text}")
        return []
