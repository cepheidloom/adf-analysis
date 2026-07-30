# ADF Analysis Tool

A Python toolkit to extract, analyse, and export Azure Data Factory resources into structured Excel reports. It covers Linked Services, Datasets, Pipelines, Activities, and Pipeline Run history, giving you a readable view of your entire ADF factory without clicking through the Azure portal.

## What This Tool Does

| Script | Output |
|---|---|
| `generate_extract/full_extract_generation.py` | Pulls everything from your ADF factory via the Azure SDK and saves it as a single JSON file |
| `generate_extract/pipeline_runs_extraction.py` | Fetches pipeline run history and saves it as a JSONL file (supports resuming via checkpoint) |
| `linked_services_processing.py` | Exports all Linked Services to Excel, grouped by type |
| `datasets_processing.py` | Exports all Datasets to Excel, grouped by type |
| `activities_processing.py` | Exports all Pipelines and Activities to Excel with navigation, type sheets, and reference mapping |
| `utils.py` | A personal collection of utility scripts — export pipeline list, extract SQL queries, Stored Procedure names, and Script activity text |
| `generate_extract/pipeline_runs_processing.py` | Processes the JSONL run history into a summarised Excel report |
| `generate_extract/generate_json_blueprint.py` | CLI tool — generates a compact structural map (tree or flat) of any JSON file, field names and types only, no values — useful for sharing structure with an LLM without exposing sensitive data |

---

## Prerequisites

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Authenticate for the extraction scripts

The extraction scripts (`full_extract_generation.py` and `pipeline_runs_extraction.py`) use `InteractiveBrowserCredential`, which opens a **browser window** asking you to sign in with your Azure account — no extra setup is needed beyond having access to your ADF factory.

### 3. Find your factory details (if you don't already have them)

You need three values for `config.yaml`: **Subscription ID**, **Resource Group**, and **Factory Name**. If you already know these, skip this step.

