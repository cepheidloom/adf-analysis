import pandas as pd
import json
import yaml
from collections import defaultdict


def export_datasets_to_excel(adf_json: dict):
    total_dataset_count = len(adf_json["datasets"])
    top_level_fields = set()
    property_level_fields = set()
    type_counts = defaultdict(int)

    ds_grouped_by_type = {}
    for ds_name, ds_content in adf_json["datasets"].items():
        top_level_fields.update(ds_content.keys())

        properties = ds_content["properties"]
        ds_type = properties["type"]

        type_counts[ds_type] += 1
        property_level_fields.update(properties.keys())

        if "Datasets Navigation" not in ds_grouped_by_type:
            ds_grouped_by_type["Datasets Navigation"] = []
        ds_grouped_by_type["Datasets Navigation"].append({"name": ds_name, "type": ds_type})
        
        row_data = {"dataset_name": ds_name}
        for key,value in properties.items():
            if isinstance(value, (dict,list)):
                if key=="linked_service_name":
                    row_data[key] = value["reference_name"]
                    continue
                if key=="folder":
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
                row_data[key] = json.dumps(value)
            else:
                row_data[key] = value
        if ds_type not in ds_grouped_by_type:
            ds_grouped_by_type[ds_type] = []
        ds_grouped_by_type[ds_type].append(row_data)

    with pd.ExcelWriter("_DATA_AND_OUTPUTS/presentable_outputs/Datasets.xlsx", engine='openpyxl') as writer:
        summary_sheet_name = "Summary"
        sorted_counts = sorted(type_counts.items(), key=lambda x:x[1], reverse=True)
        df_counts = pd.DataFrame(sorted_counts, columns=["Dataset Type", "Count"])
        df_counts.loc[len(df_counts)] = ["TOTAL", df_counts["Count"].sum()]
        df_top = pd.DataFrame(sorted(list(top_level_fields)), columns=["Top Level Fields"])
        df_prop = pd.DataFrame(sorted(list(property_level_fields)), columns=["Property Level Fields"])

        df_counts.to_excel(writer, index=False, sheet_name=summary_sheet_name, startcol=0)
        df_top.to_excel(writer, index=False, sheet_name=summary_sheet_name, startcol=3)
        df_prop.to_excel(writer, index=False, sheet_name=summary_sheet_name, startcol=5)

        worksheet = writer.sheets[summary_sheet_name]
        for col in worksheet.columns:
            max_length = 0
            column_letter = col[0].column_letter
            for cell in col:
                try:
                    if cell.value and len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except Exception:
                    pass
            worksheet.column_dimensions[column_letter].width = max_length + 2

            # ==========================================
        # 2. WRITE INDIVIDUAL TYPE SHEETS
        # ==========================================
        for ds_type, rows in ds_grouped_by_type.items():
            df = pd.DataFrame(rows)
            df.fillna("None", inplace=True)
            sheet_name = ds_type[:31]
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
    export_datasets_to_excel(adf_json)