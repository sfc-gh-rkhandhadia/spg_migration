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

## How to run

All workflows are driven through Cortex Code (CoCo). Install the skill first, then use natural language prompts — CoCo invokes the scripts internally.

### Install the skill

In CoCo, run:
```
/find-skill mssql_spg_migration_validation_testing
```

Or install directly from this repo using the GitHub plugin installer.

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

### Add a reclassification rule

```
Several procedures are showing BOTH_FAILED because they depend on a
staging row that isn't seeded. Add a rule to alternate_flow_rules.yaml
to reclassify them as FAIL_MISSING_PREREQ.
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

| Script | Purpose |
|--------|---------|
| `run.py` | Main validation runner |
| `compare_proc_outputs.py` | Compares MSSQL vs SPG outputs, applies reclassification rules |
| `mssql_proc_executor.py` | Executes objects against SQL Server |
| `spg_proc_executor.py` | Executes objects against Snowflake Postgres |
| `generate_validation_markdown.py` | Generates two-part markdown report |
| `generate_migration_report.py` | Generates 23-slide PowerPoint report |
| `alternate_flow_rules.yaml` | Rule-driven BOTH_FAILED → FAIL_MISSING_PREREQ reclassification |
| `load_mssql_to_spg.py` | FK-safe data loader (no DDL) |
| `run_validation.sh` | Runs full validation suite |
| `run_compare_and_reports.sh` | Regenerates comparison + markdown + PPTX from existing results |
