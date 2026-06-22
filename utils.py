from datetime import datetime, timedelta, timezone
from collections import Counter
from azure.mgmt.datafactory.models import RunFilterParameters
from azure.identity import InteractiveBrowserCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
import yaml

def get_pipeline_folder(adf_client, resource_group, factory_name):
    print(f"Fetching folder paths for pipelines in {factory_name}...\n")
    # Dictionary to hold our mapping
    pipeline_folders = {}
    pipelines = adf_client.pipelines.list_by_factory(resource_group, factory_name)
    for pipeline in pipelines:
        # If the pipeline is in a folder, grab the path. Otherwise, mark it as Root.
        folder_path = pipeline.folder.name if pipeline.folder else "[Root / No Folder]"
        
        pipeline_folders[pipeline.name] = folder_path
        print(f"Folder: {folder_path:<30} | Pipeline: {pipeline.name}")

    # Optional: You can dump pipeline_folders to a JSON/CSV if you want to save it!


def get_pipeline_names_last_n_days(adf_client, resource_group, factory_name, lookback_days=45, max_retries=3):
    now = datetime.now(timezone.utc)
    filter_params = RunFilterParameters(
        last_updated_after=now - timedelta(days=lookback_days),
        last_updated_before=now
    )

    counts = Counter()
    while True:
        page = None
        for attempt in range(1, max_retries + 1):
            try:
                page = adf_client.pipeline_runs.query_by_factory(
                    resource_group, factory_name, filter_params,
                    connection_timeout=30, read_timeout=90
                )
                break
            except Exception as e:
                print(f"  Attempt {attempt}/{max_retries} failed: {e}")
                if attempt == max_retries:
                    raise

        for run in page.value:
            counts[run.pipeline_name] += 1

        if not page.continuation_token:
            break
        filter_params.continuation_token = page.continuation_token

    return counts

if __name__ == "__main__":
    # # --- Configuration ---
    with open("config.yaml", "r") as f:
        config_yaml = yaml.safe_load(f)
        
    SUBSCRIPTION_ID = config_yaml["subscription_id"]
    RESOURCE_GROUP = config_yaml["resource_group"]
    FACTORY_NAME = config_yaml["factory_name"]

    adf_client = DataFactoryManagementClient(InteractiveBrowserCredential(), SUBSCRIPTION_ID)
    
    get_pipeline_folder(adf_client, RESOURCE_GROUP, FACTORY_NAME)
