import pandas as pd
import json
import yaml
# from collections import defaultdict


def collect_activities_by_type(activity_json: dict, target_type: str, matches: list):
    """Walks the full nested tree and collects every activity dict matching target_type."""
    if activity_json.get("type") == target_type:
        matches.append(activity_json)

    activity_type = activity_json.get("type")

    if activity_type == "Switch":
        for case in activity_json.get("cases", []):
            for child in case.get("activities", []):
                collect_activities_by_type(child, target_type, matches)
        for child in activity_json.get("default_activities", []):
            collect_activities_by_type(child, target_type, matches)

    elif activity_type == "IfCondition":
        for child in activity_json.get("if_true_activities", []):
            collect_activities_by_type(child, target_type, matches)
        for child in activity_json.get("if_false_activities", []):
            collect_activities_by_type(child, target_type, matches)

    elif activity_type in ("ForEach", "Until"):
        for child in activity_json.get("activities", []):
            collect_activities_by_type(child, target_type, matches)

    return matches


def gather_all_instances(adf_json: dict, target_type: str) -> list:
    """Runs the collector across every pipeline in the ADF extract."""
    matches = []
    for pl_name, pl_content in adf_json["pipelines"].items():
        for acti in pl_content["activities"]:
            collect_activities_by_type(acti, target_type, matches)
    return matches


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
            stacked = [f"{k}: {v['value'] if isinstance(v, dict) else v}" for k,v in value.items()]
            row_data[key] = "\n".join(stacked)
        elif key in ("dataset", "linked_service_name", "pipeline"):
            row_data[key] = value["reference_name"]
        elif key in("stored_procedure_name") and isinstance(value, dict):
            row_data[key] = value["value"]
        elif key == "value" and isinstance(value, dict) and value["type"] == "Expression":
            row_data[key] = value["value"]
        elif key == "dataset" and isinstance(value, dict):
            row_data["dataset"] = value["reference_name"]
            row_data["dataset_parameters"] = value["parameters"]
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
    


def activity_analysis(adf_json: dict):
    # top_level_fields = set()
    activity_grouped_by_type = {}
    for pl_name, pl_content in adf_json["pipelines"].items():
        # top_level_fields.update(pl_content.keys())
        for acti in pl_content["activities"]:
            all_rows = parse_type_activities(acti, pl_name, [])
            for row in all_rows:
                activity_type = row["type"]
                activity_grouped_by_type.setdefault(activity_type, []).append(row)
               
    with pd.ExcelWriter("_DATA_AND_OUTPUTS/presentable_outputs/activities.xlsx", engine='openpyxl') as writer:
        for acti_types,acti_rows in activity_grouped_by_type.items():
            df = pd.DataFrame(acti_rows)
            sheet_name = acti_types[:31]
            df.to_excel(writer, index=False, sheet_name=sheet_name)


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
    #######@@@ Function Call @@@#######
    ###################################
    activity_analysis(adf_json)

    ################################################
    #######@@@ Analyze Activity Instances @@@#######
    ################################################
    # top_level_fields = set()
    # subfields_set = set()
    # values_set = set()
    # for act in gather_all_instances(adf_json, "Copy"):
    #     top_level_fields.update(act.keys())
    #     for key, item in act.items():
    #         if key == "source": #and isinstance(item, dict):
    #             # values_set.add(["type"])
    #             subfields_set.update(item.keys())
    # # print(top_level_fields)
    # print(subfields_set)
    # print(values_set)