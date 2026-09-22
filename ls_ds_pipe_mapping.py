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

# True  -> "Copy Lineage" sheet covers every activity type
# False -> "Copy Lineage" sheet covers Copy activities only
INCLUDE_ALL_ACTIVITIES = True
# Ordered groups of dataset columns that reveal the table / path / url a dataset points at.
# The first group with at least one populated column wins.
DATASET_DETAIL_COLUMN_GROUPS = [
    ("schema_type_properties_schema", "table"),
    ("relative_url",),
    ("location", "sheet_name"),
    ("folder_path", "file_name"),
    ("object_api_name",),
    ("table_name",),
    ("entity_name",),
]

# Visual divider used when two source columns are merged into one cell
CELL_COLUMN_DIVIDER = "\n" + "-" * 56 + "\n"

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


def _resolve_dataset_detail(row: pd.Series, df_columns: set) -> str | None:
    """
    Resolves the location/table detail string for a single dataset row by walking
    DATASET_DETAIL_COLUMN_GROUPS and returning the first group that has data.
    When a group yields more than one populated column, each value gets a
    `|COL:- name| =>>` header and the values are split by a dashed divider;
    a lone value is returned raw.
    """
    for group in DATASET_DETAIL_COLUMN_GROUPS:
        blocks = []
        for col in group:
            if col not in df_columns:
                continue
            val = row.get(col)
            if val is None or not pd.notna(val) or not str(val).strip():
                continue
            blocks.append((col, str(val).strip()))
        if len(blocks) == 1:
            return blocks[0][1]
        if blocks:
            return CELL_COLUMN_DIVIDER.join(f"|COL:- {col}| =>>\n{val}" for col, val in blocks)
    return None


def build_dataset_detail_map(ds_dfs: dict) -> dict:
    """
    Scans every raw dataset-type DataFrame and returns a flat lookup:
        { dataset_name -> resolved location/table detail string | None }
    Skips meta sheets (Summary, Datasets Navigation).
    """
    dataset_detail_map = {}
    for sheet_name, df in ds_dfs.items():
        if sheet_name in DATASET_META_KEYS:
            continue
        if "dataset_name" not in df.columns:
            continue
        df_columns = set(df.columns)
        for _, row in df.iterrows():
            ds_name = row.get("dataset_name")
            if not ds_name or pd.isna(ds_name):
                continue
            dataset_detail_map[str(ds_name)] = _resolve_dataset_detail(row, df_columns)
    return dataset_detail_map


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


def build_pipeline_info_map(act_dfs: dict) -> dict:
    """
    Reads the `pipeline_summary` sheet and returns a flat lookup:
        { pipeline_name -> { "parameters": str | None, "variables": str | None } }
    Values are already bullet-formatted by activities_processing.
    """
    pipeline_info_map = {}
    summary_df = act_dfs.get("pipeline_summary")
    if summary_df is None or summary_df.empty or "pipeline_name" not in summary_df.columns:
        return pipeline_info_map

    for _, row in summary_df.iterrows():
        pl_name = row.get("pipeline_name")
        if not pl_name or pd.isna(pl_name):
            continue
        info = {}
        for col in ("parameters", "variables"):
            val = row.get(col) if col in summary_df.columns else None
            info[col] = str(val).strip() if val is not None and pd.notna(val) and str(val).strip() else None
        pipeline_info_map[str(pl_name)] = info
    return pipeline_info_map


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


def _format_dataset_parameters(value) -> str | None:
    """
    Renders a dataset-reference `parameters` dict (as produced by
    activities_processing) into a readable multi-line string.
    A single rendered cell covers both the resolved object/table and the
    resolved URL/path, because those live in the same parameter dict.
    """
    if not isinstance(value, dict) or not value:
        return None

    lines = []
    for k, v in value.items():
        if isinstance(v, dict):
            v = v.get("value", v)
        lines.append(f"• {k} => {v}")
    return "\n".join(lines) if lines else None


