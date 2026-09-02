import os
import json
import yaml
import pandas as pd

from linked_services_processing import get_linked_services_dataframes
from datasets_processing import get_datasets_dataframes
from activities_processing import get_activities_dataframes


# ---------------------------------------------------------------------------
# Meta-keys to skip when iterating dataframe dictionaries
# ---------------------------------------------------------------------------
ACTIVITY_META_KEYS = {"pipeline_summary", "pipeline_activity_navigation", "pipeline_references"}
DATASET_META_KEYS  = {"Summary", "Datasets Navigation"}


def build_ls_source_map(ls_mapping_json: dict) -> dict:
    """
    Flattens the multi-factory LS mapping JSON into a single lookup:
        { linked_service_name -> mapped_source }
    Duplicate LS names across factories will be overwritten by the last occurrence.
    """
    ls_source_map = {}
    # for factory, entries in ls_mapping_json.items():
    for entry in ls_mapping_json["JZN Analysis"]:
        ls_name = entry.get("Linked Service Name")
        source  = entry.get("Mapped / Inferred Source")
        if ls_name and source and str(source) != "nan":
            ls_source_map[str(ls_name)] = str(source)
    return ls_source_map


def _resolve_connection_detail(row: pd.Series, df_columns: set) -> str | None:
    """
    Resolves the connection detail string for a single LS row.
    Priority: connection_string (split on ;) → server+database fallback → all other URL columns.
    """
    # --- Special: connection_string with ; separator ---
    if "connection_string" in df_columns:
        cs_val = row.get("connection_string")
        if cs_val and pd.notna(cs_val) and str(cs_val).strip():
            REDUNDANT_KEYS = {"integrated security","user id","User Id", "Integrated Security", "Encrypt", "Connection Timeout"}
            parts = []
            for p in str(cs_val).split(";"):
                p = p.strip()
                if not p:
                    continue
                key = p.split("=")[0].strip()
                if key not in REDUNDANT_KEYS:
                    parts.append(p)
            return "\n".join(parts)
        # Fallback to server + database
        parts = []
        for col, label in (("server", "Server"), ("database", "Database")):
            if col in df_columns:
                val = row.get(col)
                if val and pd.notna(val) and str(val).strip():
                    parts.append(f"{label}: {str(val).strip()}")
        if parts:
            return "\n".join(parts)

    # --- All other single-value connection columns ---
    for col in ("base_url", "url", "domain", "host", "data_lake_store_uri",
                "endpoint", "environment_url", "sas_uri", "service_uri"):
        if col in df_columns:
            val = row.get(col)
            if val and pd.notna(val) and str(val).strip():
                return str(val).strip()

    return None


def build_ls_info_map(ls_dfs: dict) -> dict:
    """
    Scans every raw LS-type DataFrame and returns a flat lookup:
        { linked_service_name -> { "ls_type": str, "connection_detail": str | None } }
    Skips meta sheets (Summary, Linked Services Navigation).
    """
    LS_META_KEYS = {"Summary", "Linked Services Navigation"}
    ls_info_map = {}

    for sheet_name, df in ls_dfs.items():
        if sheet_name in LS_META_KEYS:
            continue
        if "linked_service_name" not in df.columns or "type" not in df.columns:
            continue

        df_columns = set(df.columns)
        for _, row in df.iterrows():
            ls_name = row.get("linked_service_name")
            ls_type = row.get("type")

            if not ls_name or pd.isna(ls_name):
                continue

            ls_info_map[str(ls_name)] = {
                "ls_type":           str(ls_type) if ls_type and pd.notna(ls_type) else None,
                "connection_detail": _resolve_connection_detail(row, df_columns),
            }

    return ls_info_map


def build_dataset_ls_map(ds_dfs: dict) -> dict:
    """
    Scans every raw dataset-type DataFrame and returns a flat lookup:
        { dataset_name -> linked_service_name }
    Skips meta sheets (Summary, Datasets Navigation).
    """
    dataset_ls_map = {}
    for sheet_name, df in ds_dfs.items():
        if sheet_name in DATASET_META_KEYS:
            continue
        if "dataset_name" not in df.columns or "linked_service_name" not in df.columns:
            continue
        for _, row in df.iterrows():
            ds_name = row.get("dataset_name")
            ls_name = row.get("linked_service_name")
            if pd.notna(ds_name) and pd.notna(ls_name):
                dataset_ls_map[str(ds_name)] = str(ls_name)
    return dataset_ls_map


