from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration
from bigquery_service import BigQueryService
from metadata_service import DualMetadataService
from lineage_service import DualLineageService
from looker_service import LookerService
from excel_service import ExcelService
from discovery_service import DiscoveryService
from sql_generator import SQLGenerator
from relationship_service import RelationshipService
import pandas as pd
import json
import os
import re
from source_classifier import classify_source, find_source_column, find_upstream_source, resolve_mappings_with_llm
from transformation_analyzer import analyze_transformations

class InsuranceReportAgent:
    def __init__(self, project_id: str = "anz-cloud-migration"):
        self.project_id = project_id
        
        # Instantiate LIVE services
        self.bq_service = BigQueryService(project_id=self.project_id)
        self.metadata_service = DualMetadataService(project_id=self.project_id)
        self.lineage_service = DualLineageService(project_id=self.project_id)
        self.looker_service = LookerService()
        
        self.setup_agent_tools()
        self.discovery_service = DiscoveryService(project_id=self.project_id)
        self.sql_generator = SQLGenerator()
        self.relationship_service = RelationshipService()

    def setup_agent_tools(self):
        execute_report_decl = FunctionDeclaration(
            name="execute_report_generation",
            description="Executes pipeline to compile and generate formatted workbooks. ALWAYS use this tool to fulfill report requests.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "report_name": {
                        "type": "STRING",
                        "description": "The complete natural-language report request. Use the user's prompt when no explicit title is provided."
                    },
                    "date_range": {
                        "type": "STRING",
                        "description": "Optional date range. Use 'All Time' when the user does not specify dates."
                    },
                    "optional_filters": {
                        "type": "STRING",
                        "description": "Optional filters explicitly requested by the user."
                    }
                },
                "required": ["report_name"]
            }
        )
        self.agent_tools = Tool(function_declarations=[execute_report_decl])
        self.model = GenerativeModel("gemini-2.5-flash", tools=[self.agent_tools])

    def execute_report_generation(
        self,
        report_name: str,
        date_range: str = "All Time",
        optional_filters: str = None,
        user_prompt: str = None,
    ) -> str:
        return self.execute_report_pipeline(
            user_prompt=user_prompt or report_name,
            report_name=report_name,
            date_range=date_range,
            optional_filters=optional_filters,
            is_excel=False
        )

    def execute_report_pipeline(
        self,
        user_prompt: str,
        report_name: str = None,
        date_range: str = "All Time",
        optional_filters: str = None,
        is_excel: bool = False,
        progress_callback = None
    ) -> str:
        print(f"\n[Agent] Initiating Unified Pipeline for input: '{user_prompt}'")
        if progress_callback:
            progress_callback("Reading input...", 5)
        
        try:
            # =====================================================
            # STEP 1: Input Parsing & Query Understanding
            # =====================================================
            print("\n[Step 1] Parsing input and performing Query Understanding...")
            if progress_callback:
                progress_callback("Extracting report requirements...", 10)
            
            parsed_columns = []
            expected_sources = {}
            business_description = ""
            
            if is_excel:
                from template_parser import TemplateParser
                parsed_template = TemplateParser.parse_template(user_prompt)
                report_name = parsed_template["report_name"]
                parsed_columns = parsed_template["required_columns"]
                columns_details = parsed_template["columns_details"]
                business_description = parsed_template["business_description"]
                
                # Query understanding based on Excel details
                plan_prompt = f"""
You are an expert insurance business analyst. Given the parsed Excel template details:
Report Name: {report_name}
Description: {business_description}
Parsed Columns: {json.dumps(columns_details, indent=2)}

You must build a Business Query Plan.
For each parsed column:
1. Classify its "column_type" as one of:
   - "Direct Column" (maps directly to a database column)
   - "Derived Column" (requires logic like CASE WHEN conditional statements)
   - "Formula Column" (requires mathematical formulas, aggregates like SUM/COUNT, or window functions)
2. Extract or formulate the "business_rule" describing the calculation or logic.
3. Extract "dependencies" which are a list of the underlying database columns/business concepts (in simple English) needed to compute this column. For a direct column, its only dependency is itself.
4. Extract "expected_source" from the parsed template details if present.

Also identify:
- "business_filters": list of business filters (e.g. [[{{"concept": "Dropped Leads"}}]]).
- "aggregations": list of aggregations (e.g. sum of premium).
- "sorting": sorting requirements.
- "grouping": grouping requirements.

Return ONLY a JSON object with this schema (no markdown fences, no explanation):
{{
  "report_name": "{report_name}",
  "required_columns": {json.dumps(parsed_columns)},
  "column_details": {{
    "Column Name": {{
      "name": "Column Name",
      "column_type": "Direct Column",
      "business_rule": "",
      "dependencies": ["Column Name"],
      "expected_source": ""
    }}
  }},
  "business_filters": [],
  "aggregations": [],
  "sorting": [],
  "grouping": []
}}
"""
                response = self.model.generate_content(plan_prompt)
                text = response.text.strip()
                text = text.replace("```json", "").replace("```", "").strip()
                plan_res = json.loads(text)
                
                business_query_plan = {
                    "report_name": report_name,
                    "required_columns": parsed_columns,
                    "column_details": plan_res.get("column_details", {}),
                    "business_filters": plan_res.get("business_filters", []),
                    "aggregations": plan_res.get("aggregations", []),
                    "sorting": plan_res.get("sorting", []),
                    "grouping": plan_res.get("grouping", [])
                }
            else:
                # Natural language input query understanding
                plan_prompt = f"""
You are an expert insurance business analyst. Given the report request prompt:
"{user_prompt}"

You must build a Business Query Plan.
Identify:
1. "report_name": a descriptive clean name for the report.
2. "required_columns": the list of clean column names/headers needed for the report.
3. For each required column:
   - Classify its "column_type" as one of:
     - "Direct Column" (maps directly to a database column)
     - "Derived Column" (requires logic like CASE WHEN conditional statements)
     - "Formula Column" (requires mathematical formulas, aggregates like SUM/COUNT, or window functions)
   - Formulate the "business_rule" describing the calculation or logic if implied by the column or request.
   - Extract "dependencies": a list of the underlying database columns/business concepts (in simple English) needed to compute this column. For a direct column, its only dependency is itself.
   - "expected_source": the expected system or source (e.g. "PAS", "CRM") if implied by the column or request.
4. "business_filters": list of business concept filters (e.g., [[{{"concept": "Active Policies"}}, {{"concept": "premium greater than 5000"}}]]).
5. "aggregations": list of aggregates.
6. "sorting": sorting.
7. "grouping": grouping.

Return ONLY a JSON object matching this schema (no markdown fences, no explanation):
{{
  "report_name": "",
  "required_columns": [],
  "column_details": {{
    "Column Name": {{
      "name": "Column Name",
      "column_type": "Direct Column",
      "business_rule": "",
      "dependencies": ["Column Name"],
      "expected_source": ""
    }}
  }},
  "business_filters": [],
  "aggregations": [],
  "sorting": [],
  "grouping": []
}}
"""
                response = self.model.generate_content(plan_prompt)
                text = response.text.strip()
                text = text.replace("```json", "").replace("```", "").strip()
                business_query_plan = json.loads(text)
                if not business_query_plan.get("report_name"):
                    business_query_plan["report_name"] = report_name or "Custom Report"
                    
            print(f"\n[Business Query Plan] generated successfully:\n{json.dumps(business_query_plan, indent=2)}")

            # =====================================================
            # STEP 2: Metadata Discovery
            # =====================================================
            print("\n[Step 2] Discovering assets and schemas...")
            if progress_callback:
                progress_callback("Searching Dataplex Metadata...", 20)
            
            all_metadata = self.discovery_service.discover_assets()
            if all_metadata.empty:
                raise Exception("No metadata discovered in project.")

            if progress_callback:
                progress_callback("Searching Dataplex Metadata...", 25, {"metadata_search_status": "Success"})

            # Collect unique dependencies to discover instead of direct column headers
            concepts_to_discover = set()
            for col_name, details in business_query_plan.get("column_details", {}).items():
                deps = details.get("dependencies", [])
                if deps:
                    concepts_to_discover.update(deps)
                else:
                    concepts_to_discover.add(col_name)
            for col_name in business_query_plan["required_columns"]:
                if col_name not in business_query_plan.get("column_details", {}):
                    concepts_to_discover.add(col_name)
                    
            concepts_to_discover = sorted(list(concepts_to_discover))
            print(f"[Metadata Discovery] Concepts to map to physical columns: {concepts_to_discover}")
            
            # Map report business column names to physical column names using Gemini
            print("\n[Metadata Discovery] Mapping business concepts to physical columns...")
            concept_mappings = self._map_concepts_to_columns(concepts_to_discover, all_metadata)
            print(f"Mapped concepts:\n{json.dumps(concept_mappings, indent=2)}")

            # Resolve dataset locations and enforce single-location query constraints (avoid cross-region joins)
            unique_datasets = all_metadata["dataset_name"].dropna().unique()
            dataset_locations = self._get_dataset_locations(unique_datasets)
            print(f"Dataset locations: {dataset_locations}")
            
            location_scores = {}
            for req_col, physical_names in concept_mappings.items():
                for _, row in all_metadata.iterrows():
                    if row["column_name"] in physical_names:
                        loc = dataset_locations.get(row["dataset_name"], "US")
                        if loc not in location_scores:
                            location_scores[loc] = set()
                        location_scores[loc].add(req_col)
                        
            dominant_location = "US"
            if location_scores:
                dominant_location = max(location_scores.keys(), key=lambda k: len(location_scores[k]))
            print(f"Dominant Location: {dominant_location} (satisfies: {list(location_scores.get(dominant_location, []))})")
            
            filtered_concept_mappings = {}
            for req_col, physical_names in concept_mappings.items():
                valid_phys = []
                for p_name in physical_names:
                    match_meta = all_metadata[all_metadata["column_name"] == p_name]
                    for _, row in match_meta.iterrows():
                        if dataset_locations.get(row["dataset_name"], "US") == dominant_location:
                            valid_phys.append(p_name)
                            break
                if valid_phys:
                    filtered_concept_mappings[req_col] = list(set(valid_phys))
            concept_mappings = filtered_concept_mappings
            print(f"Location-scoped concept mappings:\n{json.dumps(concept_mappings, indent=2)}")

            # =====================================================
            # STEP 3: Column Source Selection (Coverage Scoring)
            # =====================================================
            print("\n[Step 3] Selecting column sources via Coverage Score algorithm...")
            if progress_callback:
                progress_callback("Selecting optimal source tables...", 30)
            unique_tables = all_metadata["table_name"].dropna().unique()
            table_coverage = {}
            for table in unique_tables:
                score = 0
                table_cols = all_metadata[all_metadata["table_name"] == table]["column_name"].tolist()
                for req_col, physical_names in concept_mappings.items():
                    if any(p in table_cols for p in physical_names):
                        score += 1
                table_coverage[table] = score
                
            resolved_columns = {}
            selected_tables = set()
            selected_datasets = set()
            for req_col, physical_names in concept_mappings.items():
                candidates = []
                for _, row in all_metadata.iterrows():
                    if row["column_name"] in physical_names:
                        tbl = row["table_name"]
                        ds = row["dataset_name"]
                        score = table_coverage.get(tbl, 0)
                        candidates.append((tbl, row["column_name"], ds, score))
                if candidates:
                    candidates.sort(key=lambda x: x[3], reverse=True)
                    best = candidates[0]
                    resolved_columns[req_col] = {
                        "dataset_name": best[2],
                        "table_name": best[0],
                        "column_name": best[1]
                    }
                    selected_tables.add(best[0])
                    selected_datasets.add(best[2])
                    
            print(f"Resolved Column Mapping:\n{json.dumps(resolved_columns, indent=2)}")
            if progress_callback:
                progress_callback("Selecting optimal source tables...", 35, {
                    "datasets_used": sorted(list(selected_datasets)),
                    "tables_used": sorted(list(selected_tables))
                })

            # =====================================================
            # STEP 4: Join Discovery
            # =====================================================
            print("\n[Step 4] Resolving required table joins...")
            if progress_callback:
                progress_callback("Discovering joins...", 40)
            active_tables, joins = self._discover_joins(list(selected_tables), all_metadata)
            print(f"Active tables for query: {active_tables}")
            print(f"Discovered Join Path list: {json.dumps(joins, indent=2)}")
            if progress_callback:
                # Also update tables_used here since active_tables includes joined tables
                progress_callback("Discovering joins...", 45, {
                    "tables_used": sorted(list(active_tables))
                })

            # =====================================================
            # STEP 5: Business Filter Discovery
            # =====================================================
            print("\n[Step 5] Resolving physical filter conditions...")
            if progress_callback:
                progress_callback("Generating SQL...", 50)
            
            raw_filters = business_query_plan.get("business_filters", [])
            flat_filters = []
            for f in raw_filters:
                if isinstance(f, list):
                    flat_filters.extend(f)
                else:
                    flat_filters.append(f)
            business_query_plan["business_filters"] = flat_filters
            
            resolved_filters = self._discover_filters(business_query_plan["business_filters"], active_tables, all_metadata)
            if date_range and date_range != "All Time":
                # Add a filter on expiry_date for the date range
                resolved_filters.append("expiry_date IS NOT NULL")
            if optional_filters:
                resolved_filters.append(optional_filters)
            print(f"Resolved Filter conditions: {resolved_filters}")

            # =====================================================
            # STEP 6: SQL Generation
            # =====================================================
            print("\n[Step 6] Generating Dynamic SQL...")
            if progress_callback:
                progress_callback("Generating SQL...", 55)
            generated_sql = self.sql_generator.generate_sql_from_plan(
                plan=business_query_plan,
                resolved_columns=resolved_columns,
                joins=joins,
                filters=resolved_filters,
                metadata_df=all_metadata
            )
            print("\nGenerated SQL:\n")
            print(generated_sql)

            # =====================================================
            # STEP 7: Audit and Validation (Dry Run)
            # =====================================================
            print("\n[Step 7] Auditing joins and validating SQL...")
            if progress_callback:
                progress_callback("Generating SQL...", 60)
            relationship_df = self.relationship_service.infer_relationships(all_metadata, active_tables)
            self._audit_joins(generated_sql, relationship_df)
            
            # Dry-run validation & repair loop
            MAX_REPAIR_ATTEMPTS = 5
            for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
                is_valid, error_msg = self.bq_service.validate_query_with_error(generated_sql, location=dominant_location.lower())
                if is_valid:
                    break
                print(f"\n[SQL Repair] Attempt {attempt}/{MAX_REPAIR_ATTEMPTS} - validation error: {error_msg}")
                if attempt == MAX_REPAIR_ATTEMPTS:
                    raise Exception(f"SQL failed validation after {MAX_REPAIR_ATTEMPTS} attempts: {error_msg}")
                generated_sql = self._repair_sql(generated_sql, error_msg, all_metadata, relationship_df)
                print("\n[SQL Repair] Repaired SQL:\n")
                print(generated_sql)
                self._audit_joins(generated_sql, relationship_df)

            # =====================================================
            # STEP 8: BigQuery Execution
            # =====================================================
            print("\n[Step 8] Executing query against BigQuery...")
            if progress_callback:
                progress_callback("Executing BigQuery query...", 65)
            report_df = self.bq_service.execute_query(generated_sql, location=dominant_location.lower())
            if progress_callback:
                progress_callback("Executing BigQuery query...", 75, {"sql_execution_status": "Success"})
            
            # Fetch raw data for selected tables
            print("\n[Step 8b] Fetching raw data for Main Report sheet...")
            raw_frames = []
            for tbl in active_tables:
                match_meta = all_metadata[all_metadata["table_name"] == tbl]
                if not match_meta.empty:
                    ds = match_meta.iloc[0]["dataset_name"]
                    raw_sql = f"SELECT * FROM `{self.project_id}.{ds}.{tbl}` LIMIT 5000"
                    try:
                        raw_table_df = self.bq_service.execute_query(raw_sql, location=dominant_location.lower())
                        if not raw_table_df.empty:
                            raw_table_df.insert(0, "_source_table", tbl)
                            raw_frames.append(raw_table_df)
                    except Exception as e:
                        print(f"[Raw Data] Could not fetch {tbl}: {e}")
            raw_df = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()
            print(f"[Raw Data] Loaded {len(raw_df)} rows across active tables.")

            # =====================================================
            # STEP 9: Fetch Lineage
            # =====================================================
            print("\n[Step 9] Fetching lineage traces...")
            if progress_callback:
                progress_callback("Searching Dataplex Lineage...", 80)
            lineage_frames = []
            for tbl in active_tables:
                match_meta = all_metadata[all_metadata["table_name"] == tbl]
                if not match_meta.empty:
                    ds = match_meta.iloc[0]["dataset_name"]
                    try:
                        lineage_df = self.lineage_service.get_lineage_via_dataplex(ds, tbl)
                        if lineage_df.empty:
                            lineage_df = self.lineage_service.get_lineage_via_bigquery(ds, tbl)
                            if not lineage_df.empty:
                                lineage_df = lineage_df.rename(columns={
                                    "Target_Table": "Target Table",
                                    "Source_Dataset": "Source Dataset",
                                    "Source_Table": "Source Table"
                                })
                        if not lineage_df.empty:
                            lineage_frames.append(lineage_df)
                    except Exception as e:
                        print(f"[Lineage] Lineage unavailable for {ds}.{tbl}: {e}")
            lineage_df = pd.concat(lineage_frames, ignore_index=True) if lineage_frames else pd.DataFrame()
            if progress_callback:
                progress_callback("Searching Dataplex Lineage...", 85, {"lineage_search_status": "Success" if not lineage_df.empty else "No Lineage Found"})

            # =====================================================
            # STEP 10: Mapping Sheets Generation & Classification
            # =====================================================
            print("\n[Step 10] Building mapping sheets...")
            if progress_callback:
                progress_callback("Generating Metadata...", 90)
            pas_mappings = []
            crm_mappings = []
            
            for col in report_df.columns:
                match_info = None
                
                # Check column details first for expected source
                col_spec = business_query_plan.get("column_details", {}).get(col, {})
                expected_src = col_spec.get("expected_source", "")
                
                # Try to find match_info from resolved_columns or fallback
                for req_col, spec in resolved_columns.items():
                    if req_col.lower() == col.lower() or spec["column_name"].lower() == col.lower():
                        meta_match = all_metadata[
                            (all_metadata["column_name"].str.lower() == spec["column_name"].lower()) &
                            (all_metadata["table_name"].str.lower() == spec["table_name"].lower())
                        ]
                        if not meta_match.empty:
                            row = meta_match.iloc[0]
                            match_info = {
                                "dataset_name": row["dataset_name"],
                                "table_name": row["table_name"],
                                "column_name": row["column_name"],
                                "data_type": row["data_type"],
                                "description": row.get("description", "") or "No description available"
                            }
                            break
                            
                # If it's a formula/derived column with dependencies, find the primary dependency's source
                if not match_info and col_spec:
                    deps = col_spec.get("dependencies", [])
                    for dep in deps:
                        spec = resolved_columns.get(dep)
                        if spec:
                            meta_match = all_metadata[
                                (all_metadata["column_name"].str.lower() == spec["column_name"].lower()) &
                                (all_metadata["table_name"].str.lower() == spec["table_name"].lower())
                            ]
                            if not meta_match.empty:
                                row = meta_match.iloc[0]
                                match_info = {
                                    "dataset_name": row["dataset_name"],
                                    "table_name": row["table_name"],
                                    "column_name": row["column_name"],
                                    "data_type": row["data_type"],
                                    "description": row.get("description", "") or "No description available"
                                }
                                break
                                
                if not match_info:
                    match_info = find_source_column(col, all_metadata)
                    
                if match_info:
                    source_sys = classify_source(match_info)
                    # Override source system if explicitly specified in template
                    if expected_src:
                        if "PAS" in expected_src.upper():
                            source_sys = "PAS"
                        elif "CRM" in expected_src.upper():
                            source_sys = "CRM"
                            
                    upstream = find_upstream_source(match_info["table_name"], lineage_df)
                    mapping_record = {
                        "Report Field": col,
                        "Source Dataset": match_info["dataset_name"],
                        "Source Table": match_info["table_name"],
                        "Source Column": match_info["column_name"],
                        "Data Type": match_info["data_type"],
                        "Business Description": match_info["description"] or "No description available",
                        "Upstream Source": upstream
                    }
                    if source_sys == "PAS":
                        pas_mappings.append(mapping_record)
                    elif source_sys == "CRM":
                        crm_mappings.append(mapping_record)
                        
            pas_mapping_df = pd.DataFrame(pas_mappings) if pas_mappings else pd.DataFrame(columns=[
                "Report Field", "Source Dataset", "Source Table", "Source Column", "Data Type", "Business Description", "Upstream Source"
            ])
            crm_mapping_df = pd.DataFrame(crm_mappings) if crm_mappings else pd.DataFrame(columns=[
                "Report Field", "Source Dataset", "Source Table", "Source Column", "Data Type", "Business Description", "Upstream Source"
            ])
            
            # Enrich metadata_df with Source System classification
            enriched_metadata_df = all_metadata[all_metadata["table_name"].isin(active_tables)].copy()
            if not enriched_metadata_df.empty:
                enriched_metadata_df["Source System"] = enriched_metadata_df.apply(
                    lambda row: classify_source(row.to_dict()), axis=1
                )
                enriched_metadata_df = enriched_metadata_df.rename(columns={
                    "dataset_name": "Dataset",
                    "table_name": "Table",
                    "column_name": "Column",
                    "data_type": "Data Type",
                    "is_nullable": "Nullable",
                    "description": "Description"
                })
                for c in ["Dataset", "Table", "Column", "Data Type", "Nullable", "Description", "Source System"]:
                    if c not in enriched_metadata_df.columns:
                        enriched_metadata_df[c] = None
                enriched_metadata_df = enriched_metadata_df[
                    ["Dataset", "Table", "Column", "Data Type", "Nullable", "Description", "Source System"]
                ]
            else:
                enriched_metadata_df = pd.DataFrame(columns=[
                    "Dataset", "Table", "Column", "Data Type", "Nullable", "Description", "Source System"
                ])
                
            # Transformation mapping
            transformation_mapping_df = analyze_transformations(
                generated_sql, 
                all_metadata, 
                column_details=business_query_plan.get("column_details", {})
            )
            if progress_callback:
                progress_callback("Generating Transformation Mapping...", 93)

            # KPIs
            kpis = {
                "Raw Records in Report": len(raw_df),
                "Analytical Result Rows": len(report_df),
                "Tables Used": len(active_tables),
                "Datasets Used": len(selected_datasets),
            }

            # Generate workbook
            clean_name = re.sub(r'[^\w\-]', '_', business_query_plan["report_name"])
            clean_name = re.sub(r'_+', '_', clean_name).strip('_')
            filename = f"Outputs/{clean_name}.xlsx"

            os.makedirs("Outputs", exist_ok=True)

            def df_na_to_none(df: pd.DataFrame) -> pd.DataFrame:
                df = df.where(df.notna(), other=None)
                for col in df.columns:
                    if pd.api.types.is_datetime64_any_dtype(df[col]):
                        df[col] = df[col].dt.tz_localize(None) if df[col].dt.tz is None else df[col].dt.tz_convert(None)
                return df

            if progress_callback:
                progress_callback("Generating Dashboard...", 95)
            if progress_callback:
                progress_callback("Generating Excel report...", 97)

            actual_filename = ExcelService.generate_workbook(
                raw_data=df_na_to_none(raw_df),
                report_data=df_na_to_none(report_df),
                kpis=kpis,
                lineage_data=df_na_to_none(lineage_df) if not lineage_df.empty else lineage_df,
                metadata=df_na_to_none(enriched_metadata_df),
                pas_mapping=df_na_to_none(pas_mapping_df),
                crm_mapping=df_na_to_none(crm_mapping_df),
                transformation_mapping=df_na_to_none(transformation_mapping_df),
                output_filename=filename
            )
            
            print(f"\n[Agent] Unified Pipeline successfully generated: {actual_filename}")
            if progress_callback:
                progress_callback("Completed.", 100, {
                    "execution_status": "Completed",
                    "records_returned": len(report_df),
                    "report_name": business_query_plan.get("report_name", report_name or "Custom Report"),
                    "filename": actual_filename
                })
            return f"Generated workbook: {actual_filename}"

        except Exception as e:
            print(f"\n[Error] Unified Pipeline failed: {e}")
            import traceback
            traceback.print_exc()
            raise e

    def _map_concepts_to_columns(self, required_columns, all_metadata) -> dict:
        unique_physical_cols = list(all_metadata["column_name"].dropna().unique())
        
        prompt = f"""
You are a database schema mapper. Given a list of required report columns (business concepts) and a list of physical columns in a database schema:

Required Columns (Business Concepts):
{required_columns}

Physical Columns in Catalog:
{unique_physical_cols}

For each Required Column, identify which Physical Column name(s) match that concept. A business column may match one or more physical columns (e.g. "Policy Number" might match "policy_no", "policy_id").
Only match physical columns that actually exist in the list. Do not invent any columns.

Return ONLY a JSON object mapping: "Business Column Name": ["physical_column_name_1", "physical_column_name_2"]
"""
        try:
            response = self.model.generate_content(prompt)
            text = response.text.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as e:
            print(f"[Error] Schema mapping failed: {e}")
            mappings = {}
            for req_col in required_columns:
                matched = []
                req_clean = req_col.lower().replace(" ", "").replace("_", "")
                for col in unique_physical_cols:
                    col_clean = col.lower().replace(" ", "").replace("_", "")
                    if req_clean in col_clean or col_clean in req_clean:
                        matched.append(col)
                mappings[req_col] = matched if matched else [req_col.lower()]
            return mappings

    def _discover_joins(self, selected_tables, all_metadata) -> tuple[list, list]:
        """Automatically discover the join paths required to connect all selected tables."""
        print(f"[Join Discovery] Finding paths to connect selected tables: {selected_tables}")
        
        all_tables = list(all_metadata["table_name"].dropna().unique())
        relationship_df = self.relationship_service.infer_relationships(all_metadata, all_tables)
        
        graph = {}
        for _, row in relationship_df.iterrows():
            t1, t2 = row["left_table"], row["right_table"]
            c1, c2 = row["left_column"], row["right_column"]
            jt = row["join_type"]
            if t1 not in graph: graph[t1] = []
            if t2 not in graph: graph[t2] = []
            graph[t1].append((t2, c1, c2, jt))
            graph[t2].append((t1, c2, c1, jt))
            
        active_tables = set(selected_tables)
        joins = []
        
        if len(selected_tables) <= 1:
            return list(active_tables), joins
            
        root = selected_tables[0]
        for target in selected_tables[1:]:
            path = self._bfs_shortest_path(graph, root, target)
            if path:
                for i in range(len(path) - 1):
                    u, v = path[i], path[i+1]
                    active_tables.add(u)
                    active_tables.add(v)
                    for neighbor, c_u, c_v, jt in graph[u]:
                        if neighbor == v:
                            if not any(j["left_table"] == u and j["right_table"] == v for j in joins) and \
                               not any(j["left_table"] == v and j["right_table"] == u for j in joins):
                                joins.append({
                                    "left_table": u,
                                    "left_column": c_u,
                                    "right_table": v,
                                    "right_column": c_v,
                                    "join_type": jt
                                })
                            break
            else:
                print(f"[Join Discovery] Warning: No relationship path found between {root} and {target}")
                
        return list(active_tables), joins

    def _bfs_shortest_path(self, graph, start, target):
        if start == target:
            return [start]
        queue = [[start]]
        visited = {start}
        while queue:
            path = queue.pop(0)
            node = path[-1]
            if node in graph:
                for neighbor, _, _, _ in graph[node]:
                    if neighbor == target:
                        return path + [neighbor]
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(path + [neighbor])
        return None

    def _discover_filters(self, business_filters, active_tables, all_metadata) -> list:
        resolved_filters = []
        if not business_filters:
            return resolved_filters
            
        scoped_meta = all_metadata[all_metadata["table_name"].isin(active_tables)]
        schema_text = scoped_meta[["table_name", "column_name", "data_type", "description"]].drop_duplicates().to_string(index=False)
        
        for filt in business_filters:
            filter_text = json.dumps(filt)
            
            prompt = f"""
You are a database filter mapper.
Given the business filter specification: {filter_text}
And the schemas of active tables:
{schema_text}

Identify the best column to filter on and construct the correct SQL comparison condition representing this concept and its value.
If the filter specifies a date value, format it as a valid date literal string (e.g. '2025-06-01').
If the filter specifies a value, use it exactly.
Do NOT output placeholders like 'YYYY-MM-DD' or 'VALUE_HERE'. Use the actual values from the filter spec.

Return ONLY a JSON object matching this schema, with no markdown formatting:
{{
  "sql_condition": "table.column = 'value'"
}}
"""
            try:
                response = self.model.generate_content(prompt)
                text = response.text.strip()
                text = text.replace("```json", "").replace("```", "").strip()
                res = json.loads(text)
                cond = res.get("sql_condition")
                if cond:
                    resolved_filters.append(cond)
            except Exception as e:
                print(f"[Error] Filter discovery failed for {filter_text}: {e}")
                
        return resolved_filters

    def process_user_request(self, user_prompt: str, progress_callback = None):
        print(f"[Agent] Processing request: '{user_prompt}'")
        
        # Check if user_prompt is a path to an Excel template
        is_excel = False
        if os.path.exists(user_prompt) and user_prompt.lower().endswith(('.xlsx', '.xls', '.xlsm')):
            is_excel = True
            
        if is_excel:
            print("[Agent] Excel template input detected. Invoking template pipeline...")
            return self.execute_report_pipeline(user_prompt, is_excel=True, progress_callback=progress_callback)
        else:
            print("[Agent] Natural language input detected. Invoking chat/NL pipeline...")
            chat = self.model.start_chat()
            response = chat.send_message(user_prompt)
            
            if response.candidates and response.candidates[0].function_calls:
                tool_call = response.candidates[0].function_calls[0]
                if tool_call.name == "execute_report_generation":
                    args = tool_call.args
                    return self.execute_report_pipeline(
                        user_prompt=user_prompt,
                        report_name=args.get("report_name", "Report"),
                        date_range=args.get("date_range", "All Time"),
                        optional_filters=args.get("optional_filters", None),
                        is_excel=False,
                        progress_callback=progress_callback
                    )
            else:
                print("[Agent] No tool called. Falling back to direct pipeline with user prompt.")
                return self.execute_report_pipeline(
                    user_prompt=user_prompt,
                    report_name=user_prompt,
                    date_range="All Time",
                    is_excel=False,
                    progress_callback=progress_callback
                )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _audit_joins(self, sql: str, relationship_df: pd.DataFrame) -> None:
        """Verify that every JOIN ON pair in *sql* is present in the approved relationship graph.

        Raises RuntimeError if the generated SQL references a join column pair
        that was not approved by RelationshipService.  This acts as a deterministic
        gate that prevents hallucinated or cross-product joins from reaching BigQuery.

        The check is intentionally forgiving of table aliases: it compares only
        the bare column name pairs, which is sufficient to catch the most common
        hallucination pattern (inventing a column that does not appear in the schema).
        """
        import re

        if relationship_df is None or relationship_df.empty:
            # No approved paths — warn but do not block (tables may be queried independently).
            print(
                "[Audit] No relationship graph available — skipping join audit."
            )
            return

        # Extract all  col1 = col2  pairs from ON clauses.
        # Handles:  ON t1.col = t2.col  and  ON col = col  forms.
        on_pattern = re.compile(
            r"\bON\b.+?(?=\bJOIN\b|\bWHERE\b|\bGROUP\b|\bORDER\b|\bLIMIT\b|\bHAVING\b|$)",
            re.IGNORECASE | re.DOTALL,
        )
        col_pair_pattern = re.compile(
            r"(?:[\w`]+\.)?([\w`]+)\s*=\s*(?:[\w`]+\.)?([\w`]+)",
            re.IGNORECASE,
        )

        # Build a set of approved (col, col) pairs (order-independent).
        approved: set[frozenset] = set()
        for _, row in relationship_df.iterrows():
            approved.add(
                frozenset([str(row["left_column"]).lower(), str(row["right_column"]).lower()])
            )

        violations: list[str] = []
        for on_match in on_pattern.finditer(sql):
            on_clause = on_match.group(0)
            for left_col, right_col in col_pair_pattern.findall(on_clause):
                pair = frozenset([left_col.strip("`").lower(), right_col.strip("`").lower()])
                if pair not in approved:
                    violations.append(f"{left_col} = {right_col}")

        if violations:
            raise RuntimeError(
                f"[Audit] Generated SQL contains unapproved join(s): "
                f"{', '.join(violations)}. "
                "Execution blocked to prevent hallucinated or unsafe joins."
            )

        print(
            f"[Audit] All {len(list(on_pattern.finditer(sql)))} join(s) passed the relationship graph check."
        )

    def _repair_sql(
        self,
        broken_sql: str,
        error_message: str,
        metadata_df: pd.DataFrame,
        relationship_df: pd.DataFrame,
    ) -> str:
        """Ask Gemini to fix a SQL statement given the BigQuery validation error.

        The repaired SQL is returned as a plain string with no markdown fences.
        Only the specific syntax or reference error is targeted — the overall
        query structure and join paths must be preserved.
        """
        schema_text = metadata_df[["dataset_name", "table_name", "column_name", "data_type"]].drop_duplicates().to_string(index=False)
        relationship_text = self.sql_generator._format_relationship_allowlist(relationship_df)

        prompt = f"""You are a senior BigQuery SQL engineer.

The following BigQuery Standard SQL query failed dry-run validation with this error:

  {error_message}

Broken SQL:
```sql
{broken_sql}
```

Available Schema (use ONLY these datasets, tables, and columns):
{schema_text}

Approved Join Paths:
{relationship_text}

Instructions:
1. Fix the syntax or reference error indicated above.
2. If the error mentions 'Invalid field name' due to spaces, parentheses, slashes, dots, or other invalid characters, you MUST locate and sanitize ALL SELECT column aliases in the entire query to use only valid characters (alphanumeric and underscores, e.g. change `Renewal Premium (Gross)` to `Renewal_Premium_Gross` or `renewal_premium_gross`). Fix this for all columns in the SELECT clause in one go.
3. Ensure all tables are fully qualified using the project ID 'anz-cloud-migration' and its correct dataset name in backticks.
   Format: `anz-cloud-migration.dataset_name.table_name`
   Never reference a table as just `table` or `dataset.table` without the project prefix.
4. Do NOT change the overall query logic, selected columns, or join structure.
5. Replace any non-BigQuery syntax (e.g. Oracle KEEP/DENSE_RANK clauses) with valid BigQuery Standard SQL equivalents.
6. Return ONLY the fixed SQL with no markdown fences, no explanation.
"""
        response = self.sql_generator.model.generate_content(prompt)
        sql = response.text.strip()
        # Strip any markdown fences the model may have added
        sql = sql.replace("```sql", "").replace("```", "").strip()
        return sql

    def _extract_explicit_tables(
        self, prompt: str, all_metadata: pd.DataFrame
    ) -> list[str]:
        """Extract table names that the user explicitly named in their prompt.

        Supports two patterns:
          1. "using: table_a, table_b, table_c"  (comma-separated after "using:")
          2. Any word in the prompt that exactly matches a known table name.

        Returns a list of validated table names (must exist in all_metadata).
        Returns an empty list if no explicit tables are found, signalling the
        caller should fall back to Gemini-based asset selection.
        """
        import re

        known_tables: set[str] = set(all_metadata["table_name"].dropna().unique())
        found: list[str] = []

        # Pattern 1 — "using: table_a, table_b"
        using_match = re.search(r"\busing\s*:\s*(.+)", prompt, re.IGNORECASE)
        if using_match:
            candidates = [t.strip() for t in using_match.group(1).split(",")]
            for candidate in candidates:
                # Strip trailing punctuation and whitespace
                candidate = re.sub(r"[^\w]", "", candidate)
                if candidate in known_tables:
                    found.append(candidate)
                else:
                    print(
                        f"[Step 2] Warning: '{candidate}' not found in project metadata — skipping."
                    )
            if found:
                return found

        # Pattern 2 — any word in the prompt that exactly matches a table name
        words = set(re.findall(r"\b\w+\b", prompt))
        matched = sorted(words & known_tables)
        return matched

    def _get_dataset_locations(self, datasets) -> dict:
        locations = {}
        for ds in datasets:
            try:
                ds_ref = self.bq_service.client.dataset(ds)
                ds_obj = self.bq_service.client.get_dataset(ds_ref)
                locations[ds] = ds_obj.location.upper() if ds_obj.location else "US"
            except Exception:
                locations[ds] = "US"
        return locations
