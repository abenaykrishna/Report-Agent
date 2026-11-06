# Report-Agent 
# AI-Powered Insurance Report Generation Agent

## Project Overview

The **Insurance Report Generation Agent** is an AI-assisted reporting application that automates the process of creating insurance business reports from natural-language requests or existing Excel report templates.

In a typical reporting workflow, an analyst needs to understand the business requirement, identify the right tables and columns, determine how the data is related, write and execute SQL, gather supporting metadata, and format the results for business users. This project brings these steps together in one workflow.

A user can describe the report they need — for example, a policy lapse report or a premium collection summary — or upload an Excel template that defines the expected report structure. The agent interprets the request, discovers relevant data assets, prepares and executes a BigQuery query, and produces a structured Excel workbook.

The goal is to reduce repetitive report-building effort and make data easier to access for insurance reporting use cases.

## What the Application Does

1. **Accepts a reporting requirement**  
   Users provide a natural-language prompt or upload an Excel report template.

2. **Understands the requested report**  
   Gemini interprets the business requirement and identifies the fields, filters, calculations, and output structure needed.

3. **Discovers relevant data**  
   The application inspects available BigQuery datasets, tables, and column metadata to identify potential data sources.

4. **Maps business fields to source data**  
   It uses metadata and AI-assisted reasoning to associate requested report fields with physical tables and columns.

5. **Identifies data relationships and prepares SQL**  
   The application determines how relevant sources can be combined, generates the query, and executes it against BigQuery.

6. **Enriches the report with metadata and lineage**  
   It retrieves available metadata and data lineage information to provide context about the data used.

7. **Creates an Excel report**  
   The results are exported into a formatted, multi-sheet workbook that can be reviewed and shared.

## Example Use Cases

The project is designed around insurance reporting scenarios, including:

- **Policy Lapse Report:** Identify lapsed policies and review relevant policy and customer details.
- **Premium Collection Report:** Summarize premium collection information, including totals and reporting breakdowns.
- **Renewal and Suppression Reports:** Review policies associated with renewal activity and suppression conditions.
- **Executive Insurance Reports:** Combine information from relevant insurance data sources into a consolidated report.
- **Template-Based Reports:** Generate a report using the columns and structure provided in an uploaded Excel template.

Example request:

> Generate a policy lapse report with policy number, customer name, policy status, premium amount, and lapse date.

The agent uses the request to plan the report and retrieve the corresponding data, subject to the metadata and datasets available in the configured environment.

## High-Level Architecture

```text
                 User
                  |
                  v
          React Web Application
                  |
                  v
             FastAPI API
                  |
                  v
       Insurance Report Agent
                  |
          +-------+--------+
          |                |
          v                v
   Gemini / Vertex AI   Excel Template
   Request Analysis       Parsing
          |                |
          +-------+--------+
                  |
                  v
       Metadata & Data Discovery
                  |
          +-------+--------+
          |                |
          v                v
     BigQuery Metadata   Dataplex
                         Catalog
                  |
                  v
       Source Mapping & Relationship
               Discovery
                  |
                  v
          SQL Generation
                  |
                  v
          BigQuery Execution
                  |
                  v
       Metadata & Lineage Enrichment
                  |
                  v
          Excel Report Creation
                  |
                  v
          Preview / Download
```

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React, Vite, Material UI |
| Backend API | Python, FastAPI, Uvicorn |
| AI reasoning | Google Vertex AI, Gemini |
| Data warehouse | Google BigQuery |
| Metadata discovery | BigQuery metadata, Dataplex Data Catalog |
| Data lineage | Dataplex Data Lineage, BigQuery job-history fallback |
| Excel processing | OpenPyXL, Pandas |
| Semantic analytics integration | Looker SDK |

## Key Implementation Components

| File | Responsibility |
|---|---|
| `main.py` | FastAPI application, API endpoints, task handling, and CLI entry point |
| `report_agent.py` | Coordinates the report-generation workflow and AI-assisted reasoning |
| `discovery_service.py` | Discovers configured datasets, tables, and schemas |
| `metadata_service.py` | Retrieves table and column metadata |
| `relationship_service.py` | Identifies relationships between candidate data sources |
| `source_classifier.py` | Supports source identification and business-field mapping |
| `transformation_analyzer.py` | Analyzes requested field transformations |
| `sql_generator.py` | Builds SQL for the selected report requirements |
| `bigquery_service.py` | Validates and executes BigQuery queries |
| `lineage_service.py` | Retrieves lineage information and supports fallback lookup |
| `template_parser.py` | Extracts report requirements from Excel templates |
| `excel_service.py` | Creates and formats the generated Excel workbook |
| `looker_service.py` | Provides Looker SDK integration for supported analytics workflows |
| `frontend/src/` | React user interface |

## Generated Output

The main deliverable is an Excel workbook containing the requested report data. Depending on the report and the information available, the workbook can include:

- **Main_Report** — report records and requested columns.
- **Dashboard** — summary metrics or KPI information.
- **PAS_Mapping / CRM_Mapping** — source-field mapping information, where applicable.
- **Metadata** — information about the data assets used.
- **Lineage details** — available source and transformation context.

The exact workbook structure depends on the report request and the metadata available for the selected sources. Sample generated workbooks are included in the `Outputs/` directory.

## Running the Project

### Prerequisites

- Python 3.10 or later (use a version compatible with the pinned dependencies).
- Node.js and npm.
- Access to a Google Cloud project with the required BigQuery datasets.
- Vertex AI enabled, with permission to use the configured Gemini model.
- Appropriate BigQuery and Dataplex permissions.
- Google Cloud Application Default Credentials (ADC).

### 1. Configure Google Cloud authentication

For local development, authenticate with ADC:

```bash
gcloud auth application-default login
gcloud config set project YOUR_GCP_PROJECT_ID
```

The current implementation contains project and dataset configuration in the source code. Review the configuration in the relevant service files before running it against another environment.

### 2. Install backend dependencies

From the project root:

```bash
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install packages:

```bash
pip install -r requirements.txt
```

### 3. Install frontend dependencies

```bash
cd frontend
npm install
```

### 4. Start the backend

From the project root, run:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The API and interactive documentation are available at:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

### 5. Start the frontend

In a separate terminal:

```bash
cd frontend
npm run dev
```

Open the local URL printed by Vite, typically `http://localhost:5173`.

## API Overview

The FastAPI application exposes endpoints for uploading templates, starting report-generation tasks, checking task status, previewing results, and downloading workbooks.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/upload-template` | Upload an Excel report template |
| `POST` | `/api/generate-report` | Start report generation |
| `GET` | `/api/tasks/{task_id}` | Check task status and progress |
| `GET` | `/api/tasks/{task_id}/preview` | Preview generated report rows |
| `GET` | `/api/tasks/{task_id}/download` | Download the generated workbook |

Refer to `http://localhost:8000/docs` for the request and response schemas exposed by the running application.



---

**In short:** This project demonstrates how an AI agent can translate an insurance reporting requirement into a data-backed, metadata-enriched Excel report by coordinating LLM reasoning, data discovery, SQL execution, and report generation.
