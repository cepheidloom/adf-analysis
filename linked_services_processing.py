import pandas as pd
import json
import yaml
from collections import defaultdict

def export_linked_services_to_excel(adf_json: dict):
    # Tracking for summary sheet 
    type_counts = defaultdict(int)

    ls_grouped_by_type = {}
    for ls_name, ls_data in adf_json["linked_services"].items():
        properties = ls_data["properties"]
        ls_type = properties["type"]
        
        type_counts[ls_type] += 1

        if "Linked Services Navigation" not in ls_grouped_by_type:
            ls_grouped_by_type["Linked Services Navigation"] = []
        ls_grouped_by_type["Linked Services Navigation"].append({"name": ls_name, "type": ls_type})

        row_data = {"linked_service_name": ls_name}
        for key,value in properties.items():
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
            if isinstance(value,(dict, list)):
                row_data[key] = json.dumps(value)
            else:
                row_data[key] = value
        if ls_type not in ls_grouped_by_type:
            ls_grouped_by_type[ls_type] = []
        ls_grouped_by_type[ls_type].append(row_data)

    with pd.ExcelWriter("_DATA_AND_OUTPUTS/presentable_outputs/Linked_services.xlsx", engine='openpyxl') as writer:
        summary_sheet_name = "Summary"
        sorted_counts = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        df_counts = pd.DataFrame(sorted_counts, columns=["Linked Service Type", "Count"])

        df_counts.loc[len(df_counts)] = ["TOTAL", df_counts["Count"].sum()]
        df_counts.to_excel(writer, index=False, sheet_name=summary_sheet_name, startcol=0)

        # ==========================================
        # 2. WRITE INDIVIDUAL TYPE SHEETS
        # ==========================================
        for ls_type, rows in ls_grouped_by_type.items():
            df = pd.DataFrame(rows)
            df.fillna("None", inplace=True)
            sheet_name = ls_type[:31]
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
    export_linked_services_to_excel(adf_json)