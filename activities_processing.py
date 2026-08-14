import os
import pandas as pd
import json
import yaml


def parse_type_activities(activity_json: dict, pipeline_name: str, lineage: list) -> list:
    rows = []
    row_data = {"pipeline_name": pipeline_name}
    row_data["parent_path"] = ">".join(lineage) if lineage else ""
    row_data["immediate_parent"] = lineage[-1] if lineage else ""
    row_data["depth"] = len(lineage)

    activity_type = activity_json["type"]
    for key,value in activity_json.items():
        ################## Copy ##################
        if activity_type == "Copy" and key in ("inputs", "outputs"):
            row_data[f"{key}_dataset"] = value[0]["reference_name"]
            row_data[f"{key}_dataset_parameters"] = value[0]["parameters"]
        elif activity_type == "Copy" and key in ("source", "sink"):
            row_data[f"{key}_type"] = value["type"]
            row_data[key] = {k: v for k,v in value.items() if k!= "type"}
        ################## Copy ################## 
        elif key == "parameters":
            stacked = [f"• {k} => {v['value'] if isinstance(v, dict) else v}" for k,v in value.items()]
            row_data[key] = "\n".join(stacked)
        elif key in ("dataset", "linked_service_name", "pipeline"):
            row_data[key] = value["reference_name"]
        elif key in("stored_procedure_name") and isinstance(value, dict):
            row_data[key] = value["value"]
        elif key == "value" and isinstance(value, dict) and value["type"] == "Expression":
            row_data[key] = value["value"]
        elif key == "authentication" and isinstance(value, dict):
            # Drill down into password -> store to find the Linked Service
            password = value.get("password", {})
            if isinstance(password, dict):
                store = password.get("store", {})
                if isinstance(store, dict):
                    ls_name = store.get("reference_name", store.get("referenced_name"))
                    if ls_name:
                        row_data["auth_linked_service"] = ls_name
            # Format and retain the entire original authentication dictionary (redundancy kept)
            row_data[key] = "\n".join([f"{k}: {v}" for k, v in value.items()])
        elif key == "linked_services" and isinstance(value, list):
            # Extract all linked service names and join them with a newline
            extracted_ls = [ls.get("reference_name", ls.get("referenceName", "")) 
                for ls in value if isinstance(ls, dict)]
            # Filter out any empty strings just in case
            extracted_ls = [ls for ls in extracted_ls if ls]
            if extracted_ls:
                row_data["web_linked_services"] = "\n".join(extracted_ls)
        elif key in ("activities", "cases","default_activities","if_true_activities","if_false_activities"):
            continue
        else:
            row_data[key] = value

    rows.append(row_data)

    # --- walk into children (the "tree-walking" part) ---
    activity_type = activity_json["type"]
    new_lineage = lineage + [f"{activity_type}: {activity_json.get('name', '')}"]

    if activity_type == "Switch":
        for case in activity_json.get("cases", []):
            case_lineage = new_lineage[:-1] + [f"Switch case: {case.get('name', '')}"]
            for child in case.get("activities", []):
                rows.extend(parse_type_activities(child, pipeline_name, case_lineage))
        for child in activity_json.get("default_activities", []):
            rows.extend(parse_type_activities(child, pipeline_name, new_lineage))

    elif activity_type == "IfCondition":
        for child in activity_json.get("if_true_activities", []):
            rows.extend(parse_type_activities(child, pipeline_name, new_lineage))
        for child in activity_json.get("if_false_activities", []):
            rows.extend(parse_type_activities(child, pipeline_name, new_lineage))

    elif activity_type in ("ForEach", "Until"):
            for child in activity_json.get("activities", []):
                rows.extend(parse_type_activities(child, pipeline_name, new_lineage))

    return rows    
    
