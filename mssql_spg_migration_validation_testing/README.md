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

### 1. Source: SQL Server (MSSQL)

You need a running SQL Server instance with the source database. The easiest way is Docker:

```bash
docker run -d --name mssql \
  -e ACCEPT_EULA=Y \
  -e SA_PASSWORD=YourPassword123! \
  -p 1434:1433 \
  mcr.microsoft.com/mssql/server:2022-latest
```

Load your DDL scripts into the `MENU_MANAGEMENT` database (or your source DB name).

### 2. Target: Snowflake Postgres (SPG)

- Create a Snowflake Postgres instance in your Snowflake account
- Deploy the converted DDL (tables, views, procedures, functions, triggers) into the `postgres` database
- SPG user must have `CREATE SCHEMA` and full DML privileges

### 3. Python dependencies

```bash
pip install pymssql psycopg2-binary pyyaml python-pptx
```

### 4. Validation schema in SPG

Create the validation tracking schema once:

```sql
CREATE SCHEMA IF NOT EXISTS validation;

CREATE TABLE IF NOT EXISTS validation.validation_run (
    run_id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    run_number SERIAL,
    object_type TEXT,
    run_started_at TIMESTAMPTZ DEFAULT now(),
    run_completed_at TIMESTAMPTZ,
    total_objects INT DEFAULT 0,
    pass_count INT DEFAULT 0,
    fail_count INT DEFAULT 0,
    skip_count INT DEFAULT 0,
    run_status TEXT DEFAULT 'RUNNING'
);

CREATE TABLE IF NOT EXISTS validation.validation_result (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    run_id UUID REFERENCES validation.validation_run(run_id),
    run_number INT,
    object_type TEXT,
    source_schema TEXT,
    object_name TEXT,
    test_verdict TEXT,
    mssql_rows INT,
    spg_rows INT,
    issues TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 5. Environment variables

Create a `.env` file or export these before running:

```bash
export MSSQL_HOST=localhost
export MSSQL_PORT=1434
export MSSQL_USER=sa
export MSSQL_PASSWORD=YourPassword123!
export MSSQL_DB=MENU_MANAGEMENT

export SPG_HOST=<your-spg-host>.snowflakecomputing.app
export SPG_PORT=5432
export SPG_USER=snowflake_admin
export SPG_PASSWORD=<your-spg-password>
export SPG_DATABASE=postgres

export MSSQL_SPG_SHARED_DIR=/path/to/this/scripts/folder
```

---

## How to run

### Run full validation

```bash
bash scripts/run_validation.sh
```

This runs validation for triggers, views, and procedures/functions against both MSSQL and SPG and writes results to `validation.validation_result` in SPG.

### Load test data into SPG

```bash
python3 scripts/load_mssql_to_spg.py
```

Copies rows from MSSQL into SPG — drops foreign keys, truncates, inserts, restores foreign keys. Does **not** deploy any DDL.

### Regenerate reports only (no re-validation)

```bash
bash scripts/run_compare_and_reports.sh
```

Reads the latest validation results from SPG and generates:
- `Migration_Validation_<date>.md` — Markdown report
- `Migration_Validation_<date>.pptx` — PowerPoint report

---

## Prompt examples

Use these prompts in Cortex Code (CoCo) after installing the skill:

**Run full validation and generate reports:**
```
/mssql_spg_migration_validation_testing

Validate the MSSQL to SPG migration for my MENU_MANAGEMENT database.
MSSQL is at localhost:1434 (sa / MyPassword).
SPG host is abc123.snowflakecomputing.app (snowflake_admin / MyPassword).
Output reports to /path/to/output/
```

**Regenerate reports from existing validation results:**
```
Regenerate the markdown and PowerPoint reports using the latest validation
run results in SPG. Output to /path/to/output/
```

**Investigate a specific failure:**
```
The validation shows stg.p_microsloadlog_update is FAIL. What is the
reason and how do I fix it?
```

**Add a reclassification rule:**
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
