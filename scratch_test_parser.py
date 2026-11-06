from template_parser import TemplateParser
import traceback

def main():
    template_path = "Suppressed_Policies_Report_Template.xlsx"
    try:
        print(f"Parsing template: {template_path}")
        res = TemplateParser.parse_template(template_path)
        print("\n=== Parsed Results ===")
        print(f"Report Name: {res.get('report_name')}")
        print(f"Description: {res.get('business_description')}")
        print("\nColumns and details:")
        for idx, col in enumerate(res.get("columns_details", []), start=1):
            print(f" {idx}. Column: {col.get('name')}")
            if col.get('business_rule'):
                print(f"    Rule: {col.get('business_rule')}")
            if col.get('expected_source'):
                print(f"    Expected Source: {col.get('expected_source')}")
    except Exception as e:
        print("Failed to parse template!")
        traceback.print_exc()

if __name__ == "__main__":
    main()
