import json
from datetime import datetime, timezone
from azure.identity import InteractiveBrowserCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
import yaml

# --- Configuration ---
with open("_DATA_AND_OUTPUTS/config.yaml", "r") as f:
    config_yaml = yaml.safe_load(f)
    
SUBSCRIPTION_ID = config_yaml["subscription_id"]
RESOURCE_GROUP = config_yaml["resource_group"]
FACTORY_NAME = config_yaml["factory_name"]


# How far back to fetch run history
RUNS_LOOKBACK_DAYS = 30

print("Authenticating...")
credential = InteractiveBrowserCredential()
adf_client = DataFactoryManagementClient(credential, SUBSCRIPTION_ID)

factory_dump = {
    "factory_name": FACTORY_NAME,
    "extracted_at": datetime.now(timezone.utc).isoformat(),

    # --- Definition / Config layer ---
    "factory_metadata": {},
    "global_parameters": {},
    "linked_services": {},
    "datasets": {},
    "pipelines": {},
    "data_flows": {},
    "triggers": {},

    # --- Infrastructure layer ---
    "integration_runtimes": {},          # IR definitions
    "integration_runtime_status": {},    # live status per IR
    "integration_runtime_nodes": {},     # node-level metrics (self-hosted IRs)

    # --- Networking layer ---
    "managed_virtual_networks": {},
    "managed_private_endpoints": {},
    "private_endpoint_connections": {},
    "private_link_resources": {},
    "credential_operations": {},

    # --- CDC ---
    "change_data_capture": {},
}

print(f"=== Starting Full JSON Extract for {FACTORY_NAME} ===")

# ── 1. Factory metadata ────────────────────────────────────────────────────────
print("Fetching factory metadata...")
factory_obj = adf_client.factories.get(RESOURCE_GROUP, FACTORY_NAME)
factory_dump["factory_metadata"] = factory_obj.as_dict()

# ── 2. Global Parameters ───────────────────────────────────────────────────────
print("Fetching Global Parameters...")
for gp in adf_client.global_parameters.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
    gp_def = adf_client.global_parameters.get(RESOURCE_GROUP, FACTORY_NAME, gp.name)
    factory_dump["global_parameters"][gp.name] = gp_def.as_dict()

# ── 3. Linked Services ─────────────────────────────────────────────────────────
print("Fetching Linked Services...")
for ls in adf_client.linked_services.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
    ls_def = adf_client.linked_services.get(RESOURCE_GROUP, FACTORY_NAME, ls.name)
    factory_dump["linked_services"][ls.name] = ls_def.as_dict()

# ── 4. Datasets ────────────────────────────────────────────────────────────────
print("Fetching Datasets...")
for ds in adf_client.datasets.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
    ds_def = adf_client.datasets.get(RESOURCE_GROUP, FACTORY_NAME, ds.name)
    factory_dump["datasets"][ds.name] = ds_def.as_dict()

# ── 5. Pipelines ───────────────────────────────────────────────────────────────
print("Fetching Pipelines...")
for pl in adf_client.pipelines.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
    pl_def = adf_client.pipelines.get(RESOURCE_GROUP, FACTORY_NAME, pl.name)
    factory_dump["pipelines"][pl.name] = pl_def.as_dict()

# ── 6. Data Flows ──────────────────────────────────────────────────────────────
print("Fetching Data Flows...")
for df in adf_client.data_flows.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
    df_def = adf_client.data_flows.get(RESOURCE_GROUP, FACTORY_NAME, df.name)
    factory_dump["data_flows"][df.name] = df_def.as_dict()

# ── 7. Triggers ────────────────────────────────────────────────────────────────
print("Fetching Triggers...")
for tr in adf_client.triggers.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
    tr_def = adf_client.triggers.get(RESOURCE_GROUP, FACTORY_NAME, tr.name)
    factory_dump["triggers"][tr.name] = tr_def.as_dict()

