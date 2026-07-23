import json
import pandas as pd
import yaml
from collections import defaultdict
from datetime import datetime

with open("_DATA_AND_OUTPUTS/config.yaml", "r") as f:
        config_yaml = yaml.safe_load(f)

INPUT_FILE = config_yaml["jsonl_input_file"]
OUTPUT_FILE = "_DATA_AND_OUTPUTS/presentable_outputs/pipeline_parameters.xlsx"


def normalize_value(val):
    """Recursively strip expression-wrapper dicts down to just their 'value'."""
    if isinstance(val, dict):
        if "value" in val:
            return normalize_value(val["value"])
        normalized = {k: normalize_value(v) for k, v in val.items()}
        return json.dumps(normalized, sort_keys=True, default=str)
    if isinstance(val, list):
        normalized = [normalize_value(v) for v in val]
        return json.dumps(normalized, default=str)
    return val


def load_runs(path):
    runs = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip().strip("\x00")
            if not line:
                continue
            try:
                runs.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Skipping bad line {i}: {e}")
    return runs


def build_unpivoted_parameters(runs):
    """Produces exactly what was in the first sheet (Pipeline_Parameters), untouched."""
    pipeline_data = defaultdict(lambda: {"params": defaultdict(set)})

    for run in runs:
        pipeline_name = run.get("pipeline_name", "UNKNOWN")
        params = run.get("pipeline_parameters") or {}
        for param_name, param_val in params.items():
            normalized = normalize_value(param_val)
            pipeline_data[pipeline_name]["params"][param_name].add(normalized)

    unpivoted_rows = []
    for pipeline_name, info in pipeline_data.items():
        for param_name, value_set in sorted(info["params"].items()):
            for val in sorted(value_set):
                unpivoted_rows.append({
                    "Pipeline Name": pipeline_name,
                    "Parameter Name": param_name,
                    "Parameter Value": str(val)
                })
    return unpivoted_rows


def build_pipeline_summary(runs):
    """Produces the new second sheet: 1 row per pipeline, summary stats, param names only."""
    pipeline_data = defaultdict(lambda: {
        "total_runs": 0, "succeeded": 0, "failed": 0, "cancelled": 0,
        "earliest": None, "latest": None,
        "param_names": set()
    })

    for run in runs:
        name = run.get("pipeline_name", "Unknown")
        p = pipeline_data[name]
        p["total_runs"] += 1

        status = (run.get("status") or "").lower()
        if status == "succeeded":       p["succeeded"] += 1
        elif status == "failed":        p["failed"] += 1
        elif status == "cancelled":     p["cancelled"] += 1

        run_start = run.get("run_start")
        if run_start and run_start != "None":
            try:
                dt = datetime.fromisoformat(run_start.replace("Z", "+00:00"))
                if p["earliest"] is None or dt < p["earliest"]: p["earliest"] = dt
                if p["latest"] is None or dt > p["latest"]:     p["latest"] = dt
            except: pass

        params = run.get("pipeline_parameters") or {}
        for param_name in params.keys():
            p["param_names"].add(param_name)

    rows = []
    for name, p in sorted(pipeline_data.items(), key=lambda x: x[1]["total_runs"], reverse=True):
        rows.append({
            "Pipeline Name":            name,
            "Total Runs":               p["total_runs"],
            "Succeeded":                p["succeeded"],
            "Failed":                   p["failed"],
            "Cancelled":                p["cancelled"],
            "Success Rate %":           round((p["succeeded"] / p["total_runs"]) * 100, 1) if p["total_runs"] else 0,
            "Earliest Run":             p["earliest"].strftime("%Y-%m-%d %H:%M") if p["earliest"] else "",
            "Latest Run":               p["latest"].strftime("%Y-%m-%d %H:%M") if p["latest"] else "",
            "Pipeline Parameters":      ", ".join(sorted(p["param_names"]))
        })
    return rows


def build_all_runs(runs):
    """Integrates the commented code to output 1 row per run."""
    rows = []
    for run in runs:
        params = run.get("pipeline_parameters") or {}
        rows.append({
            "Pipeline Name":    run.get("pipeline_name", "Unknown"),
            "Run ID":           run.get("run_id", ""),
            "Status":           run.get("status", ""),
            "Run Start":        run.get("run_start", ""),
            "Run End":          run.get("run_end", ""),
            "Duration (ms)":    run.get("duration_ms"),
            "Invoked By Type":  (run.get("invoked_by") or {}).get("invoked_by_type", ""),
            "Parameter Keys":   ", ".join(params.keys()) if params else "",
            "Parameter Values": " | ".join(f"{k}={v}" for k, v in params.items()) if params else "",
            "Raw Parameters":   json.dumps(params) if params else "",
        })
    return rows


if __name__ == "__main__":
    runs = load_runs(INPUT_FILE)
    
    # Build datasets
    unpivoted_rows = build_unpivoted_parameters(runs)
    summary_rows = build_pipeline_summary(runs)
    # all_runs_rows = build_all_runs(runs) #uncomment this line and below 3 to create runwise excel.

    # Create DataFrames
    df_unpivoted = pd.DataFrame(unpivoted_rows)
    df_summary = pd.DataFrame(summary_rows)
    # df_all_runs = pd.DataFrame(all_runs_rows)

    # Write to Excel
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        df_unpivoted.to_excel(writer, index=False, sheet_name="Pipeline_Parameters")
        df_summary.to_excel(writer, index=False, sheet_name="Pipeline_Summary")
        # df_all_runs.to_excel(writer, index=False, sheet_name="All_Pipeline_Runs")

    print(f"Wrote {len(unpivoted_rows)} unpivoted params, {len(summary_rows)} summary pipelines to {OUTPUT_FILE}")
    # print(f"Wrote {len(all_runs_rows)} individual runs to {OUTPUT_FILE}")