import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import os
import uuid
import threading
import time
import traceback
import pandas as pd

from report_agent import InsuranceReportAgent

# Setup upload folder programmatically
os.makedirs("uploads", exist_ok=True)

agent = InsuranceReportAgent(project_id="anz-cloud-migration")
app = FastAPI(title="Insurance Report Agent API")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for tasks
tasks = {}
tasks_lock = threading.Lock()

class ReportRequest(BaseModel):
    prompt: Optional[str] = None
    template_path: Optional[str] = None

def run_pipeline_thread(task_id: str, input_str: str, start_time: float):
    def progress_callback(stage: str, percent: int, metadata_updates: dict = None):
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]["progress_stage"] = stage
                tasks[task_id]["progress_percent"] = percent
                if metadata_updates:
                    tasks[task_id]["result"].update(metadata_updates)
                    
    try:
        # Run agent pipeline
        agent.process_user_request(input_str, progress_callback=progress_callback)
        
        duration = round(time.time() - start_time, 1)
        gen_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["progress_stage"] = "Completed."
                tasks[task_id]["progress_percent"] = 100
                tasks[task_id]["result"]["execution_status"] = "Completed"
                tasks[task_id]["result"]["generation_time"] = gen_time
                tasks[task_id]["result"]["execution_duration"] = f"{duration} seconds"
                
    except Exception as e:
        traceback.print_exc()
        duration = round(time.time() - start_time, 1)
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["progress_stage"] = "Failed."
                tasks[task_id]["error"] = str(e)
                tasks[task_id]["result"]["execution_status"] = "Failed"
                tasks[task_id]["result"]["execution_duration"] = f"{duration} seconds"

@app.post("/api/upload-template")
async def upload_template(file: UploadFile = File(...)):
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".xlsx", ".xls"]:
        raise HTTPException(status_code=400, detail="Unsupported file format. Only .xlsx and .xls are supported.")
        
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join("uploads", unique_filename)
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
        
    return {
        "template_path": file_path.replace("\\", "/"),
        "filename": filename
    }

@app.post("/api/generate-report")
async def generate_report_endpoint(request: ReportRequest):
    if not request.prompt and not request.template_path:
        raise HTTPException(status_code=400, detail="Either a natural language query or an Excel template path must be provided.")
        
    task_id = str(uuid.uuid4())
    
    # Decide which input to pass. Prioritize template path if provided.
    input_str = request.template_path if request.template_path else request.prompt
    
    # Check that template path exists if we are using it
    if request.template_path and not os.path.exists(request.template_path):
        raise HTTPException(status_code=400, detail="Provided template file not found on the server.")

    with tasks_lock:
        tasks[task_id] = {
            "task_id": task_id,
            "status": "processing",
            "progress_stage": "Reading input...",
            "progress_percent": 5,
            "error": None,
            "result": {
                "report_name": "In Progress...",
                "execution_status": "Processing",
                "generation_time": None,
                "execution_duration": None,
                "records_returned": 0,
                "datasets_used": [],
                "tables_used": [],
                "metadata_search_status": "Pending",
                "lineage_search_status": "Pending",
                "sql_execution_status": "Pending",
                "filename": None
            }
        }
        
    # Start task in background thread
    t = threading.Thread(
        target=run_pipeline_thread,
        args=(task_id, input_str, time.time()),
        daemon=True
    )
    t.start()
    
    return {"task_id": task_id}

@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.get("/api/tasks/{task_id}/preview")
async def get_task_preview(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task is not completed yet")
        
    filepath = task["result"].get("filename")
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Generated report file not found")
        
    try:
        # Load Main_Report sheet
        df = pd.read_excel(filepath, sheet_name="Main_Report")
        columns = list(df.columns)
        
        # Convert to records
        raw_data = df.head(100).to_dict(orient="records")
        
        # Sanitize records to replace NaN/Inf/NaT with None for JSON compliance
        import math
        def sanitize_val(v):
            if v is None:
                return None
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    return None
            if pd.isna(v):
                return None
            if hasattr(v, 'isoformat'):
                return v.isoformat()
            if type(v).__name__ in ['NaTType', 'NAType']:
                return None
            return v
            
        sanitized_data = []
        for row in raw_data:
            sanitized_row = {k: sanitize_val(v) for k, v in row.items()}
            sanitized_data.append(sanitized_row)
            
        return {
            "columns": columns,
            "data": sanitized_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse report preview sheet: {str(e)}")

@app.get("/api/tasks/{task_id}/download")
async def download_task_report(task_id: str):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="Task is not completed yet")
        
    filepath = task["result"].get("filename")
    if not filepath or not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Generated report file not found")
        
    return FileResponse(
        path=filepath,
        filename=os.path.basename(filepath),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Fallback endpoint for generating report from CLI or old endpoint compatibility
class OldReportRequest(BaseModel):
    prompt: str

@app.post("/generate-report")
async def old_generate_report_endpoint(request: OldReportRequest):
    try:
        agent.process_user_request(request.prompt)
        return {"status": "success", "message": "Report generated locally."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve built frontend static files if they exist
if os.path.exists("frontend/dist"):
    app.mount("/", StaticFiles(directory="frontend/dist", html=True), name="frontend")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "--serve":
            uvicorn.run("main:app", host="0.0.0.0", port=8000)
        else:
            agent.process_user_request(sys.argv[1])
    else:
        user_prompt = input("Enter report query or template filepath: ").strip()
        if user_prompt:
            agent.process_user_request(user_prompt)
        else:
            print("Error: No input provided. Exiting.")