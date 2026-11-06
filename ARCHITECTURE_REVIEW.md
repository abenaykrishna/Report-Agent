# Enterprise AI Reporting Agent Architecture Review

## Executive assessment

The current system is a promising prototype, but it is not yet an enterprise metadata-driven reporting platform. It demonstrates a linear path from a natural language prompt to discovery, asset selection, SQL generation, BigQuery execution, lineage retrieval, and Excel export. However, it still relies on model inference for critical decisions, performs broad unbounded discovery at request time, lacks a relationship catalog, does not use lineage before SQL generation, has limited validation and governance controls, and has hardcoded project/model defaults.

Production-readiness score: **3 / 10**.

The largest risks are incorrect joins, excessive BigQuery scans, missing security boundaries, non-deterministic agent behavior, and inability to scale discovery across hundreds of datasets and thousands of tables.

## 1. Current maturity assessment

| Capability | Current maturity | Target maturity | Required change |
| --- | --- | --- | --- |
| Natural language intake | Prototype | Deterministic intent router | Treat report generation as the default action and make clarifying questions optional only when required fields are impossible to infer. |
| Discovery | Prototype | Cached enterprise catalog | Move from request-time full scans to scheduled catalog indexing with search/ranking. |
| Metadata | Basic technical schema | Business + technical metadata | Include descriptions, tags, policy tags, owners, freshness, row counts, and sample-safe profiles. |
| Relationship inference | Weak | Evidence-ranked relationship graph | Build a relationship catalog from PK/FK signals, naming, Dataplex lineage, query history, and curated overrides. |
| SQL generation | Unsafe LLM-only | Plan-generate-validate-repair | Generate a structured query plan first, then SQL, then validate and repair using dry runs and AST checks. |
| Lineage | Post-execution reporting only | Pre-SQL planning input | Use lineage and query history before SQL generation to rank table paths and joins. |
| Excel generation | Basic workbook | Business report product | Add business sections, sheet-specific formatting, data dictionaries, mapping sheets, and audit details. |
| Security | Minimal | Least privilege + governance | Add IAM scoping, row/column security awareness, output controls, audit logs, and prompt-injection defenses. |
| Operations | Minimal | SLO-driven service | Add tracing, retries, quotas, budgets, async jobs, persisted artifacts, and monitoring. |

## 2. Architectural weaknesses and fixes

### Weakness: tool invocation is optional and brittle

The agent currently relies on Gemini deciding to call `execute_report_generation`. Because the tool schema requires a `date_range`, the model may ask for a date range even when the user requested an all-time report.

**Change:** make `date_range` optional, strengthen the tool description, and add a deterministic fallback path that invokes report generation directly when no tool call is returned.

**Why:** report generation is the primary product action. The orchestration layer should not fail because the model chose a conversational response.

### Weakness: one-shot LLM asset selection

The system sends all discovered metadata to the model and asks for selected datasets/tables. This does not scale and can exceed context limits.

**Change:** add a multi-stage retrieval pipeline:

1. Tokenize and classify the user request.
2. Search a cached metadata index.
3. Rank candidate tables using business descriptions, column names, tags, lineage, and usage history.
4. Ask the model to choose only from top-ranked candidates.

**Why:** enterprise environments need search and ranking before generative reasoning.

### Weakness: no relationship graph

Join inference currently depends on column-name similarity only.

**Change:** create a relationship discovery layer that emits edges like:

```json
{
  "left_table": "policy_master",
  "left_column": "policy_no",
  "right_table": "renewal_master",
  "right_column": "policy_no",
  "confidence": 0.95,
  "evidence": ["same_name", "lineage", "query_history"]
}
```

**Why:** joins are the highest-risk part of text-to-SQL. They need explicit evidence and auditable confidence.

### Weakness: lineage arrives too late

Lineage is retrieved after query execution, so it cannot improve table or join selection.

**Change:** retrieve lineage during planning, before SQL generation, and include upstream/downstream tables as relationship evidence.

**Why:** lineage helps identify reporting marts, source systems, and valid transformation paths.

## 3. Scalability concerns and proposed solutions

