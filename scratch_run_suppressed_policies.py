import sys
from report_agent import InsuranceReportAgent

def main():
    agent = InsuranceReportAgent(project_id="anz-cloud-migration")
    template_path = "Suppressed_Policies_Report_Template.xlsx"
    print(f"Starting pipeline execution for template: {template_path}")
    try:
        agent.execute_report_pipeline(template_path, is_excel=True)
        print("\nPipeline execution COMPLETED successfully!")
    except Exception as e:
        print(f"\nPipeline execution FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
