import pandas as pd
from google.cloud import bigquery
from google.cloud import datacatalog_v1

class DualMetadataService:
    def __init__(self, project_id: str = "anz-cloud-migration"):
        self.project_id = project_id
        self.bq_client = bigquery.Client(project=self.project_id)
        self.datacatalog_client = datacatalog_v1.DataCatalogClient()

    def get_metadata_via_bigquery(self, dataset_id: str, table_name: str) -> pd.DataFrame:
        """Retrieves metadata natively using BigQuery INFORMATION_SCHEMA."""
        print(f"[Metadata Service] Fetching BQ native metadata for {dataset_id}.{table_name}...")
        
        query = f"""
            SELECT 
                table_name AS `Table Name`,
                column_name AS `Column Name`,
                data_type AS `Data Type`,
                description AS `Business Description`
            FROM 
                `{self.project_id}.{dataset_id}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`
            WHERE 
                table_name = '{table_name}'
        """
        df = self.bq_client.query(query).to_dataframe()
        return df

    def get_metadata_via_dataplex(self, dataset_id: str, table_name: str) -> pd.DataFrame:
        """Retrieves unified metadata using Dataplex/Data Catalog."""
        print(f"[Metadata Service] Fetching Dataplex metadata for {dataset_id}.{table_name}...")
        
        # Dataplex uses Data Catalog underlying linked resources for BigQuery
        resource_name = f"//bigquery.googleapis.com/projects/{self.project_id}/datasets/{dataset_id}/tables/{table_name}"
        request = datacatalog_v1.LookupEntryRequest(linked_resource=resource_name)
        
        try:
            entry = self.datacatalog_client.lookup_entry(request=request)
            
            metadata_records = []
            for column in entry.schema.columns:
                metadata_records.append({
                    "Table Name": table_name,
                    "Column Name": column.column,
                    "Data Type": column.type,
                    "Business Description": column.description or "No description available in Dataplex"
                })
            return pd.DataFrame(metadata_records)
        except Exception as e:
            print(f"[Error] Dataplex Metadata Lookup failed: {e}")
            return pd.DataFrame()