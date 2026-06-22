import json
import os
from datetime import datetime, timedelta, timezone
from azure.identity import InteractiveBrowserCredential
from azure.mgmt.datafactory import DataFactoryManagementClient
from azure.mgmt.datafactory.models import (
    RunFilterParameters,
    RunQueryFilter,
    RunQueryFilterOperand,
    RunQueryFilterOperator
)
import yaml
# --- Configuration ---
with open("config.yaml", "r") as f:
    config_yaml = yaml.safe_load(f)
    
SUBSCRIPTION_ID = config_yaml["subscription_id"]
RESOURCE_GROUP = config_yaml["resource_group"]
FACTORY_NAME = config_yaml["factory_name"]

LOOKBACK_DAYS = 30

PIPELINES_TO_SKIP = [
    "MG_IN_Streaming_Alerts",
    "Graylog_LRS_Affiliate_Servers_2",
    "ADF-DB_LOCK_LOG",
    "AT_IN_SITE_USER_COUNT_RAW"
]

OUTPUT_FILE = f"{FACTORY_NAME}_runs.jsonl"
CHECKPOINT_FILE = f"{FACTORY_NAME}_checkpoint.json"

# --- Helpers ---
def save_checkpoint(token, runs_written, pages_fetched):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({
            "continuation_token": token,
            "runs_written": runs_written,
            "pages_fetched": pages_fetched,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }, f, indent=2)

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return None

def append_run(run_record):
    with open(OUTPUT_FILE, "a") as f:
        f.write(json.dumps(run_record, default=str) + "\n")

# --- Auth ---
print("Authenticating...")
credential = InteractiveBrowserCredential()
adf_client = DataFactoryManagementClient(credential, SUBSCRIPTION_ID)

# --- Time Window + Server-Side Filter ---
now = datetime.now(timezone.utc)

filter_params = RunFilterParameters(
    last_updated_after=now - timedelta(days=LOOKBACK_DAYS),
    last_updated_before=now,
    filters=[
        RunQueryFilter(
            operand=RunQueryFilterOperand.PIPELINE_NAME,
            operator=RunQueryFilterOperator.NOT_IN,
            values=PIPELINES_TO_SKIP
        )
    ] if PIPELINES_TO_SKIP else None
)

# --- Resume or Start Fresh ---
checkpoint = load_checkpoint()
runs_written = 0
pages_fetched = 0

if checkpoint:
    print(f"\nResuming from checkpoint:")
    print(f"  Pages already fetched : {checkpoint['pages_fetched']}")
    print(f"  Runs already written  : {checkpoint['runs_written']}")
    print(f"  Last updated          : {checkpoint['last_updated']}")
    filter_params.continuation_token = checkpoint["continuation_token"]
    runs_written = checkpoint["runs_written"]
    pages_fetched = checkpoint["pages_fetched"]
else:
    print("\nStarting fresh...")
    if os.path.exists(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)

print(f"\nFetching pipeline runs (last {LOOKBACK_DAYS} days)...")
print(f"Skipping pipelines: {PIPELINES_TO_SKIP}\n")