# ── 8. Integration Runtimes ────────────────────────────────────────────────────
print("Fetching Integration Runtimes...")
for ir in adf_client.integration_runtimes.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
    ir_def = adf_client.integration_runtimes.get(RESOURCE_GROUP, FACTORY_NAME, ir.name)
    factory_dump["integration_runtimes"][ir.name] = ir_def.as_dict()

    # Live status (starts, version, capabilities)
    try:
        ir_status = adf_client.integration_runtimes.get_status(RESOURCE_GROUP, FACTORY_NAME, ir.name)
        factory_dump["integration_runtime_status"][ir.name] = ir_status.as_dict()
    except Exception as e:
        factory_dump["integration_runtime_status"][ir.name] = {"error": str(e)}

    # Node-level metrics (only meaningful for self-hosted IRs)
    try:
        ir_monitoring = adf_client.integration_runtimes.get_monitoring_data(RESOURCE_GROUP, FACTORY_NAME, ir.name)
        factory_dump["integration_runtime_nodes"][ir.name] = ir_monitoring.as_dict()
    except Exception as e:
        factory_dump["integration_runtime_nodes"][ir.name] = {"error": str(e)}

# ── 9. Managed VNet & Private Endpoints ───────────────────────────────────────
print("Fetching Managed Virtual Networks...")
try:
    for mvn in adf_client.managed_virtual_networks.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
        mvn_def = adf_client.managed_virtual_networks.get(RESOURCE_GROUP, FACTORY_NAME, mvn.name)
        factory_dump["managed_virtual_networks"][mvn.name] = mvn_def.as_dict()

        # Private endpoints inside this managed VNet
        for mpe in adf_client.managed_private_endpoints.list_by_factory(
            RESOURCE_GROUP, FACTORY_NAME, mvn.name
        ):
            mpe_def = adf_client.managed_private_endpoints.get(
                RESOURCE_GROUP, FACTORY_NAME, mvn.name, mpe.name
            )
            factory_dump["managed_private_endpoints"][mpe.name] = mpe_def.as_dict()
except Exception as e:
    factory_dump["managed_virtual_networks"]["error"] = str(e)

# ── 10. Private Endpoint Connections (to the factory itself) ──────────────────
print("Fetching Private Endpoint Connections...")
try:
    for pec in adf_client.private_end_point_connections.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
        factory_dump["private_endpoint_connections"][pec.name] = pec.as_dict()
except Exception as e:
    factory_dump["private_endpoint_connections"]["error"] = str(e)

# ── 11. Private Link Resources ─────────────────────────────────────────────────
print("Fetching Private Link Resources...")
try:
    plr = adf_client.private_link_resources.get(RESOURCE_GROUP, FACTORY_NAME)
    factory_dump["private_link_resources"] = plr.as_dict()
except Exception as e:
    factory_dump["private_link_resources"] = {"error": str(e)}

# ── 12. Credentials ────────────────────────────────────────────────────────────
print("Fetching Credentials...")
try:
    for cred in adf_client.credential_operations.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
        cred_def = adf_client.credential_operations.get(RESOURCE_GROUP, FACTORY_NAME, cred.name)
        factory_dump["credential_operations"][cred.name] = cred_def.as_dict()
except Exception as e:
    factory_dump["credential_operations"]["error"] = str(e)

# ── 13. Change Data Capture ────────────────────────────────────────────────────
print("Fetching Change Data Capture resources...")
try:
    for cdc in adf_client.change_data_capture.list_by_factory(RESOURCE_GROUP, FACTORY_NAME):
        cdc_def = adf_client.change_data_capture.get(RESOURCE_GROUP, FACTORY_NAME, cdc.name)
        factory_dump["change_data_capture"][cdc.name] = cdc_def.as_dict()
except Exception as e:
    factory_dump["change_data_capture"]["error"] = str(e)


# ── Save ───────────────────────────────────────────────────────────────────────
output_filename = f"_DATA_AND_OUTPUTS/{FACTORY_NAME}_full_extract.json"
print(f"\nWriting to {output_filename}...")
with open(output_filename, "w") as outfile:
    json.dump(factory_dump, outfile, indent=4, default=str)

print("=== Extract Complete ===")