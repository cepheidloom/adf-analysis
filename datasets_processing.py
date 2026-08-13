import os
import pandas as pd
import json
import yaml
from collections import defaultdict

def get_datasets_dataframes(adf_json: dict) -> dict:
    """
    Parses the ADF JSON and returns a dictionary of Pandas DataFrames.
    Keys are the sheet/type names, values are the DataFrames.
    """
    type_counts = defaultdict(int)
    ds_grouped_by_type = {}

    # --- 1. Parse JSON into Python Dictionaries ---
    for ds_name, ds_content in adf_json["datasets"].items():
        properties = ds_content["properties"]
        ds_type = properties["type"]

        type_counts[ds_type] += 1
        if "Datasets Navigation" not in ds_grouped_by_type:
            ds_grouped_by_type["Datasets Navigation"] = []
        ds_grouped_by_type["Datasets Navigation"].append({"name": ds_name, "type": ds_type})
        
        row_data = {"dataset_name": ds_name}
        for key, value in properties.items():
            if isinstance(value, (dict, list)):
                if key == "linked_service_name":
                    row_data[key] = value["reference_name"]
                    continue
                if key == "folder":
                    row_data[key] = value["name"]
                    continue
                if key == "relative_url":
                    row_data[key] = value["value"]
                    continue
                if key == "location":
                    stacked_items = []
                    for loc_key, loc_val in value.items():
                        if isinstance(loc_val, dict):
                            loc_val = loc_val["value"]
                        stacked_items.append(f"{loc_key}: {loc_val}")
                    row_data[key] = "\n".join(stacked_items)
                    continue
                if key == "parameters" and isinstance(value, dict):
                    formatted_params = []
                    for p_name, p_details in value.items():
                        if isinstance(p_details, dict):
                            p_type = p_details["type"]
                            p_default = p_details.get("default_value", None)
    
                            if p_default is not None:
                                formatted_params.append(f"• {p_name} [{p_type}] -> Default: {p_default}")
                            else:
                                formatted_params.append(f"• {p_name}: {p_type}")
                        else:
                            formatted_params.append(f"• {p_name}: {p_details}")
                    row_data[key] = "\n".join(formatted_params)
                    continue
                row_data[key] = json.dumps(value)
            else:
                row_data[key] = value
        if ds_type not in ds_grouped_by_type:
            ds_grouped_by_type[ds_type] = []
        ds_grouped_by_type[ds_type].append(row_data)

    # --- 2. Convert Dictionaries to DataFrames ---
    dataframes = {}
    
    # Build Summary DataFrame
    sorted_counts = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    df_counts = pd.DataFrame(sorted_counts, columns=["Dataset Type", "Count"])
    df_counts.loc[len(df_counts)] = ["TOTAL", df_counts["Count"].sum()]
    dataframes["Summary"] = df_counts
    
    # Build Individual Type DataFrames
    for ds_type, rows in ds_grouped_by_type.items():
        dataframes[ds_type] = pd.DataFrame(rows)
        
    return dataframes


def export_datasets_to_excel(dataframes: dict, output_path: str = "_DATA_AND_OUTPUTS/presentable_outputs/Datasets.xlsx"):
    """
    Takes a dictionary of DataFrames and writes them to an Excel workbook.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # 1. Force Summary sheet to be first
        if "Summary" in dataframes:
            dataframes["Summary"].to_excel(writer, index=False, sheet_name="Summary")
            
        # 2. Force Datasets Navigation to be second
        if "Datasets Navigation" in dataframes:
            dataframes["Datasets Navigation"].to_excel(writer, index=False, sheet_name="Datasets Navigation")

        # 3. Write all remaining sheets dynamically
        for sheet_name, df in dataframes.items():
            if sheet_name in ("Summary", "Datasets Navigation"):
                continue
            
            # Excel sheet names cannot exceed 31 characters
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])


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
    
    # 1. Get the dictionary of DataFrames
    dfs = get_datasets_dataframes(adf_json)
    
    # 2. Export them to Excel
    export_datasets_to_excel(dfs)