try:
    while True:
        page_result = adf_client.pipeline_runs.query_by_factory(
            RESOURCE_GROUP, FACTORY_NAME, filter_params
        )
        pages_fetched += 1
        batch = page_result.value

        if not batch:
            break

        next_token = page_result.continuation_token
        save_checkpoint(next_token, runs_written, pages_fetched)
        print(f"Page {pages_fetched} fetched ({len(batch)} runs) | Total written so far: {runs_written}")

        for run in batch:
            run_record = {
                # --- Identity ---
                "run_id": run.run_id,
                "pipeline_name": run.pipeline_name,

                # --- Status & Timing ---
                "status": run.status,
                "run_start": str(run.run_start),
                "run_end": str(run.run_end),
                "duration_ms": run.duration_in_ms,
                "message": run.message,

                # --- Invocation ---
                "invoked_by": {
                    "name": run.invoked_by.name if run.invoked_by else None,
                    "id": run.invoked_by.id if run.invoked_by else None,
                    "invoked_by_type": run.invoked_by.invoked_by_type if run.invoked_by else None,
                },

                # --- Parameters ---
                "pipeline_parameters": run.parameters or {},

                # --- Activities ---
                "copy_activities": [],
                "all_activities_summary": []
            }

            try:
                activity_filter = RunFilterParameters(
                    last_updated_after=now - timedelta(days=LOOKBACK_DAYS),
                    last_updated_before=now
                )
                activity_runs = adf_client.activity_runs.query_by_pipeline_run(
                    RESOURCE_GROUP, FACTORY_NAME, run.run_id, activity_filter
                )

                for act in activity_runs.value:
                    run_record["all_activities_summary"].append({
                        "activity_name": act.activity_name,
                        "activity_type": act.activity_type,
                        "status": act.status,
                        "duration_ms": act.duration_in_ms,
                        "activity_run_start": str(act.activity_run_start),
                        "activity_run_end": str(act.activity_run_end),
                        "error": act.error if act.status == "Failed" else None
                    })

                    if act.activity_type == "Copy":
                        act_input = act.input or {}
                        act_output = act.output or {}

                        source_props = {k: v for k, v in act_input.get("source", {}).items() if not str(k).startswith("$")}
                        sink_props = {k: v for k, v in act_input.get("sink", {}).items() if not str(k).startswith("$")}

                        run_record["copy_activities"].append({
                            # --- Identity ---
                            "activity_name": act.activity_name,
                            "activity_run_id": act.activity_run_id,
                            "pipeline_run_id": act.pipeline_run_id,

                            # --- Status & Timing ---
                            "status": act.status,
                            "duration_ms": act.duration_in_ms,
                            "activity_run_start": str(act.activity_run_start),
                            "activity_run_end": str(act.activity_run_end),
                            "error": act.error if act.status == "Failed" else None,

                            # --- Source ---
                            "source_datasets": act_input.get("inputs", []),
                            "source_execution": source_props,

                            # --- Sink ---
                            "sink_datasets": act_input.get("outputs", []),
                            "sink_execution": sink_props,

                            # --- Translator / Column Mapping ---
                            "translator": act_input.get("translator"),

                            # --- Volume & Performance ---
                            "rows_read": act_output.get("rowsRead"),
                            "rows_written": act_output.get("rowsCopied"),
                            "data_read_bytes": act_output.get("dataRead"),
                            "data_written_bytes": act_output.get("dataWritten"),
                            "throughput_kb_per_s": act_output.get("throughput"),
                            "used_parallel_copies": act_output.get("usedParallelCopies"),
                            "copy_duration_ms": act_output.get("copyDuration"),
                            "execution_details": act_output.get("executionDetails", []),

                            # --- Raw Payloads ---
                            "raw_input": act_input,
                            "raw_output": act_output
                        })

            except Exception as e:
                run_record["activity_fetch_error"] = str(e)

            append_run(run_record)
            runs_written += 1

        save_checkpoint(next_token, runs_written, pages_fetched)

        if not next_token:
            print("\nAll pages fetched — no more continuation token.")
            break

        filter_params.continuation_token = next_token

except KeyboardInterrupt:
    print(f"\n\nInterrupted. Progress saved.")
    print(f"Pages fetched : {pages_fetched}")
    print(f"Runs written  : {runs_written}")
    print(f"Re-run the script to resume.")
    exit(0)

except Exception as e:
    print(f"\n\nUnexpected error: {e}")
    print(f"Progress saved to checkpoint. Re-run to resume.")
    raise

# --- Completion ---
if os.path.exists(CHECKPOINT_FILE):
    os.remove(CHECKPOINT_FILE)
    print("Checkpoint cleaned up.")

print(f"\n=== Complete ===")
print(f"Total pages fetched : {pages_fetched}")
print(f"Total runs written  : {runs_written}")
print(f"Output              : {OUTPUT_FILE}")