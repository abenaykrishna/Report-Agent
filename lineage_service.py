import pandas as pd
from google.cloud import bigquery
from google.cloud import datacatalog_lineage_v1

class DualLineageService:
    def __init__(self, project_id: str = "anz-cloud-migration", location: str = "us-central1"):
        self.project_id = project_id
        self.location = location
        self.bq_client = bigquery.Client(project=self.project_id)
        # Updated Client initialized here to match the new package
        self.lineage_client = datacatalog_lineage_v1.LineageClient()

    def get_lineage_via_bigquery(self, dataset_id: str, table_name: str, region: str = "us") -> pd.DataFrame:
        """Derives lineage by inspecting BigQuery's native Job execution logs (INFORMATION_SCHEMA.JOBS)."""
        print(f"[Lineage Service] Parsing BQ native lineage for {table_name}...")
        
        query = f"""
            SELECT 
                destination_table.table_id AS Target_Table,
                ref_table.dataset_id AS Source_Dataset,
                ref_table.table_id AS Source_Table
            FROM 
                `{self.project_id}.region-{region}.INFORMATION_SCHEMA.JOBS`,
                UNNEST(referenced_tables) AS ref_table
            WHERE 
                destination_table.project_id = '{self.project_id}'
                AND destination_table.dataset_id = '{dataset_id}'
                AND destination_table.table_id = '{table_name}'
                AND statement_type IN ('MERGE', 'INSERT', 'CREATE_TABLE_AS_SELECT')
            GROUP BY 1, 2, 3
        """
        df = self.bq_client.query(query).to_dataframe()
        return df

    def get_lineage_via_dataplex(self, dataset_id: str, table_name: str, max_links: int = 50) -> pd.DataFrame:
        """Retrieves official visual lineage mappings via the Dataplex Data Lineage API."""
        print(f"[Lineage Service] Fetching Dataplex Lineage API links for {table_name}...")
        
        # Fully qualified name format for BQ in Dataplex Lineage
        fqn = f"bigquery:{self.project_id}.{dataset_id}.{table_name}"
        
        # Updated object references here to use the new module
        target = datacatalog_lineage_v1.EntityReference(fully_qualified_name=fqn)
        parent = f"projects/{self.project_id}/locations/{self.location}"
        request = datacatalog_lineage_v1.SearchLinksRequest(parent=parent, target=target)
        
        lineage_records = []
        try:
            links = self.lineage_client.search_links(request=request)
            for link in links:
                lineage_records.append({
                    "Target Table": table_name,
                    "Source System": link.source.fully_qualified_name.split(":")[0],
                    "Source FQN": link.source.fully_qualified_name
                })
                # Cap results to avoid runaway pagination
                if len(lineage_records) >= max_links:
                    break
            return pd.DataFrame(lineage_records)
        except Exception as e:
            print(f"[Error] Dataplex Lineage lookup failed: {e}")
            return pd.DataFrame()