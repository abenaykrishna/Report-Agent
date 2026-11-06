import os
from google.cloud import bigquery

client = bigquery.Client(project="anz-cloud-migration")

datasets = ["gold_insurance_layer", "gold_layer", "phi_gold_reporting"]

for dataset_id in datasets:
    print(f"\nTables in dataset: {dataset_id}")
    try:
        tables = list(client.list_tables(dataset_id))
        for table in tables:
            print(f" - {table.table_id}")
            # print first 5 columns of each table
            t_ref = client.get_table(f"anz-cloud-migration.{dataset_id}.{table.table_id}")
            cols = [f.name for f in t_ref.schema][:5]
            print(f"   cols: {cols}")
    except Exception as e:
        print(f"Error listing tables in {dataset_id}: {e}")
