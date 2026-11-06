import os
from discovery_service import DiscoveryService

try:
    ds = DiscoveryService(project_id="anz-cloud-migration")
    metadata_df = ds.discover_assets()
    if not metadata_df.empty:
        print(f"Successfully discovered {len(metadata_df)} rows of metadata.")
        print("\nUnique tables and their datasets:")
        print(metadata_df[["dataset_name", "table_name"]].drop_duplicates().to_string(index=False))
        # Save a summary to a text file
        metadata_df.to_csv("discovered_metadata_summary.csv", index=False)
    else:
        print("Discovered metadata is empty.")
except Exception as e:
    print(f"Error during metadata discovery: {e}")
