import openpyxl

def main():
    f_path = "Outputs/List_of_All_Policies_with_Suppression_of_Renewal_Notice.xlsx"
    print(f"Inspecting file: {f_path}")
    try:
        wb = openpyxl.load_workbook(f_path, data_only=True)
        print(f"Sheet names: {wb.sheetnames}")
        
        if "Transformation_Mapping" in wb.sheetnames:
            ws = wb["Transformation_Mapping"]
            headers = [cell.value for cell in ws[3]]
            print(f"Transformation Mapping Headers: {headers}")
            print("First 5 rows of Transformation Mapping:")
            for r_idx in range(4, 9):
                row_vals = [ws.cell(row=r_idx, column=c_idx).value for c_idx in range(1, len(headers) + 1)]
                if any(row_vals):
                    print(f"  Row {r_idx}: {row_vals}")
                    
        if "Main_Report" in wb.sheetnames:
            ws_main = wb["Main_Report"]
            main_headers = [cell.value for cell in ws_main[1]]
            print(f"\nMain Report Headers: {main_headers}")
            print(f"Main Report Rows count: {ws_main.max_row - 1}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
