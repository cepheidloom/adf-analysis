import pandas as pd
import json
import yaml
from collections import defaultdict

#########################################################################################
#################################@@@ PRINT FUNCTIONS @@@#################################
#########################################################################################

def print_linked_service_analysis(adf_json: dict):
    # count = 0
    set_type = dict()
    for ls in adf_json["linked_services"]:
        # print(adf_json["linked_services"][ls]["properties"]["type"])
        try:
            set_type[adf_json["linked_services"][ls]["properties"]["type"]] += 1
        except Exception as e:
            set_type[adf_json["linked_services"][ls]["properties"]["type"]] = 1
    list_type = sorted(set_type.items(), key=lambda item: item[1], reverse=True)
    for key,value in list_type:
        print( key,"-->", value)
    
def print_linked_service_type_properties(adf_json: dict):
    top_level_fields = set()
    property_level_fields = set()
    for ls in adf_json["linked_services"]:
        for fie in adf_json["linked_services"][ls]:
            top_level_fields.add(fie)
        for ty_fie in adf_json["linked_services"][ls]["properties"]:
                property_level_fields.add(ty_fie)
    print("*"*10, "Linked Services Top level fields", "*"*10)
    for i in top_level_fields: print(i)
    print("-"*70,"\n"+"-"*70)
    print("*"*10, "Linked Services Property level fields","*"*10)
    for i in property_level_fields: print(i)

def print_basic_information_of_factory(adf_json: dict):
    print(f"Stats for factory: {adf_json["factory_name"]}")
    print(f"Total Linked Services: {len(adf_json["linked_services"])}")
    print(f"Total Datasets: {len(adf_json["datasets"])}")
    print(f"Total Pipelines: {len(adf_json["pipelines"])}")
    print(f"Total Data Flows: {len(adf_json["data_flows"])}")
    print(f"Total Triggers: {len(adf_json["triggers"])}")
    print(f"Total Integration Runtimes: {len(adf_json["integration_runtimes"])}")


def print_trigger_info(adf_json: dict):
    print(len(adf_json["triggers"]))
    for trigger in adf_json["triggers"]:
        if adf_json["triggers"][trigger]["properties"]["runtime_state"] == "Started":
            print(
                trigger,
                "---->",
                adf_json["triggers"][trigger]["properties"]["recurrence"]["frequency"],
                "---->",
                adf_json["triggers"][trigger]["properties"]["runtime_state"],
                "---->",
                len(adf_json["triggers"][trigger]["properties"]["pipelines"]),
            )

    print("")
    for trigger in adf_json["triggers"]:
        if adf_json["triggers"][trigger]["properties"]["runtime_state"] == "Stopped":
            print(
                trigger,
                "---->",
                adf_json["triggers"][trigger]["properties"]["recurrence"]["frequency"],
                "---->",
                adf_json["triggers"][trigger]["properties"]["runtime_state"],
                "---->",
                len(adf_json["triggers"][trigger]["properties"]["pipelines"]),
            )
#########################################################################################
#################################@@@ END print functions END @@@#########################
#########################################################################################

   
def export_linked_services_to_excel(adf_json: dict):
    # Tracking for summary sheet
    top_level_fields = set() 
    property_level_fields = set() 
    type_counts = defaultdict(int)

    ls_grouped_by_type = {}
    for ls_name, ls_data in adf_json["linked_services"].items():
        for field in ls_data:
            top_level_fields.add(field)

        properties = ls_data["properties"]
        ls_type = properties["type"]
        
        type_counts[ls_type] += 1

        row_data = {"linked_service_name": ls_name}
        for key,value in properties.items():
            property_level_fields.add(key)
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
        for ls_type, rows in ls_grouped_by_type.items():
            df = pd.DataFrame(rows)
            df.fillna("None", inplace=True)
            sheet_name = ls_type[:31]
            df.to_excel(writer, index=False, sheet_name=sheet_name)


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

def get_pipeline_names(adf_json: dict, print_or_output: bool) -> list:
    pl_list = []
    for pl in adf_json["pipelines"]:
        try:
            fol_name = adf_json["pipelines"][pl]["folder"]["name"]
        except Exception as e:
            fol_name = ""
        pl_list.append([pl, fol_name])
    
    if print_or_output:
        for i in pl_list: print(i)
    else:
        df = pd.DataFrame(pl_list, columns=['pipeline', 'folder'])
        df.to_excel("_DATA_AND_OUTPUTS/presentable_outputs/pipelines.xlsx", index=False, sheet_name = "pipelines")




