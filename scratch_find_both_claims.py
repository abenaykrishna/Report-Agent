from google.cloud import bigquery

client = bigquery.Client(project="anz-cloud-migration")

datasets = list(client.list_datasets())
found = False

for dataset in datasets:
    dataset_id = dataset.dataset_id
    try:
        tables = list(client.list_tables(dataset_id))
        for table in tables:
            if "both_claims" in table.table_id or "both_claims_data_primary_raw_raw" in table.table_id:
                print(f"FOUND: anz-cloud-migration.{dataset_id}.{table.table_id}")
                found = True
    except Exception:
        pass

if not found:
    print("Table both_claims_data_primary_raw_raw not found.")