| Concern | Risk | Solution |
| --- | --- | --- |
| Full dataset scans per request | Slow, expensive, API quota pressure | Maintain a scheduled metadata index in BigQuery or AlloyDB. |
| Passing all schemas to Gemini | Context overflow and higher latency | Use vector/text search to provide only top candidates. |
| Thousands of table combinations | Bad joins and exponential planning | Build and query a relationship graph. |
| Synchronous API execution | Request timeouts | Convert report generation to an async job with status polling. |
| Large Excel downloads | Memory pressure | Stream results, cap rows, export large details to GCS, and include summaries in Excel. |
| Unbounded BigQuery scans | Cost blowouts | Enforce maximum bytes billed and dry-run cost gates. |

## 4. Reliability concerns and mitigation strategies

* **Do not swallow BigQuery execution failures.** Return structured errors instead of empty DataFrames.
* **Add retry with exponential backoff** for transient Vertex AI, BigQuery, Dataplex, and Looker calls.
* **Persist job state** with request, selected assets, generated SQL, dry-run stats, execution status, workbook URI, and errors.
* **Add SQL repair loops** that use dry-run errors as feedback, capped at a small retry count.
* **Add deterministic fallbacks** for tool calling and JSON parsing failures.
* **Add contract tests** for representative prompts, expected tables, and expected join keys.

## 5. Security concerns and recommended controls

| Area | Current risk | Recommended control |
| --- | --- | --- |
| IAM | Broad project-level access likely | Use least-privilege service accounts and dataset-level permissions. |
| PII | Customer email/phone can be exported freely | Enforce policy tags, masking, approval workflows, and output classification. |
| SQL injection | User prompt can influence generated SQL | Restrict SQL to `SELECT`, parse SQL AST, block DDL/DML/export statements. |
| Prompt injection | Metadata descriptions could contain malicious instructions | Treat metadata as data, not instructions, and delimit it in prompts. |
| Output storage | Local Excel files may leak data | Store encrypted artifacts in GCS with signed URLs and retention policies. |
| Audit | No durable audit trail | Log user, prompt hash, selected assets, SQL hash, bytes billed, and artifact URI. |

## 6. GCP best-practice gaps

* Use Application Default Credentials and environment configuration rather than hardcoded project IDs.
* Use Cloud Run or Cloud Functions for the API layer and Cloud Tasks / Pub/Sub for async report jobs.
* Use BigQuery `maximum_bytes_billed`, labels, dry runs, and reservation-aware controls.
* Use Dataplex/Data Catalog policy tags for sensitive columns.
* Use Cloud Logging, Cloud Trace, Error Reporting, and structured logs.
* Persist generated reports to GCS rather than the local container filesystem.
* Store secrets in Secret Manager, not local Looker config files.

## 7. Agent design improvements

Recommended orchestration pattern:

1. **Intent parser**: classify report request, missing constraints, output type, and safety requirements.
2. **Candidate retriever**: retrieve top datasets/tables/columns from an indexed catalog.
3. **Relationship planner**: build candidate join graph and choose join path.
4. **Query planner**: produce structured JSON plan before SQL.
5. **SQL compiler**: generate SQL from the plan.
6. **Validator**: dry run, enforce allowlist, estimate cost, and repair if needed.
7. **Executor**: execute with labels, timeout, and bytes limits.
8. **Report builder**: generate workbook and include audit metadata.

The model should not be the only control point. Every model output should be validated by deterministic code.

## 8. Metadata discovery improvements

Add these fields to discovery:

* `project_id`, `dataset_name`, `table_name`, `column_name`, `ordinal_position`, `data_type`, `is_nullable`.
* Column descriptions from `INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`.
* Table type, creation time, last modified time, row count, and size.
* Policy tags and sensitive-data classifications.
* Dataplex/Data Catalog descriptions, tags, glossary terms, owners, and quality scores.
* Usage statistics from `INFORMATION_SCHEMA.JOBS_BY_PROJECT`.
* Sample profiles where safe: null ratio, distinct count estimate, min/max for dates.

## 9. SQL generation improvements

The SQL generator should receive structured inputs, not a raw DataFrame string only:

* user request
* candidate tables
* columns with business descriptions
* relationship graph edges
* lineage hints
* required output columns
* known filters
* forbidden operations
* BigQuery dialect rules

Validation strategy:

1. Parse generated SQL and require exactly one `SELECT` statement.
2. Block DDL, DML, temporary functions, external connections, and wildcard table scans unless explicitly allowed.
3. Dry run with `maximum_bytes_billed`.
4. Check that referenced tables and columns are from the approved candidate set.
5. Confirm all requested business fields are represented or explicitly marked unavailable.
6. Run repair prompt only with deterministic validation errors.