def scan_activity_types(act_lis: list, output_set: set):
    for actv in act_lis:
        if actv["type"] == "Switch":
            try:
                for activs in actv["cases"]:
                    scan_activity_types(activs["activities"], output_set)
            except Exception as e:
                pass
            try:
                scan_activity_types(actv["default_activities"], output_set)
            except Exception as e:
                pass

        elif actv["type"] == "IfCondition":
            try:
                scan_activity_types(actv["if_true_activities"], output_set)
            except Exception as e:
                pass
            try:
                scan_activity_types(actv["if_false_activities"], output_set)
            except Exception as e:
                pass

        elif actv["type"] == "ForEach" or actv["type"] == "Until":
            scan_activity_types(actv["activities"], output_set)

        output_set.add(actv["type"])


def get_activity_type_set(adf_json: dict) -> set:

    activities_type_set = set()
    for pl in adf_json["pipelines"]:
        scan_activity_types(
            adf_json["pipelines"][pl]["activities"], activities_type_set
        )

    return activities_type_set


def scan_activities(act_lis: list, output_list: list):
    for actv in act_lis:
        if actv["type"] in ["Lookup", "SqlServerStoredProcedure", "Script"]:
            output_list.append(actv)

        if actv["type"] == "Switch":
            try:
                for activs in actv["cases"]:
                    scan_activities(activs["activities"], output_list)
            except Exception as e:
                pass
            try:
                scan_activities(actv["default_activities"], output_list)
            except Exception as e:
                pass

        elif actv["type"] == "IfCondition":
            try:
                scan_activities(actv["if_true_activities"], output_list)
            except Exception as e:
                pass
            try:
                scan_activities(actv["if_false_activities"], output_list)
            except Exception as e:
                pass

        elif actv["type"] == "ForEach" or actv["type"] == "Until":
            scan_activities(actv["activities"], output_list)


def get_lookup_sp_var_activities(adf_json: dict) -> dict:

    activities_list = []
    for pl in adf_json["pipelines"]:
        scan_activities(adf_json["pipelines"][pl]["activities"], activities_list)

    activities_dict = {"lookups": activities_list}
    return activities_dict


def analyze_lookup(lookup_sp_getvar_json: dict) -> dict:
    queries = {
        "Lookup": {
            "sql_reader_query": [],
            "sql_reader_stored_procedure": [],
            "ParquetSource": [],
            "JsonSource": [],
            "DelimitedTextSource": [],
        },
        "SqlServerStoredProcedure": [],
        "Scripts": [],
    }
    for i in lookup_sp_getvar_json["lookups"]:
        if i["type"] == "Lookup":

            if i["source"]["type"] == "AzureSqlSource":
                try:
                    sql_query = i["source"]["sql_reader_query"]
                    if isinstance(sql_query, dict):
                        query_text = sql_query["value"]
                    else:
                        query_text = sql_query

                    queries["Lookup"]["sql_reader_query"].append(
                        {"sql_reader_query": query_text,
                         "dataset_reference_name": i["dataset"]["reference_name"]
                         }
                    )
                except Exception as e:
                    sql_sp_name = i["source"]["sql_reader_stored_procedure_name"]
                    sql_sp_param = i["source"]["stored_procedure_parameters"]
                    queries["Lookup"]["sql_reader_stored_procedure"].append(
                        {
                            "sql_reader_stored_procedure_name": sql_sp_name,
                            "stored_procedure_parameters": sql_sp_param,
                            "dataset_reference_name": i["dataset"]["reference_name"],
                        }
                    )

            elif i["source"]["type"] == "ParquetSource":
                queries["Lookup"]["ParquetSource"].append(
                    {"name": i["name"], "dataset": i["dataset"]}
                )
            elif i["source"]["type"] == "JsonSource":
                queries["Lookup"]["JsonSource"].append(
                    {
                        "name": i["name"],
                        "dataset": i["dataset"],
                        "store_settings_type": i["source"]["store_settings"]["type"],
                    }
                )
            elif i["source"]["type"] == "DelimitedTextSource":
                queries["Lookup"]["DelimitedTextSource"].append(
                    {
                        "name": i["name"],
                        "dataset": i["dataset"],
                        "store_settings_type": i["source"]["store_settings"]["type"],
                    }
                )

        elif i["type"] == "SqlServerStoredProcedure":
            sp_name = i["stored_procedure_name"]
            sp_params = i.get("stored_procedure_parameters")
            queries["SqlServerStoredProcedure"].append(
                {
                    "stored_procedure_name": sp_name,
                    "stored_procedure_parameters": sp_params,
                    "linked_service_name": i["linked_service_name"]["reference_name"],
                }
            )

        elif i["type"] == "Script":
            script_linked_service = i["linked_service_name"]["reference_name"]
            script_list = []
            for scr in i["scripts"]:
                script_text_field = scr["text"]
                if isinstance(script_text_field, dict):
                    script_text = script_text_field["value"]
                else:
                    script_text = script_text_field

                script_type = scr["type"]
                script_list.append({"text": script_text, "type": script_type})
            queries["Scripts"].append(
                {"scripts": script_list, "linked_service_name": script_linked_service}
            )

    return queries


