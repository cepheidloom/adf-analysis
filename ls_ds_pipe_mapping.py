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
        pipeline_name, datasets (set), direct_linked_services (set)
    """
    rows = []
    for sheet_name, df in act_dfs.items():
        if sheet_name in ACTIVITY_META_KEYS:
            continue

        for _, row in df.iterrows():
            pipeline_name = row.get("pipeline_name")
            if not pipeline_name or pd.isna(pipeline_name):
                continue

            datasets = set()
            direct_ls = set()

            # --- Collect dataset references ---
            for col in ("inputs_dataset", "outputs_dataset", "dataset"):
                val = row.get(col)
                if val and pd.notna(val):
                    datasets.add(str(val))

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
                "pipeline_name":        str(pipeline_name),
                "datasets":             datasets,
                "direct_linked_services": direct_ls,
            })
    return rows


def build_lineage_df(ds_dfs: dict, act_dfs: dict) -> pd.DataFrame:
    """
    Combines dataset and activity information into a flat lineage table:
        Linked Service | Dataset | Pipeline
    """
    dataset_ls_map   = build_dataset_ls_map(ds_dfs)
    activity_rows    = extract_activity_references(act_dfs)
    output_rows      = []

    # Track which datasets were seen in at least one activity
    datasets_seen_in_activities = set()

    for act_row in activity_rows:
        pipeline = act_row["pipeline_name"]
        datasets  = act_row["datasets"]
        direct_ls = act_row["direct_linked_services"]

        # ----------------------------------------------------------------
        # Case A: Activity references a Dataset
        #   → resolve the LS from the dataset map
        #   → emit (LS, Dataset, Pipeline)
        # ----------------------------------------------------------------
        for ds in datasets:
            datasets_seen_in_activities.add(ds)
            ls = dataset_ls_map.get(ds)          # may be None if LS not found
            output_rows.append({
                "Linked Service": ls,
                "Dataset":        ds,
                "Pipeline":       pipeline,
            })

        # ----------------------------------------------------------------
        # Case B: Activity references an LS directly (no dataset in row)
        #   → emit (LS, None, Pipeline)
        # ----------------------------------------------------------------
        for ls in direct_ls:
            output_rows.append({
                "Linked Service": ls,
                "Dataset":        None,
                "Pipeline":       pipeline,
            })

    # ----------------------------------------------------------------
    # Case C: Dataset exists but was never referenced in any activity
    #   → emit (LS, Dataset, None)
    # ----------------------------------------------------------------
    for ds_name, ls_name in dataset_ls_map.items():
        if ds_name not in datasets_seen_in_activities:
            output_rows.append({
                "Linked Service": ls_name,
                "Dataset":        ds_name,
                "Pipeline":       None,
            })

    df = pd.DataFrame(output_rows, columns=["Linked Service", "Dataset", "Pipeline"])
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

    ###################################
    #######@@@ Execution Flow @@@######
    ###################################

    # 1. Load all dataframes from the three processing modules
    ls_dfs  = get_linked_services_dataframes(adf_json)   # for reference (not used in joins directly)
    ds_dfs  = get_datasets_dataframes(adf_json)
    act_dfs = get_activities_dataframes(adf_json)

    # 2. Build the lineage DataFrame
    lineage_df = build_lineage_df(ds_dfs, act_dfs)

    # 3. Export to Excel
    export_lineage_to_excel(lineage_df)