def extract_activity_references(act_dfs: dict) -> list[dict]:
    """
    Scans every raw activity-type DataFrame and extracts:
        - pipeline_name
        - datasets referenced (inputs_dataset, outputs_dataset, dataset)
        - linked services referenced directly (linked_service_name,
          auth_linked_service, web_linked_services)

    Returns a list of dicts, each with keys:
        pipeline_name, datasets (dict of name->role), direct_linked_services (set)
    """
    rows = []
    for sheet_name, df in act_dfs.items():
        if sheet_name in ACTIVITY_META_KEYS:
            continue

        for _, row in df.iterrows():
            pipeline_name = row.get("pipeline_name")
            if not pipeline_name or pd.isna(pipeline_name):
                continue

            datasets = {}   # { dataset_name -> role }
            direct_ls = set()

            # --- Collect dataset references ---
            col_role_map = {
                "inputs_dataset":  "Input (Copy)",
                "outputs_dataset": "Output (Copy)",
                "dataset":         "Referenced",
            }
            for col, role in col_role_map.items():
                val = row.get(col)
                if val and pd.notna(val):
                    datasets[str(val)] = role

            # --- Collect direct linked service references ---
            for col in ("linked_service_name", "auth_linked_service"):
                val = row.get(col)
                if val and pd.notna(val):
                    direct_ls.add(str(val))

            # web_linked_services is newline-joined
            web_ls = row.get("web_linked_services")
            if web_ls and pd.notna(web_ls):
                for ls in str(web_ls).split("\n"):
                    ls = ls.strip()
                    if ls:
                        direct_ls.add(ls)

            rows.append({
                "pipeline_name":          str(pipeline_name),
                "datasets":               datasets,
                "direct_linked_services": direct_ls,
            })
    return rows


def build_lineage_df(ds_dfs: dict, act_dfs: dict, ls_source_map: dict, ls_info_map: dict) -> pd.DataFrame:
    """
    Combines dataset and activity information into a flat lineage table:
        Linked Service | Source | LS Type | LS Connection Detail | Dataset | Pipeline | Dataset Role
    """
    dataset_ls_map   = build_dataset_ls_map(ds_dfs)
    activity_rows    = extract_activity_references(act_dfs)
    output_rows      = []

    datasets_seen_in_activities = set()

    for act_row in activity_rows:
        pipeline  = act_row["pipeline_name"]
        datasets  = act_row["datasets"]
        direct_ls = act_row["direct_linked_services"]

        # Case A: Activity references a Dataset
        for ds, role in datasets.items():
            datasets_seen_in_activities.add(ds)
            ls      = dataset_ls_map.get(ds)
            ls_info = ls_info_map.get(ls, {}) if ls else {}
            output_rows.append({
                "Linked Service":       ls,
                "Source":               ls_source_map.get(ls) if ls else None,
                "LS Type":              ls_info.get("ls_type"),
                "LS Connection Detail": ls_info.get("connection_detail"),
                "Dataset":              ds,
                "Pipeline":             pipeline,
                "Dataset Role":         role,
            })

        # Case B: Activity references an LS directly
        for ls in direct_ls:
            ls_info = ls_info_map.get(ls, {})
            output_rows.append({
                "Linked Service":       ls,
                "Source":               ls_source_map.get(ls),
                "LS Type":              ls_info.get("ls_type"),
                "LS Connection Detail": ls_info.get("connection_detail"),
                "Dataset":              None,
                "Pipeline":             pipeline,
                "Dataset Role":         None,
            })

    # Case C: Dataset never referenced in any activity
    for ds_name, ls_name in dataset_ls_map.items():
        if ds_name not in datasets_seen_in_activities:
            ls_info = ls_info_map.get(ls_name, {})
            output_rows.append({
                "Linked Service":       ls_name,
                "Source":               ls_source_map.get(ls_name),
                "LS Type":              ls_info.get("ls_type"),
                "LS Connection Detail": ls_info.get("connection_detail"),
                "Dataset":              ds_name,
                "Pipeline":             None,
                "Dataset Role":         "Unreferenced",
            })

    df = pd.DataFrame(output_rows, columns=[
        "Linked Service", "Source", "LS Type", "LS Connection Detail",
        "Dataset", "Pipeline", "Dataset Role"
    ])
    df = df.drop_duplicates()
    df = df.sort_values(["Linked Service", "Dataset", "Pipeline"], na_position="last")
    df = df.reset_index(drop=True)
    return df


def export_lineage_to_excel(
    df: pd.DataFrame,
    output_path: str = "_DATA_AND_OUTPUTS/presentable_outputs/Lineage_Mapping.xlsx"
):
    """
    Writes the lineage DataFrame to an Excel workbook (single sheet).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Lineage Mapping")
    print(f"[✓] Lineage mapping exported → {output_path}")
    print(f"    Total rows : {len(df)}")


if __name__ == "__main__":

    # *****-------------*****
    # ---- Configuration ----
    # *****-------------*****
    with open("_DATA_AND_OUTPUTS/config.yaml", "r") as f:
        config_yaml = yaml.safe_load(f)

    json_path = config_yaml["full_extract_path"]

    with open(json_path, "r") as f:
        adf_json = json.load(f)

    with open("_DATA_AND_OUTPUTS/ls_source_mapping.json", "r") as f:
        ls_mapping_json = json.load(f)



    ###################################
    #######@@@ Execution Flow @@@######
    ###################################

    # 1. Load all dataframes from the three processing modules
    ls_dfs  = get_linked_services_dataframes(adf_json)   # for reference (not used in joins directly)
    ds_dfs  = get_datasets_dataframes(adf_json)
    act_dfs = get_activities_dataframes(adf_json)

    # 2. Build the lineage DataFrame
    ls_source_map = build_ls_source_map(ls_mapping_json)
    ls_info_map   = build_ls_info_map(ls_dfs)         
    lineage_df    = build_lineage_df(ds_dfs, act_dfs, ls_source_map, ls_info_map)

    # 3. Export to Excel
    export_lineage_to_excel(lineage_df)