def parse_type_activities(activity_json: dict) -> dict:
    row_data = {}
    if activity_json["type"] == "Switch":
        try:
            for case in activity_json["cases"]:
                for activity in case["activities"]:
                    parse_type_activities(activity)
        except Exception as e:
            pass
        try:
            for activity in activity_json["default_activities"]:
                parse_type_activities(activity)
        except Exception as e:
            pass

    elif activity_json["type"] == "IfCondition":
        try:
            for activity in activity_json["if_true_activities"]:
                parse_type_activities(activity)
        except Exception as e:
            pass
        try:
            for activity in activity_json["if_false_activities"]:
                parse_type_activities(activity)
        except Exception as e:
            pass

    elif activity_json["type"] == "ForEach" or activity_json["type"] == "Until":
            for activity in activity_json["activities"]:
                parse_type_activities(activity)
    
    
    for key,value in activity_json.items():
        if key == "parameters":
            stacked_params = []
            for pm_name, pm_val in value.items():
                if isinstance(pm_val,dict):
                    clean_val = pm_val["value"]
                else:
                    clean_val = pm_val
                stacked_params.append(f"{pm_name}: {clean_val}")
            row_data[key] = "\n".join(stacked_params)
            continue
        if key == "dataset":
            row_data[key] = value["reference_name"]
            continue
        if key == "linked_service_name":
            row_data[key] = value["reference_name"]
            continue
        if activity_json["type"] == "ExecutePipeline":
            if key== "pipeline":
                row_data[key] = value["reference_name"]
                continue
        row_data[key] = value
    return row_data


def activity_analysis(adf_json: dict):
    # top_level_fields = set()
    # activity_fields = set()
    # activity_types = set()
    activity_grouped_by_type = {}
    for pl_name, pl_content in adf_json["pipelines"].items():
        # top_level_fields.update(pl_content.keys())
        for acti in pl_content["activities"]:
            activity_type = acti["type"]
            # activity_fields.update(acti.keys())
            # activity_types.add(acti["type"])
            row_data = {"pipeline_name": pl_name}
            row_data.update(parse_type_activities(acti))
            if activity_type not in activity_grouped_by_type:
                activity_grouped_by_type[activity_type] = []
            activity_grouped_by_type[activity_type].append(row_data)

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

    # # ##############################################################
    # # Get Activities(Lookup, SqlServerStoredProcedure, Script)
    # # ##############################################################
    # with open("_DATA_AND_OUTPUTS/lookup_sp_getvar.json", "w", encoding="utf-8") as f:
    #     json.dump(get_lookup_sp_var_activities(adf_json), f, indent=4)

    # ##########################
    # # Get queries and sp names
    # ##########################
    # with open("_DATA_AND_OUTPUTS/lookup_sp_getvar.json", "r") as f:
    #     lookup_sp_getvar_json = json.load(f)

    # with open("_DATA_AND_OUTPUTS/sp_and_queries.json", "w", encoding="utf-8") as f:
    #     json.dump(analyze_lookup(lookup_sp_getvar_json), f, indent=4)

    activity_analysis(adf_json)