# mssql_spg_migration_validation_testing

End-to-end validation skill for MSSQL → Snowflake Postgres (SPG) migrations.

Validates that stored procedures, functions, views, and triggers produce identical results on both platforms, checks schema/DDL coverage, and generates a Markdown + PowerPoint report.

---

## What it does

- **Behavioral validation** — executes stored procedures, functions, views, and triggers on both MSSQL and SPG and compares row counts and output
- **Schema validation** — checks table, view, procedure, function, trigger, index, and constraint coverage in SPG vs MSSQL
- **Markdown report** — two-part report: Part 1 (DDL structure) and Part 2 (behavioral execution parity)
- **PowerPoint report** — 23-slide deck with KPIs, schema coverage, pass rate charts, and remediation priorities

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **Docker Desktop** | Used to run SQL Server locally — the skill handles container setup automatically |
| **Python 3.9+** | Required to run the validation and reporting scripts |
| **Cortex Code (CoCo)** | The skill is invoked from CoCo; install via the skill catalog |
| **Snowflake account** | With a Snowflake Postgres (SPG) instance provisioned |

> The skill handles SQL Server container creation, data loading, and validation schema setup automatically — you do not need to configure these manually.

### DDL inputs required

The skill needs DDL scripts for both sides of the migration before validation can run:

| Input | Description |
|-------|-------------|
| **MSSQL DDL** | Original SQL Server scripts (`.sql` files) — tables, views, stored procedures, functions, triggers. The skill deploys these into the local SQL Server container. |
| **SPG DDL** | Converted Postgres-compatible scripts — either provided by you or already deployed into the SPG instance. If the SPG instance already has the converted objects deployed, no DDL files are needed. |

> If you have not yet converted your MSSQL DDL to Postgres, use the `mssql-ddl-realization` skill first to parse, convert, and deploy the DDL to SPG before running this validation skill.

---

## How to install

### Option 1 — Install from GitHub (recommended)

In Cortex Code (CoCo), run:

```
/github-plugin-installer https://github.com/sfc-gh-rkhandhadia/spg_migration
```

CoCo will clone the repo and register the skill automatically.

### Option 2 — Install from a local folder

If you have already cloned the repo locally:

```
/local-plugin-installer /path/to/spg_migration/mssql_spg_migration_validation_testing
```

### Verify the install

After installing, confirm the skill is available:

```
/find-skill mssql_spg_migration_validation_testing
```

---

## How to run

### Run full validation and generate reports

```
/mssql_spg_migration_validation_testing

Validate the MSSQL to SPG migration for my <database name> database.
MSSQL DDL scripts are at <path to sql scripts>.
SPG host is <host>.snowflakecomputing.app (user: snowflake_admin).
Output reports to <output folder path>.
```

### Regenerate reports from existing validation results

```
Regenerate the markdown and PowerPoint migration reports using the
latest validation results already stored in SPG.
Output to <output folder path>.
```

### Load test data into SPG

```
Load data from MSSQL into SPG for the <database name> database so
procedures and functions have rows to work with during validation.
```

### Investigate a specific failure

```
The validation shows <schema.object_name> has verdict FAIL / SPG_ERROR.
What is the reason and how do I fix it?
```

---

## Verdict taxonomy

| Verdict | Meaning |
|---------|---------|
| `PASS` | Output matches on both MSSQL and SPG |
| `PASS_DML_PROC` | DML/ETL procedure — executed successfully on both sides, no result set by design |
| `FAIL` | Row count or column mismatch |
| `SPG_ERROR` | SPG execution failed, MSSQL succeeded |
| `MSSQL_ERROR` | MSSQL execution failed |
| `BOTH_FAILED` | Both sides failed — likely a data-state dependency |
| `FAIL_MISSING_PREREQ` | Reclassified BOTH_FAILED — prerequisite seed data missing, not a migration defect |
| `SPG_ONLY` | Object exists in SPG but not in MSSQL source (e.g. added by converter) |

---

## Key scripts

### Main pipeline

| Script | Purpose |
|--------|---------|
| `run.py` | Main validation runner — triggers all phases in order |
| `mssql_proc_executor.py` | Executes every procedure/function against SQL Server; writes `mssql_output.jsonl` |
| `spg_proc_executor.py` | Executes every procedure/function against Snowflake Postgres; writes `spg_output.jsonl` |
| `compare_proc_outputs.py` | Diffs MSSQL vs SPG outputs, applies reclassification rules, writes to audit tables |
| `validate_batch.py` | View validation: row count, column set, and data hash parity |
| `validate_triggers.py` | Trigger existence, table target, and event type parity |
| `validate_funcs_procs_separate.py` | Structural parity check (existence + param count/names) across all schemas; writes to audit tables |
| `prereq_guard.py` | YAML-driven prerequisite state restorer — run before proc execution |
| `param_discovery.py` | Samples real parameter values from live data for use by both executors |
| `load_mssql_to_spg.py` | FK-safe data loader from MSSQL into SPG (no DDL changes) |
| `generate_validation_markdown.py` | Generates two-part Markdown report from audit table results |
| `generate_migration_report.py` | Generates 27-slide Snowflake-branded PowerPoint report |
| `alternate_flow_rules.yaml` | Rule-driven `BOTH_FAILED` → `FAIL_MISSING_PREREQ` reclassification config |
| `setup_validation_tables.sql` | Creates `validation.validation_run`, `validation.validation_result`, and summary views in SPG |

### Shell wrappers

| Script | Purpose |
|--------|---------|
| `run_validation.sh` | Loads `.env` and runs `python3 run.py --all` |
| `run_compare_and_reports.sh` | Regenerates comparison + Markdown + PPTX from existing JSONL results (no re-execution) |

### Ad-hoc and legacy scripts

These scripts print to stdout only — results are **not** written to the audit tables and cannot be used for report generation.

| Script | Purpose | Use instead |
|--------|---------|-------------|
| `run_validation.py` | All-object validator (tables, views, procs, functions, triggers, types) against a single environment using `.env` credentials | `run.py --all` for a full audited run |
| `full_validation.py` | **Legacy.** Structural check for the `api` schema only (hardcoded). Checks param counts and view row counts; does not execute procedures. | `run.py --all` or `validate_funcs_procs_separate.py` |
| `full_schema_audit.py` | Structural existence check across all schemas — procedures, functions, and views. Wide-angle survey with no execution. | `validate_funcs_procs_separate.py` (persists results) |
