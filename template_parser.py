import os
import re
import json
from openpyxl import load_workbook
from vertexai.generative_models import GenerativeModel

class TemplateParser:
    @staticmethod
    def parse_template(file_path: str) -> dict:
        """Parses an Excel template to retrieve report details, business rules, and formulas.
        
        Returns:
            dict containing:
                - report_name: str
                - business_description: str
                - required_columns: list[str]
                - columns_details: list[dict]
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Template file not found at: {file_path}")
            
        print(f"[Template Parser] Loading template workbook from: {file_path}")
        # Load with data_only=False to retrieve cell formulas (e.g. '=A1+B1') instead of calculated values
        wb = load_workbook(file_path, data_only=False)
        ws = wb.active
        
        max_row = ws.max_row
        max_col = ws.max_column
        
        cell_descriptions = []
        # Trailing cells scanner for rich spreadsheet representations
        for r in range(1, max_row + 1):
            row_cells = []
            for c in range(1, max_col + 1):
                cell = ws.cell(row=r, column=c)
                val = cell.value
                val_str = str(val).strip() if val is not None else ""
                
                comment_str = ""
                if cell.comment:
                    # Capture comments or annotations associated with cells
                    comment_text = cell.comment.text.strip() if cell.comment.text else ""
                    if comment_text:
                        comment_str = f" [Comment: {comment_text}]"
                
                if val_str or comment_str:
                    col_letter = cell.column_letter
                    is_formula = " (Formula)" if val_str.startswith("=") else ""
                    row_cells.append(f"{col_letter}{r}: {repr(val_str)}{is_formula}{comment_str}")
            if row_cells:
                cell_descriptions.append(", ".join(row_cells))
                
        sheet_text = "\n".join(cell_descriptions)
        
        prompt = f"""
You are an expert business spreadsheet layout parser.
Given a text representation of all non-empty cells in an Excel business report template:

{sheet_text}

Identify and extract:
1. "report_name": the name/title of the report. If not explicitly specified, infer it or default to "".
2. "business_description": description of the report's business goal or context if available.
3. "columns": a JSON list of objects, one for each required column in the report. For each column, identify:
   - "name": the clean name/header of the column.
   - "business_rule": any business rules, casing logic (e.g. Y/N conversion), notes, formulas, calculation instructions, or descriptions associated with this column (found in adjacent cells, comments, or annotations). If there are no rules or calculations, set it to "".
   - "expected_source": the expected system or label (e.g. "PAS", "CRM", "PAS-DMS") if mentioned in adjacent cells or comments.

Return ONLY a JSON object with these keys:
- "report_name"
- "business_description"
- "columns"
"""
        model = GenerativeModel("gemini-2.5-flash")
        print("[Template Parser] Sending cell details to Gemini for layout understanding...")
        response = model.generate_content(prompt)
        text = response.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        
        parsed = json.loads(text)
        columns_list = parsed.get("columns", [])
        
        # Clean required columns list for downstream steps
        required_columns = []
        columns_details = []
        for col in columns_list:
            col_name = col.get("name", "").strip()
            if col_name:
                required_columns.append(col_name)
                columns_details.append({
                    "name": col_name,
                    "business_rule": col.get("business_rule", "").strip(),
                    "expected_source": col.get("expected_source", "").strip()
                })
                
        report_name = parsed.get("report_name", "").strip()
        if not report_name:
            base_name = os.path.basename(file_path)
            report_name = os.path.splitext(base_name)[0].replace("_", " ").title()
            
        print(f"[Template Parser] Parsed Report Name: '{report_name}', columns: {required_columns}")
        return {
            "report_name": report_name,
            "business_description": parsed.get("business_description", "").strip(),
            "required_columns": required_columns,
            "columns_details": columns_details
        }
