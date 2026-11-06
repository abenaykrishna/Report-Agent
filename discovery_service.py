from google.cloud import bigquery
import pandas as pd


class DiscoveryService:

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = bigquery.Client(project=project_id)

    def discover_assets(self) -> pd.DataFrame:
        """
        Discover all datasets, tables and columns available
        in the project.
        """

        assets = []
        datasets = list(self.client.list_datasets())
        
        # Only scan the core datasets used for report generation
        core_datasets = {"gold_insurance_layer", "gold_layer", "claims_silver", "phi_silver_raw_us"}

        for dataset in datasets:
            dataset_id = dataset.dataset_id
            
            if dataset_id not in core_datasets:
                continue

            try:

                query = f"""
                SELECT
                    '{self.project_id}' AS project_id,
                    '{dataset_id}' AS dataset_name,
                    c.table_name,
                    t.table_type,
                    c.column_name,
                    c.ordinal_position,
                    c.data_type,
                    c.is_nullable,
                    fp.description
                FROM
                    `{self.project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMNS` c
                LEFT JOIN
                    `{self.project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS` fp
                ON
                    c.table_name = fp.table_name
                    AND c.column_name = fp.column_name
                LEFT JOIN
                    `{self.project_id}.{dataset_id}.INFORMATION_SCHEMA.TABLES` t
                ON
                    c.table_name = t.table_name
                """

                df = self.client.query(query).to_dataframe()

                if not df.empty:
                    assets.append(df)

            except Exception as e:
                print(
                    f"Skipping dataset {dataset_id}: {e}"
                )

        if assets:
            return pd.concat(
                assets,
                ignore_index=True
            )

        return pd.DataFrame()