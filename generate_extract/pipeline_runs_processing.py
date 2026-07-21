# import json
# from collections import defaultdict
# from datetime import datetime
# import pandas as pd
# from openpyxl import load_workbook
# from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
# from openpyxl.utils import get_column_letter

# JSONL_FILE = "_DATA_AND_OUTPUTS/runs_data/21May-7July__shell-32-eun-adf-okjtarmveaftjxpeuzj_runs.jsonl"
# OUTPUT_FILE = "pipeline_analysis.xlsx"

# # ─────────────────────────────────────────────
# # READER
# # ─────────────────────────────────────────────

# def read_jsonl(filepath):
#     runs = []
#     with open(filepath, encoding="utf-8") as f:
#         # for line in f:
#         #     line = line.strip()
#         #     if line:
#         #         runs.append(json.loads(line))
#         for i, line in enumerate(f, start=1):
#                 # line = line.strip().strip("\x00")
#                 if not line:
#                     continue
#                 try:
#                     runs.append(json.loads(line))
#                 except json.JSONDecodeError as e:
#                     print(f"Skipping bad line {i}: {e}")
#     print(f"Loaded {len(runs)} runs from {filepath}")
#     return runs


# # ─────────────────────────────────────────────
# # DATA BUILDERS
# # ─────────────────────────────────────────────

# def build_distribution(runs):
#     pipeline_data = defaultdict(lambda: {
#         "total": 0, "succeeded": 0, "failed": 0,
#         "cancelled": 0, "other": 0,
#         "earliest": None, "latest": None,
#         "invoked_by_types": defaultdict(int),
#         "has_copy_activities": 0,
#         "total_rows_read": 0, "total_rows_written": 0,
#     })

#     for run in runs:
#         name = run.get("pipeline_name", "Unknown")
#         p = pipeline_data[name]
#         p["total"] += 1

#         status = (run.get("status") or "").lower()
#         if status == "succeeded":       p["succeeded"] += 1
#         elif status == "failed":        p["failed"] += 1
#         elif status == "cancelled":     p["cancelled"] += 1
#         else:                           p["other"] += 1

#         run_start = run.get("run_start")
#         if run_start and run_start != "None":
#             try:
#                 dt = datetime.fromisoformat(run_start.replace("Z", "+00:00"))
#                 if p["earliest"] is None or dt < p["earliest"]: p["earliest"] = dt
#                 if p["latest"] is None or dt > p["latest"]:     p["latest"] = dt
#             except: pass

#         invoked_type = (run.get("invoked_by") or {}).get("invoked_by_type") or "Unknown"
#         p["invoked_by_types"][invoked_type] += 1

#         for act in run.get("copy_activities", []):
#             p["has_copy_activities"] += 1
#             p["total_rows_read"]    += act.get("rows_read") or 0
#             p["total_rows_written"] += act.get("rows_written") or 0

#     rows = []
#     for name, p in sorted(pipeline_data.items(), key=lambda x: x[1]["total"], reverse=True):
#         rows.append({
#             "Pipeline Name":            name,
#             "Total Runs":               p["total"],
#             "Succeeded":                p["succeeded"],
#             "Failed":                   p["failed"],
#             "Cancelled":                p["cancelled"],
#             "Other":                    p["other"],
#             "Success Rate %":           round((p["succeeded"] / p["total"]) * 100, 1) if p["total"] else 0,
#             "Earliest Run":             p["earliest"].strftime("%Y-%m-%d %H:%M") if p["earliest"] else "",
#             "Latest Run":               p["latest"].strftime("%Y-%m-%d %H:%M") if p["latest"] else "",
#             "Runs With Copy Activity":  p["has_copy_activities"],
#             "Total Rows Read":          p["total_rows_read"],
#             "Total Rows Written":       p["total_rows_written"],
#             "Invoked By":               ", ".join(f"{k}: {v}" for k, v in p["invoked_by_types"].items()),
#         })
#     return pd.DataFrame(rows)


