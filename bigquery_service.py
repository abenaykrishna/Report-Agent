import pandas as pd
from google.cloud import bigquery

class BigQueryService:
    def __init__(self, project_id: str = "anz-cloud-migration"):
        self.project_id = project_id
        self.client = bigquery.Client(project=self.project_id)

    def execute_query(self, query: str, location: str = "us") -> pd.DataFrame:
        """Executes a live query against BigQuery and returns a Pandas DataFrame."""
        print(f"[BigQuery Service] Executing Live Query in location '{location}':\n{query}")
        try:
            query_job = self.client.query(query, location=location)
            df = query_job.to_dataframe()
            return df
        except Exception as e:
            print(f"[Error] BigQuery execution failed: {str(e)}")
            return pd.DataFrame() # Return empty DataFrame on failure to prevent crashes
    
    def validate_query(self, query: str, location: str = "us") -> bool:
        is_valid, _ = self.validate_query_with_error(query, location=location)
        return is_valid

    def validate_query_with_error(self, query: str, location: str = "us") -> tuple[bool, str]:
        """Dry-run the query and return (is_valid, error_message).

        Returns (True, "") on success.
        Returns (False, "<error string>") on failure so callers can use the
        error message in a repair prompt.
        """
        try:
            job_config = bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False
            )
            self.client.query(
                query,
                job_config=job_config,
                location=location
            )
            return True, ""

        except Exception as e:
            error_msg = str(e)
            print(f"SQL Validation Failed: {error_msg}")
            return False, error_msg