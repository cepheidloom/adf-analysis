import os
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
    print(f"Stats for factory:", adf_json["factory_name"])
    print(f"Total Linked Services:", len(adf_json["linked_services"]))
    print(f"Total Datasets:", len(adf_json["datasets"]))
    print(f"Total Pipelines:", len(adf_json["pipelines"]))
    print(f"Total Data Flows:", len(adf_json["data_flows"]))
    print(f"Total Triggers:", len(adf_json["triggers"]))
    print(f"Total Integration Runtimes:", len(adf_json["integration_runtimes"]))


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
        os.makedirs("_DATA_AND_OUTPUTS/presentable_outputs", exist_ok=True)
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


if __name__ == "__main__":

    # *****-------------*****
    # ---- Configuration ----
    # *****-------------*****
    os.makedirs("_DATA_AND_OUTPUTS", exist_ok=True)
    with open("_DATA_AND_OUTPUTS/config.yaml", "r") as f:
        config_yaml = yaml.safe_load(f)

    json_path = config_yaml["full_extract_path"]

    with open(json_path, "r") as f:
        adf_json = json.load(f)

    os.makedirs("_DATA_AND_OUTPUTS", exist_ok=True)

    # ##############################################################
    # Get Activities(Lookup, SqlServerStoredProcedure, Script)
    # ##############################################################
    with open("_DATA_AND_OUTPUTS/lookup_sp_getvar.json", "w", encoding="utf-8") as f:
        json.dump(get_lookup_sp_var_activities(adf_json), f, indent=4)

    ##########################
    # Get queries and sp names
    ##########################
    with open("_DATA_AND_OUTPUTS/lookup_sp_getvar.json", "r") as f:
        lookup_sp_getvar_json = json.load(f)

    with open("_DATA_AND_OUTPUTS/sp_and_queries.json", "w", encoding="utf-8") as f:
        json.dump(analyze_lookup(lookup_sp_getvar_json), f, indent=4)

    ################################################
    #######@@@ Analyze Activity Instances @@@#######
    ################################################
    # # Inspect raw fields of a specific activity type
    # # Useful for understanding what keys/subfields a
    # # particular activity type exposes in your ADF extract.
    
    # # Change "Copy" to any activity type you want to inspect
    # # (e.g. "Lookup", "Script", "ForEach", "Switch", etc.)
    
    # # top_level_fields → all keys present on that activity
    # # subfields_set    → keys inside a chosen nested field (e.g. "source")

    # top_level_fields = set()
    # subfields_set = set()
    # values_set = set()
    # for act in gather_all_instances(adf_json, "Copy"):
    #     top_level_fields.update(act.keys())
    #     for key, item in act.items():
    #         if key == "source": #and isinstance(item, dict): # change to any nested field you want to drill into
    #             # values_set.add(["type"])
    #             subfields_set.update(item.keys())
    # # print(top_level_fields)
    # print(subfields_set)
    # print(values_set)