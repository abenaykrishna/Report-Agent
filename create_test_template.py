import openpyxl
from openpyxl.comments import Comment

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Report Template"

ws["A1"] = "Report Name"
ws["B1"] = "Dropout Leads & Recovery Report"

ws["A3"] = "Description"
ws["B3"] = "List of dropped leads, their current recovery actions, responses, and key calculations"

ws["A5"] = "Columns"
columns = [
    ("Policy Number", "", "PAS"),
    ("Customer Name", "", "PAS"),
    ("Recovery Action", "", "CRM"),
    ("Renewal Present (Y/N)", "Business Rule:\nIf renewal_status is 'RENEWED' then 'Y' else 'N'", "PAS"),
    ("Conversion Rate", "Calculation: Recovered Policies / Total Dropped Policies * 100", "PAS-DMS")
]

for idx, (col_name, rule, source) in enumerate(columns, start=6):
    cell_a = ws[f"A{idx}"]
    cell_a.value = f"* {col_name}"
    
    if rule:
        # Put rule in adjacent cell B
        ws[f"B{idx}"] = rule
        # Also add a cell comment to verify both comment and cell scanners
        cell_a.comment = Comment(rule, "Business Analyst")
        
    if source:
        ws[f"C{idx}"] = f"Source System: {source}"

wb.save("test_dropout_leads_template.xlsx")
print("Template 'test_dropout_leads_template.xlsx' created successfully.")
