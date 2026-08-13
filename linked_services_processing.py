import os
import pandas as pd
import json
import yaml
from collections import defaultdict

def get_linked_services_dataframes(adf_json: dict) -> dict:
    """
    Parses the ADF JSON and returns a dictionary of Pandas DataFrames.
    Keys are the sheet/type names, values are the DataFrames.
    """
    type_counts = defaultdict(int)
    ls_grouped_by_type = {}
    
    # --- 1. Parse JSON into Python Dictionaries ---
    for ls_name, ls_data in adf_json["linked_services"].items():
        properties = ls_data["properties"]
        ls_type = properties["type"]
        
        type_counts[ls_type] += 1

        if "Linked Services Navigation" not in ls_grouped_by_type:
            ls_grouped_by_type["Linked Services Navigation"] = []
        ls_grouped_by_type["Linked Services Navigation"].append({"name": ls_name, "type": ls_type})

        row_data = {"linked_service_name": ls_name}
        for key, value in properties.items():
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
            if isinstance(value, (dict, list)):
                row_data[key] = json.dumps(value)
            else:
                row_data[key] = value
                
        if ls_type not in ls_grouped_by_type:
            ls_grouped_by_type[ls_type] = []
        ls_grouped_by_type[ls_type].append(row_data)

    # --- 2. Convert Dictionaries to DataFrames ---
    dataframes = {}
    
    # Build Summary DataFrame
    sorted_counts = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
    df_counts = pd.DataFrame(sorted_counts, columns=["Linked Service Type", "Count"])
    df_counts.loc[len(df_counts)] = ["TOTAL", df_counts["Count"].sum()]
    dataframes["Summary"] = df_counts
    
    # Build Individual Type DataFrames
    for ls_type, rows in ls_grouped_by_type.items():
        dataframes[ls_type] = pd.DataFrame(rows)
        
    return dataframes


def export_linked_services_to_excel(dataframes: dict, output_path: str = "_DATA_AND_OUTPUTS/presentable_outputs/Linked_services.xlsx"):
    """
    Takes a dictionary of DataFrames and writes them to an Excel workbook.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        # 1. Force Summary sheet to be first
        if "Summary" in dataframes:
            dataframes["Summary"].to_excel(writer, index=False, sheet_name="Summary")
            
        # 2. Force Linked Services Navigation to be second
        if "Linked Services Navigation" in dataframes:
            dataframes["Linked Services Navigation"].to_excel(writer, index=False, sheet_name="Linked Services Navigation")

        # 3. Write all remaining sheets dynamically
        for sheet_name, df in dataframes.items():
            if sheet_name in ("Summary", "Linked Services Navigation"):
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
    dfs = get_linked_services_dataframes(adf_json)
    
    # 2. Export them to Excel
    export_linked_services_to_excel(dfs)