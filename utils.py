import pandas as pd
import json
import yaml


def get_pipeline_names(adf_json: dict) -> list:
    pl_list = []
    for pl in adf_json["pipelines"]:
        try:
            fol_name = adf_json["pipelines"][pl]["folder"]["name"]
        except Exception as e:
            fol_name = ""
        pl_list.append([pl, fol_name])

    return pl_list


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
        scan_activity_types(adf_json["pipelines"][pl]["activities"], activities_type_set)
    
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

                    queries["Lookup"]["sql_reader_query"].append(query_text)
                except Exception as e:
                    sql_sp_name = i["source"]["sql_reader_stored_procedure_name"]
                    sql_sp_param = i["source"]["stored_procedure_parameters"]
                    queries["Lookup"]["sql_reader_stored_procedure"].append(
                        {
                            "sql_reader_stored_procedure_name": sql_sp_name,
                            "stored_procedure_parameters": sql_sp_param,
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


if __name__ == "__main__":

    # *****-------------*****
    # ---- Configuration ----
    # *****-------------*****
    with open("_DATA_AND_OUTPUTS/config.yaml", "r") as f:
        config_yaml = yaml.safe_load(f)

    json_path = config_yaml["full_extract_path"]

    with open(json_path, "r") as f:
        adf_json = json.load(f)

    # # ##################
    # # Get Pipeline Names
    # # ##################
    # df = pd.DataFrame(get_pipeline_names(adf_json), columns=['pipeline', 'folder'])
    # df.to_excel("_DATA_AND_OUTPUTS/presentable_outputs/pipelines.xlsx", index=False, sheet_name = "pipelines")

    # # ##################
    # # Print Trigger info
    # # ##################
    # print_trigger_info(adf_json)

    # # ##############################################################
    # # Get Activities(Lookup, SqlServerStoredProcedure, Script)
    # # ##############################################################
    # with open("_DATA_AND_OUTPUTS/lookup_sp_getvar.json", "w", encoding="utf-8") as f:
    #     json.dump(get_lookup_sp_var_activities(adf_json),f, indent=4)

    # ##########################
    # # Get queries and sp names
    # ##########################
    # with open("_DATA_AND_OUTPUTS/lookup_sp_getvar.json", "r") as f:
    #     lookup_sp_getvar_json = json.load(f)

    # with open("_DATA_AND_OUTPUTS/sp_and_queries.json", "w", encoding="utf-8") as f:
    #     json.dump(analyze_lookup(lookup_sp_getvar_json), f, indent=4)

    print(get_activity_type_set(adf_json))