def build_copy_lineage_df(ds_dfs: dict, act_dfs: dict, ls_info_map: dict,
                          include_all_activities: bool = INCLUDE_ALL_ACTIVITIES) -> pd.DataFrame:
    """
    Builds a source→sink lineage table from the activity DataFrames produced by
    activities_processing.get_activities_dataframes.

    include_all_activities=False -> only the `Copy` activity sheet.
    include_all_activities=True  -> every activity sheet; non-Copy activities fall
    back to their single `dataset` / `linked_service_name` reference on the source side.

    Linked service columns are resolved from the dataset each side points to,
    reusing the same dataset→LS and LS→info lookups as build_lineage_df.
    """
    dataset_ls_map     = build_dataset_ls_map(ds_dfs)
    dataset_detail_map = build_dataset_detail_map(ds_dfs)
    pipeline_info_map  = build_pipeline_info_map(act_dfs)

    columns = [
        "Pipeline_Name", "Activity_Name",
        "Source_Dataset_Name", "Source_Dataset_Type", "Source_Dataset_Detail", "Source_Dataset_Parameters",
        "Sink_Dataset_Name", "Sink_Dataset_Type", "Sink_Dataset_Detail", "Sink_Dataset_Parameters",
        "Pipeline_Parameters", "Pipeline_Variables",
        "Source_LinkedService", "Source_LinkedService_Type", "Source_LS_Connection_Detail",
        "Sink_LinkedService", "Sink_LinkedService_Type", "Sink_LS_Connection_Detail",
    ]
    if include_all_activities:
        columns.insert(2, "Activity_Type")

    if include_all_activities:
        activity_dfs = [df for sheet, df in act_dfs.items() if sheet not in ACTIVITY_META_KEYS]
    else:
        activity_dfs = [act_dfs["Copy"]] if "Copy" in act_dfs else []

    activity_dfs = [df for df in activity_dfs if df is not None and not df.empty]
    if not activity_dfs:
        return pd.DataFrame(columns=columns)

    def _scalar(row: pd.Series, col: str):
        val = row.get(col)
        if val is None or (not isinstance(val, (dict, list)) and pd.isna(val)):
            return None
        return str(val)

    output_rows = []
    for act_df in activity_dfs:
        for _, row in act_df.iterrows():
            pipeline = _scalar(row, "pipeline_name")
            src_ds = _scalar(row, "inputs_dataset") or _scalar(row, "dataset")
            snk_ds = _scalar(row, "outputs_dataset")

            src_ls = dataset_ls_map.get(src_ds) if src_ds else None
            src_ls = src_ls or _scalar(row, "linked_service_name")
            snk_ls = dataset_ls_map.get(snk_ds) if snk_ds else None
            src_ls_info = ls_info_map.get(src_ls, {}) if src_ls else {}
            snk_ls_info = ls_info_map.get(snk_ls, {}) if snk_ls else {}
            pl_info     = pipeline_info_map.get(pipeline, {}) if pipeline else {}

            output_rows.append({
                "Pipeline_Name":               pipeline,
                "Activity_Name":               _scalar(row, "name"),
                "Activity_Type":               _scalar(row, "type"),
                "Source_Dataset_Name":         src_ds,
                "Source_Dataset_Type":         _scalar(row, "source_type"),
                "Source_Dataset_Detail":       dataset_detail_map.get(src_ds) if src_ds else None,
                "Source_Dataset_Parameters":   _format_dataset_parameters(row.get("inputs_dataset_parameters")),
                "Sink_Dataset_Name":           snk_ds,
                "Sink_Dataset_Type":           _scalar(row, "sink_type"),
                "Sink_Dataset_Detail":         dataset_detail_map.get(snk_ds) if snk_ds else None,
                "Sink_Dataset_Parameters":     _format_dataset_parameters(row.get("outputs_dataset_parameters")),
                "Pipeline_Parameters":         pl_info.get("parameters"),
                "Pipeline_Variables":          pl_info.get("variables"),
                "Source_LinkedService":        src_ls,
                "Source_LinkedService_Type":   src_ls_info.get("ls_type"),
                "Source_LS_Connection_Detail": src_ls_info.get("connection_detail"),
                "Sink_LinkedService":          snk_ls,
                "Sink_LinkedService_Type":     snk_ls_info.get("ls_type"),
                "Sink_LS_Connection_Detail":   snk_ls_info.get("connection_detail"),
            })

    df = pd.DataFrame(output_rows, columns=columns)
    df = df.drop_duplicates()
    df = df.sort_values(["Pipeline_Name", "Activity_Name"], na_position="last")
    return df.reset_index(drop=True)


def export_lineage_to_excel(
    df: pd.DataFrame,
    copy_lineage_df: pd.DataFrame | None = None,
    output_path: str = "_DATA_AND_OUTPUTS/presentable_outputs/Lineage_Mapping.xlsx"
):
    """
    Writes the lineage DataFrame (and, when provided, the Copy-activity
    source→sink lineage) to an Excel workbook.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Lineage Mapping")
        if copy_lineage_df is not None:
            copy_lineage_df.to_excel(writer, index=False, sheet_name="Copy Lineage")
    print(f"[✓] Lineage mapping exported → {output_path}")
    print(f"    Total rows : {len(df)}")
    if copy_lineage_df is not None:
        print(f"    Copy lineage rows : {len(copy_lineage_df)}")


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

    # 2. Build the lineage DataFrames
    ls_source_map   = build_ls_source_map(ls_mapping_json)
    ls_info_map     = build_ls_info_map(ls_dfs)
    lineage_df      = build_lineage_df(ds_dfs, act_dfs, ls_source_map, ls_info_map)
    copy_lineage_df = build_copy_lineage_df(ds_dfs, act_dfs, ls_info_map)

    # 3. Export to Excel
    export_lineage_to_excel(lineage_df, copy_lineage_df)