def build_navigation_dataframe(master_activity_list: list) -> pd.DataFrame:
    nav_rows = []
    
    for row in master_activity_list:
        base_info = {
            "Pipeline Name": row.get("pipeline_name", ""),
            "Full Path": row.get("parent_path", ""),
            "Immediate Parent": row.get("immediate_parent", ""),
            "Depth": row.get("depth", 0),
            "Activity Name": row.get("name", "Unknown"),
            "Activity Type": row.get("type", "Unknown")
        }
        
        datasets = set()
        linked_services = set()
        
        if "inputs_dataset" in row: datasets.add(row["inputs_dataset"])
        if "outputs_dataset" in row: datasets.add(row["outputs_dataset"])
        if "dataset" in row: datasets.add(row["dataset"])
        
        if "linked_service_name" in row: linked_services.add(row["linked_service_name"])
        if "auth_linked_service" in row: linked_services.add(row["auth_linked_service"])
        
        if "web_linked_services" in row and row["web_linked_services"]:
            for ls in row["web_linked_services"].split("\n"):
                if ls.strip():
                    linked_services.add(ls.strip())
                    
        if not datasets and not linked_services:
            nav_rows.append({**base_info, "Dataset": None, "Linked Service": None})
        else:
            for ds in datasets:
                nav_rows.append({**base_info, "Dataset": ds, "Linked Service": None})
            for ls in linked_services:
                nav_rows.append({**base_info, "Dataset": None, "Linked Service": ls})
                
    return pd.DataFrame(nav_rows).drop_duplicates()


def get_activities_dataframes(adf_json: dict) -> dict:
    """
    Parses the ADF JSON and returns a dictionary of Pandas DataFrames.
    Keys are the sheet/type names, values are the DataFrames.
    """
    activity_grouped_by_type = {}
    master_activity_list = []
    pipeline_summary_rows = []
    
    for pl_name, pl_content in adf_json["pipelines"].items():
        # --- Extract top-level pipeline fields ---
        pl_row = {"pipeline_name": pl_name}
        for key, value in pl_content.items():
            if key not in ("activities", "id", "name", "type", "etag"):
                if key == "folder":
                    pl_row[key] = value["name"]
                    continue
                elif key in ("parameters", "variables") and isinstance(value, dict):
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
                    pl_row[key] = "\n".join(formatted_params)
                    continue
                pl_row[key] = value

        pipeline_summary_rows.append(pl_row)

        for acti in pl_content["activities"]:
            all_rows = parse_type_activities(acti, pl_name, [])
            master_activity_list.extend(all_rows)
            
            for row in all_rows:
                activity_type = row["type"]
                activity_grouped_by_type.setdefault(activity_type, []).append(row)

    # --- Generate Navigation DataFrames ---
    nav_df = build_navigation_dataframe(master_activity_list)
    
    merged_references = (
        nav_df.dropna(subset=["Dataset", "Linked Service"], how="all")
        [["Pipeline Name", "Dataset", "Linked Service"]]
        .drop_duplicates()
        .sort_values(["Pipeline Name"])
    )
    clean_nav_df = nav_df.drop(columns=["Dataset", "Linked Service"]).drop_duplicates()

    # --- Pack everything into a Dictionary ---
    dataframes = {}
    dataframes["pipeline_summary"] = pd.DataFrame(pipeline_summary_rows)
    dataframes["pipeline_activity_navigation"] = clean_nav_df
    dataframes["pipeline_references"] = merged_references

    for acti_types, acti_rows in activity_grouped_by_type.items():
        dataframes[acti_types] = pd.DataFrame(acti_rows)

    return dataframes


def export_activities_to_excel(dataframes: dict, output_path: str = "_DATA_AND_OUTPUTS/presentable_outputs/Activities.xlsx"):
    """
    Takes a dictionary of DataFrames and writes them to an Excel workbook with specific sheet ordering.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        
        # 1. Force explicit core sheets in order
        explicit_sheets = ["pipeline_summary", "pipeline_activity_navigation", "pipeline_references"]
        
        for sheet in explicit_sheets:
            if sheet in dataframes:
                dataframes[sheet].to_excel(writer, index=False, sheet_name=sheet)

        # 2. Write all individual activity sheets dynamically
        for sheet_name, df in dataframes.items():
            if sheet_name in explicit_sheets:
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
    dfs = get_activities_dataframes(adf_json)
    
    # 2. Export them to Excel
    export_activities_to_excel(dfs)