# def build_pipeline_parameters(runs):
#     rows = []
#     for run in runs:
#         params = run.get("pipeline_parameters") or {}
#         rows.append({
#             "Pipeline Name":    run.get("pipeline_name", "Unknown"),
#             "Run ID":           run.get("run_id", ""),
#             "Status":           run.get("status", ""),
#             "Run Start":        run.get("run_start", ""),
#             "Run End":          run.get("run_end", ""),
#             "Duration (ms)":    run.get("duration_ms"),
#             "Invoked By Type":  (run.get("invoked_by") or {}).get("invoked_by_type", ""),
#             "Invoked By Name":  (run.get("invoked_by") or {}).get("name", ""),
#             "Parameter Keys":   ", ".join(params.keys()) if params else "",
#             "Parameter Values": " | ".join(f"{k}={v}" for k, v in params.items()) if params else "",
#             "Raw Parameters":   json.dumps(params) if params else "",
#         })
#     return pd.DataFrame(rows)


# def build_copy_activity_details(runs):
#     rows = []
#     for run in runs:
#         pipeline_name   = run.get("pipeline_name", "Unknown")
#         run_id          = run.get("run_id", "")
#         run_status      = run.get("status", "")
#         run_start       = run.get("run_start", "")
#         pipeline_params = run.get("pipeline_parameters") or {}

#         for act in run.get("copy_activities", []):
#             source_datasets = act.get("source_datasets") or []
#             sink_datasets   = act.get("sink_datasets") or []
#             source_exec     = act.get("source_execution") or {}
#             sink_exec       = act.get("sink_execution") or {}

#             # Flatten source info
#             src = source_datasets[0] if source_datasets else {}
#             snk = sink_datasets[0] if sink_datasets else {}

#             rows.append({
#                 # ── Identity ──
#                 "Pipeline Name":                pipeline_name,
#                 "Run ID":                       run_id,
#                 "Pipeline Status":              run_status,
#                 "Run Start":                    run_start,
#                 "Activity Name":                act.get("activity_name", ""),
#                 "Activity Status":              act.get("status", ""),
#                 "Activity Run Start":           act.get("activity_run_start", ""),
#                 "Activity Run End":             act.get("activity_run_end", ""),
#                 "Duration (ms)":                act.get("duration_ms"),

#                 # ── Pipeline Parameters ──
#                 "Pipeline Parameters":          " | ".join(f"{k}={v}" for k, v in pipeline_params.items()),

#                 # ── Source ──
#                 "Source Dataset Name":          src.get("referenceName", ""),
#                 "Source Runtime Params":        " | ".join(
#                                                     f"{k}={v}" for k, v in (src.get("parameters") or {}).items()
#                                                 ),
#                 "Source Query / Logic":         json.dumps(source_exec) if source_exec else "",

#                 # ── Sink ──
#                 "Sink Dataset Name":            snk.get("referenceName", ""),
#                 "Sink Runtime Params":          " | ".join(
#                                                     f"{k}={v}" for k, v in (snk.get("parameters") or {}).items()
#                                                 ),
#                 "Sink Write Logic":             json.dumps(sink_exec) if sink_exec else "",

#                 # ── Volume ──
#                 "Rows Read":                    act.get("rows_read"),
#                 "Rows Written":                 act.get("rows_written"),
#                 "Data Read (bytes)":            act.get("data_read_bytes"),
#                 "Data Written (bytes)":         act.get("data_written_bytes"),
#                 "Throughput (KB/s)":            act.get("throughput_kb_per_s"),

#                 # ── Error ──
#                 "Error":                        json.dumps(act.get("error")) if act.get("error") else "",
#             })
#     return pd.DataFrame(rows)


# def build_source_sink_map(runs):
#     """Unique source → sink combinations with parameter patterns and run counts."""
#     combo_data = defaultdict(lambda: {
#         "count": 0, "succeeded": 0, "failed": 0,
#         "pipelines": set(), "param_examples": []
#     })

#     for run in runs:
#         pipeline_name = run.get("pipeline_name", "Unknown")
#         for act in run.get("copy_activities", []):
#             source_datasets = act.get("source_datasets") or []
#             sink_datasets   = act.get("sink_datasets") or []

#             src = source_datasets[0] if source_datasets else {}
#             snk = sink_datasets[0] if sink_datasets else {}

