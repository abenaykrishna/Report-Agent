import os
import sys
from report_agent import InsuranceReportAgent

def main():
    agent = InsuranceReportAgent(project_id="anz-cloud-migration")
    
    print("\n" + "="*50)
    print("TEST 1: NATURAL LANGUAGE INPUT MODE")
    print("="*50)
    nl_prompt = "Generate Policy Lapse Report for June 2025"
    try:
        res = agent.execute_report_pipeline(
            user_prompt=nl_prompt,
            report_name=nl_prompt,
            date_range="June 2025",
            is_excel=False
        )
        print(f"NL Test Success: {res}")
    except Exception as e:
        print(f"NL Test Failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*50)
    print("TEST 2: EXCEL TEMPLATE INPUT MODE")
    print("="*50)
    template_path = "test_dropout_leads_template.xlsx"
    try:
        res = agent.execute_report_pipeline(
            user_prompt=template_path,
            is_excel=True
        )
        print(f"Excel Template Test Success: {res}")
    except Exception as e:
        print(f"Excel Template Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