## 10. Lineage integration recommendations

Lineage should feed planning as follows:

* Before asset selection, discover lineage neighborhoods for candidate tables.
* Prefer curated reporting tables when lineage shows they already combine requested source domains.
* Use upstream lineage to explain which PAS, CRM, and renewal sources contribute to the output.
* Use lineage links as relationship evidence, not as a replacement for schema relationships.
* Include lineage confidence and edge direction in the SQL prompt.

## 11. Eliminating hardcoded assumptions

Actionable steps:

1. Move `project_id`, location, model name, output path, and BigQuery limits into configuration.
2. Remove insurance-specific names from prompts and replace them with domain-neutral report-generation instructions.
3. Replace hardcoded dataset examples with dynamic examples from discovered metadata.
4. Create a semantic glossary table instead of encoding business concepts in code.
5. Store relationship overrides in BigQuery or Dataplex tags, not Python constants.
6. Derive Excel sheet mappings from report metadata and source-system tags.

## 12. File-by-file refactoring plan

| File | Recommended changes |
| --- | --- |
| `main.py` | Add async job API, request IDs, environment-driven config, health endpoint, and structured error responses. |
| `report_agent.py` | Separate orchestration from Gemini chat, make tool fields optional, add fallback execution, retrieve relationships and lineage before SQL generation. |
| `discovery_service.py` | Return richer metadata, add region/location handling, caching, policy tags, descriptions, table stats, and search/ranking methods. |
| `metadata_service.py` | Normalize Dataplex and BigQuery metadata into one schema and include business descriptions in prompts. |
| `lineage_service.py` | Add relationship-oriented lineage APIs for pre-SQL planning and merge Dataplex plus BigQuery job history evidence. |
| `sql_generator.py` | Generate query plans, include relationship/lineage context, require JSON for planning, sanitize markdown, and support repair loops. |
| `bigquery_service.py` | Add max bytes billed, job labels, timeout, destination tables, structured failures, and AST/allowlist validation. |
| `excel_service.py` | Fix API consistency, add PAS/CRM mapping sheets, freeze panes, filters, formats, audit sheet, and output to GCS. |
| `looker_service.py` | Treat Looker as optional semantic enrichment; do not hardcode fields. |
| `README.md` | Document architecture, configuration, security controls, local run, tests, and limitations. |

## 13. Recommended implementation order

1. **Fix deterministic invocation and function schema.** This immediately addresses the observed failure mode.
2. **Fix workbook API mismatch and execution error handling.** These are correctness issues.
3. **Add richer metadata descriptions to discovery.** SQL quality improves quickly.
4. **Add relationship discovery.** Reduces join hallucination.
5. **Integrate lineage before SQL generation.** Improves table/path selection.
6. **Add SQL validation and repair loop.** Reduces unsafe or invalid SQL.
7. **Move to async jobs and persisted artifacts.** Required for production reliability.
8. **Add governance/security controls.** Required before enterprise use with PII.
9. **Add observability and cost controls.** Required for scale.
10. **Introduce catalog cache/search.** Required for hundreds of datasets.

## 14. Production-readiness score

**3 / 10**

The system is valuable as a proof of concept but not production-ready. It lacks deterministic orchestration, relationship evidence, pre-generation lineage use, robust SQL safety, cost controls, strong security, scalable catalog indexing, durable job state, and enterprise observability.

## 15. Specific code-level changes to make next

The next changes should be:

1. Make only `report_name` required in the tool schema and default `date_range` to `All Time`.
2. Add a fallback in `process_user_request` that calls `execute_report_generation(user_prompt, "All Time")` when the model does not call the tool.
3. Fix the workbook method call to match `ExcelService.generate_workbook` parameters.
4. Add metadata descriptions, ordinal position, nullable flag, and table catalog data in discovery.
5. Add `RelationshipService` to infer join edges from exact column matches, high-value key suffixes, lineage evidence, and curated overrides.
6. Pass relationship and lineage context into SQL generation.
7. Add BigQuery dry-run bytes estimation and `maximum_bytes_billed` before execution.
8. Replace empty-DataFrame-on-error behavior with explicit exceptions.