#             src_name    = src.get("referenceName", "Unknown")
#             snk_name    = snk.get("referenceName", "Unknown")
#             src_params  = src.get("parameters") or {}
#             snk_params  = snk.get("parameters") or {}

#             key = (src_name, snk_name)
#             c = combo_data[key]
#             c["count"] += 1
#             c["pipelines"].add(pipeline_name)

#             status = (act.get("status") or "").lower()
#             if status == "succeeded":   c["succeeded"] += 1
#             elif status == "failed":    c["failed"] += 1

#             if len(c["param_examples"]) < 3:
#                 c["param_examples"].append({
#                     "source_params": src_params,
#                     "sink_params":   snk_params,
#                     "pipeline":      pipeline_name
#                 })

#     rows = []
#     for (src_name, snk_name), c in sorted(combo_data.items(), key=lambda x: x[1]["count"], reverse=True):
#         example = c["param_examples"][0] if c["param_examples"] else {}
#         rows.append({
#             "Source Dataset":           src_name,
#             "Sink Dataset":             snk_name,
#             "Total Executions":         c["count"],
#             "Succeeded":                c["succeeded"],
#             "Failed":                   c["failed"],
#             "Pipelines Using This":     ", ".join(sorted(c["pipelines"])),
#             "Example Source Params":    " | ".join(
#                                             f"{k}={v}" for k, v in (example.get("source_params") or {}).items()
#                                         ),
#             "Example Sink Params":      " | ".join(
#                                             f"{k}={v}" for k, v in (example.get("sink_params") or {}).items()
#                                         ),
#             "All Param Examples":       json.dumps(c["param_examples"]),
#         })
#     return pd.DataFrame(rows)


# # ─────────────────────────────────────────────
# # FORMATTING
# # ─────────────────────────────────────────────

# HEADER_FILL  = PatternFill("solid", start_color="1F4E79", end_color="1F4E79")
# FAILED_FILL  = PatternFill("solid", start_color="FCE4D6", end_color="FCE4D6")
# ALT_FILL     = PatternFill("solid", start_color="F2F2F2", end_color="F2F2F2")
# THIN_BORDER  = Border(
#     left   = Side(style="thin", color="CCCCCC"),
#     right  = Side(style="thin", color="CCCCCC"),
#     top    = Side(style="thin", color="CCCCCC"),
#     bottom = Side(style="thin", color="CCCCCC"),
# )

# def format_sheet(ws, failed_col_name=None, col_widths=None):
#     # Header
#     headers = [cell.value for cell in ws[1]]
#     for cell in ws[1]:
#         cell.font      = Font(bold=True, color="FFFFFF", name="Arial", size=10)
#         cell.fill      = HEADER_FILL
#         cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
#         cell.border    = THIN_BORDER
#     ws.row_dimensions[1].height = 30

#     # Detect failed column index
#     failed_col_idx = None
#     if failed_col_name and failed_col_name in headers:
#         failed_col_idx = headers.index(failed_col_name) + 1

#     # Data rows
#     for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
#         is_failed = False
#         if failed_col_idx:
#             val = ws.cell(row=row_idx, column=failed_col_idx).value
#             is_failed = bool(val and str(val).strip() not in ("", "0", "Succeeded", "succeeded"))

#         fill = FAILED_FILL if is_failed else (ALT_FILL if row_idx % 2 == 0 else None)
#         for cell in row:
#             cell.font      = Font(name="Arial", size=10)
#             cell.border    = THIN_BORDER
#             cell.alignment = Alignment(vertical="center", wrap_text=False)
#             if fill:
#                 cell.fill = fill

#     # Column widths
#     if col_widths:
#         for col_letter, width in col_widths.items():
#             ws.column_dimensions[col_letter].width = width
#     else:
#         for col_cells in ws.columns:
#             max_len = max((len(str(c.value or "")) for c in col_cells), default=10)
#             ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max_len + 4, 50)

#     ws.freeze_panes        = "B2"
#     ws.auto_filter.ref     = ws.dimensions