If not, you can look them up in the [Azure Portal](https://portal.azure.com) under your Data Factory resource → Overview, or run the following Azure CLI commands:

```bash
az login
```

```bash
az graph query -q "Resources | where type == 'microsoft.datafactory/factories' | join kind=leftouter (ResourceContainers | where type == 'microsoft.resources/subscriptions' | project subscriptionId, SubscriptionName=name) on subscriptionId | project FactoryName=name, ResourceGroup=resourceGroup, SubscriptionName, SubscriptionId=subscriptionId, Location=location" --query "data" --output table
```

> **Note:** The `az graph query` command requires the `resource-graph` extension:
> ```bash
> az extension add --name resource-graph
> ```

---

## First-Time Setup

Before running anything, do two things:

**1. Create the `_DATA_AND_OUTPUTS/` folder** in the repository root.

**2. Create `_DATA_AND_OUTPUTS/config.yaml`** with the following content — this file is read by all scripts:

```yaml
# Azure ADF connection details
# Required by: full_extract_generation.py, pipeline_runs_extraction.py
subscription_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
resource_group:  "my-resource-group-name"
factory_name:    "my-adf-factory-name"

# Path to the full JSON extract produced by full_extract_generation.py
# Required by: linked_services_processing.py, datasets_processing.py,
#              activities_processing.py, utils.py
full_extract_path: "_DATA_AND_OUTPUTS/my-adf-factory-name_full_extract.json"

# Path to the JSONL pipeline runs file produced by pipeline_runs_extraction.py
# Required by: pipeline_runs_processing.py
jsonl_input_file: "_DATA_AND_OUTPUTS/runs_data/my-adf-factory-name_runs.jsonl"
```

> **Important:** Add `config.yaml` to `.gitignore` — it contains your Azure subscription details. Add `_DATA_AND_OUTPUTS/` too, to avoid committing large JSON/JSONL extracts.

### Config key reference

| Key | Used by | Description |
|---|---|---|
| `subscription_id` | `full_extract_generation.py`, `pipeline_runs_extraction.py` | Your Azure Subscription ID |
| `resource_group` | `full_extract_generation.py`, `pipeline_runs_extraction.py` | Resource group containing your ADF factory |
| `factory_name` | `full_extract_generation.py`, `pipeline_runs_extraction.py` | The ADF factory name |
| `full_extract_path` | `datasets_processing.py`, `activities_processing.py`, `linked_services_processing.py`, `utils.py` | Path to the JSON extract produced by `full_extract_generation.py` |
| `jsonl_input_file` | `pipeline_runs_processing.py` | Path to the JSONL runs file produced by `pipeline_runs_extraction.py` |

---

## Directory Structure

> **Important:** All scripts must be run from the **repository root**, not from inside any subfolder.

```
adf-analysis/                               <- repository root, run all scripts from here
|
+-- _DATA_AND_OUTPUTS/                      <- create this folder manually
|   +-- config.yaml                         <- create this file manually (see above)
|   +-- presentable_outputs/                <- auto-created by processing scripts
|   |   +-- Datasets.xlsx                   <- generated by datasets_processing.py
|   |   +-- Activities.xlsx                 <- generated by activities_processing.py
|   |   +-- Linked_services.xlsx            <- generated by linked_services_processing.py
|   |   +-- pipelines.xlsx                  <- generated by utils.py
|   |   +-- pipeline_parameters.xlsx        <- generated by pipeline_runs_processing.py
|   |
|   +-- <factory_name>_full_extract.json    <- generated by full_extract_generation.py
|   +-- runs_data/
|       +-- <factory_name>_runs.jsonl       <- generated by pipeline_runs_extraction.py
|       +-- <factory_name>_checkpoint.json  <- auto-managed by pipeline_runs_extraction.py
|
+-- generate_extract/
+-- datasets_processing.py
+-- activities_processing.py
+-- linked_services_processing.py
+-- utils.py
+-- README.md
```

---

## Run Order

There are **two independent sequences**. You can run either or both — they do not depend on each other.

---

### Track A — Factory Definition → Excel Reports

**Step A1: Extract the factory definition**

```bash
python generate_extract/full_extract_generation.py
```

A browser window opens for Azure authentication. Once signed in, the script fetches all factory resources (Linked Services, Datasets, Pipelines, Triggers, Integration Runtimes, etc.).

Produces: `_DATA_AND_OUTPUTS/<factory_name>_full_extract.json`

**Step A2: Export to Excel** *(run any or all, in any order, after Step A1)*

```bash
python linked_services_processing.py
python datasets_processing.py
python activities_processing.py
```

These all read from `full_extract_path` in your `config.yaml`.

**Step A3: Run utils.py** *(optional, requires Step A1)*

```bash
python utils.py
```

`utils.py` is a personal collection of scripts written as the need arose — there is no single fixed purpose to it. Running it currently produces:

- `_DATA_AND_OUTPUTS/presentable_outputs/pipelines.xlsx` — all pipeline names and their folder paths
- `_DATA_AND_OUTPUTS/lookup_sp_getvar.json` — raw dump of all Lookup, SqlServerStoredProcedure, and Script activity definitions
- `_DATA_AND_OUTPUTS/sp_and_queries.json` — extracted SQL queries, stored procedure names, and script text from those activities

---

### Track B — Pipeline Run History → Excel Report

**Step B1: Extract pipeline run history**

Open `generate_extract/pipeline_runs_extraction.py` and adjust these two constants near the top before running:

```python
LOOKBACK_DAYS = 45          # how many days of run history to fetch
PIPELINES_TO_SKIP = []      # pipeline names to exclude, e.g. ["MyDebugPipeline"]
```

Then run:

```bash
python generate_extract/pipeline_runs_extraction.py
```

A browser window opens for Azure authentication. The script fetches pipeline runs page by page and writes them to a JSONL file.

Produces: `_DATA_AND_OUTPUTS/runs_data/<factory_name>_runs.jsonl`

If the script is interrupted, re-run it — it resumes from where it left off using a checkpoint file, which is automatically deleted on successful completion.

**Step B2: Process run history into Excel**

```bash
python generate_extract/pipeline_runs_processing.py
```

Produces: `_DATA_AND_OUTPUTS/presentable_outputs/pipeline_parameters.xlsx`

This Excel file contains two sheets:
- **Pipeline_Parameters** — one row per unique parameter value seen across all runs (unpivoted)
- **Pipeline_Summary** — one row per pipeline with total/succeeded/failed/cancelled run counts and date range

> **Tip:** There is a third sheet option (`All_Pipeline_Runs`) — one row per individual run. To enable it, uncomment the three lines marked in `pipeline_runs_processing.py`.

---

## JSON Blueprint Tool

`generate_extract/generate_json_blueprint.py` is a standalone CLI tool that maps the structure of any JSON file — field names, types, and nesting — without exposing any actual values. This is useful when you want to share the shape of a large ADF extract with an LLM to get development help, without leaking the underlying data.

```bash
# Tree mode (default) — human-readable indented view
python generate_extract/generate_json_blueprint.py _DATA_AND_OUTPUTS/my-factory_full_extract.json --mode tree

# Flat mode — one dot-path per line, compact, good for pasting into an LLM chat
python generate_extract/generate_json_blueprint.py _DATA_AND_OUTPUTS/my-factory_full_extract.json --mode flat

# Optionally specify a custom output file path
python generate_extract/generate_json_blueprint.py _DATA_AND_OUTPUTS/my-factory_full_extract.json --mode flat my_blueprint.txt
```

By default the output is saved as `<input_file>_blueprint_tree.txt` or `_blueprint_flat.txt` alongside the input file.

---

## Notes

- All scripts must be run from the repository root, not from inside `generate_extract/`.
- Authentication uses a browser popup (`InteractiveBrowserCredential`) — no need for `az login`.
- Add `_DATA_AND_OUTPUTS/config.yaml` and `_DATA_AND_OUTPUTS/` to `.gitignore` to avoid committing sensitive details and large data files to source control.