# def write_sheet(wb, sheet_name, df, failed_col_name=None, col_widths=None):
#     if sheet_name in wb.sheetnames:
#         del wb[sheet_name]
#     ws = wb.create_sheet(sheet_name)
#     # Write header
#     ws.append(list(df.columns))
#     # Write rows
#     for _, row in df.iterrows():
#         ws.append([str(v) if isinstance(v, (dict, list)) else v for v in row])
#     format_sheet(ws, failed_col_name=failed_col_name, col_widths=col_widths)
#     print(f"  Sheet '{sheet_name}' written — {len(df)} rows")


# # ─────────────────────────────────────────────
# # MAIN
# # ─────────────────────────────────────────────

# def main():
#     runs = read_jsonl(JSONL_FILE)

#     print("\nBuilding datasets...")
#     df_distribution  = build_distribution(runs)
#     df_parameters    = build_pipeline_parameters(runs)
#     df_copy_details  = build_copy_activity_details(runs)
#     df_source_sink   = build_source_sink_map(runs)

#     print(f"  Distribution rows   : {len(df_distribution)}")
#     print(f"  Parameter rows      : {len(df_parameters)}")
#     print(f"  Copy activity rows  : {len(df_copy_details)}")
#     print(f"  Source-sink rows    : {len(df_source_sink)}")

#     # Bootstrap with first sheet via pandas then add rest via openpyxl
#     df_distribution.to_excel(OUTPUT_FILE, index=False, sheet_name="Pipeline Distribution")
#     wb = load_workbook(OUTPUT_FILE)

#     # Format the first sheet that pandas created
#     format_sheet(
#         wb["Pipeline Distribution"],
#         failed_col_name="Failed",
#         col_widths={
#             "A": 45, "B": 12, "C": 12, "D": 10, "E": 12,
#             "F": 10, "G": 14, "H": 18, "I": 18, "J": 20,
#             "K": 16, "L": 16, "M": 40,
#         }
#     )

#     print("\nWriting sheets...")
#     write_sheet(wb, "Pipeline Parameters",    df_parameters,   failed_col_name="Status")
#     write_sheet(wb, "Copy Activity Details",  df_copy_details, failed_col_name="Activity Status")
#     write_sheet(wb, "Source Sink Map",        df_source_sink,  failed_col_name="Failed")

#     wb.save(OUTPUT_FILE)
#     print(f"\nSaved to {OUTPUT_FILE}")

# if __name__ == "__main__":
#     main()

import json
import pandas as pd
from collections import defaultdict

INPUT_FILE = "_DATA_AND_OUTPUTS/runs_data/21May-7July__shell-32-eun-adf-okjtarmveaftjxpeuzj_runs.jsonl"
OUTPUT_FILE = "_DATA_AND_OUTPUTS/presentable_outputs/pipeline_parameters.xlsx"


def normalize_value(val):
    """Recursively strip expression-wrapper dicts (e.g. {'value': ..., 'type': 'Expression'})
    down to just their 'value', discarding 'type' and any other sibling keys.
    Any other dict/list gets converted to a compact JSON string so it stays hashable
    (for set dedup) and readable in Excel."""
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


def build_pipeline_param_summary(runs):
    pipeline_data = defaultdict(lambda: {"run_count": 0, "params": defaultdict(set)})

    for run in runs:
        pipeline_name = run.get("pipeline_name", "UNKNOWN")
        entry = pipeline_data[pipeline_name]
        entry["run_count"] += 1

        params = run.get("pipeline_parameters") or {}
        for param_name, param_val in params.items():
            normalized = normalize_value(param_val)
            entry["params"][param_name].add(normalized)

    rows = []
    for pipeline_name, info in pipeline_data.items():
        formatted_parts = []
        for param_name, value_set in sorted(info["params"].items()):
            values_str = ", ".join(sorted(str(v) for v in value_set))
            formatted_parts.append(f"{param_name}: [{values_str}]")

        rows.append({
            "pipeline_name": pipeline_name,
            "run_count": info["run_count"],
            "distinct_param_count": len(info["params"]),
            "parameters": "\n".join(formatted_parts)
        })

    return rows


runs = load_runs(INPUT_FILE)
rows = build_pipeline_param_summary(runs)

df = pd.DataFrame(rows)
df.to_excel(OUTPUT_FILE, index=False, engine="openpyxl")
print(f"Wrote {len(rows)} pipelines to {OUTPUT_FILE}")  