---
name: mssql-spg-load
description: "Load data from a MSSQL source database into a Snowflake Postgres (SPG) instance using the repo's reload utility. Use when: reloading SPG after a reset, syncing MSSQL test data to SPG, running a pg_reload script, loading a source database into SPG, or any time the user says 'load same data', 'reload SPG', 'load data into Snowflake Postgres', or 'sync data'."
---

# MSSQL → SPG Data Load

Full clean reload of a MSSQL source database into a Snowflake Postgres (SPG) instance using the project's Python reload utility.

## DDL Deployment Guardrail

**Never deploy DDL to SPG without explicit user confirmation.**

SPG may already contain converted schema objects (tables, views, functions, stored procedures, triggers, types). Deploying DDL without asking can overwrite or break existing converted code.

The following DDL operations are **exempt** from this guardrail because they are a normal part of the load process:

- `ALTER TABLE ... DROP CONSTRAINT` — dropping FK constraints before load
- `ALTER TABLE ... ADD CONSTRAINT ... NOT VALID` — restoring FK constraints after load
- `TRUNCATE TABLE` — clearing target tables before reload

Before executing any other DDL statement against SPG — including `CREATE TABLE`, `CREATE VIEW`, `CREATE FUNCTION`, `CREATE PROCEDURE`, `CREATE TYPE`, `DROP TABLE`, or any statement that creates, replaces, or destroys schema objects — you must ask the user:

> SPG may already have converted schema objects deployed. Do you want me to deploy DDL to SPG, or should I skip schema deployment and load data only?

Default answer if the user does not specify: **skip DDL deployment, load data only.**

This guardrail applies whether the DDL comes from:
- the PG DDL scripts directory
- a generated loader script
- inline fixes or patches
- any other source

Only proceed with DDL deployment if the user explicitly confirms it.

---

## What the Utility Does

The reload utility typically performs the following actions:

1. Collects existing foreign key definitions from SPG before teardown
2. Drops discovered foreign key constraints as needed for reload
3. Truncates target tables in SPG
4. Applies source-specific data fixups when the selected script supports them
5. Copies data from MSSQL to SPG
6. Restores foreign keys, often as `NOT VALID`
7. Seeds any required post-load state such as active job metadata
8. Emits load metadata for downstream validation when configured

Do not hard-code object counts such as number of constraints, tables, warnings, or rows loaded. Always read these from runtime output.

## Reload Script Discovery

Locate the reload script in the user's repo or workspace rather than assuming a fixed local path, file name, or folder structure.

Look for the reload entrypoint using signals such as:

- Python scripts or modules whose purpose is to reload, sync, seed, or copy data from MSSQL into SPG
- repo documentation, comments, or runbooks that identify the supported reload command
- a script, module, or command explicitly named by the user

If multiple candidate reload paths exist:

- prefer the one explicitly named by the user
- otherwise choose the one documented for full data reload into SPG
- otherwise compare whether a candidate includes optional source-side fixups or post-load validation steps
- if still ambiguous, ask the user which reload path to use

Do not assume or reference a specific source database name, script file name, script prefix, utility folder, or repo layout. Use generic terms such as `source MSSQL database` and `selected reload script` unless the user explicitly wants environment-specific names documented.

### When no reload script exists

If no reload script is found in the repo or workspace, generate one dynamically. Do not ask the user to provide one.

**The generated loader must be data-only by default.** It must not include any `CREATE`, `ALTER`, or `DROP` statements. If the user explicitly requests schema deployment as part of the load, apply the DDL Deployment Guardrail above before adding any DDL to the generated script.

**Required: consume `object_inventory.json` before writing the loader.**

If `object_inventory.json` exists in the shared directory (produced by `mssql-ddl-realization`), read it before writing a single line of loader code. It contains the DDL and column-level types for every table in the source. Use it to:

1. Build the table list and load order from the object graph — do not query `INFORMATION_SCHEMA` as a substitute
2. Scan all column definitions for types that require special adapter registration or value conversion before writing the loader

The following SQL Server → Postgres type mappings must always be handled in the generated loader, regardless of whether they appear in the current schema. Register or implement all adapters upfront:

| SQL Server type | Postgres type | Required handling |
|---|---|---|
| `uniqueidentifier` | `uuid` | Call `psycopg2.extras.register_uuid()` before connecting. Pass `uuid.UUID` objects through directly. |
| `bit` | `boolean` | Detect target column type from `information_schema.columns`; cast `int` → `bool` when target is `boolean`. |
| `int IDENTITY` / `bigint IDENTITY` | `GENERATED ALWAYS AS IDENTITY` | Use `OVERRIDING SYSTEM VALUE` in the INSERT statement. Detect via `identity_generation = 'ALWAYS'` in `information_schema.columns`. |
| `varbinary` / `binary` | `bytea` | Convert `bytes` → `hex string` or pass as `memoryview`. |
| `datetime` / `datetime2` | `timestamp` | Pass Python `datetime.datetime` objects through directly. |

**Foreign key handling:** Drop all FK constraints before loading (to allow any-order inserts), and do not restore them unless the user explicitly requests it. Dynamically discover FKs from `information_schema.table_constraints` — do not hardcode constraint names.

**Verification gate:** After the loader completes, query row counts for every table in the load manifest and compare against the MSSQL source. Any table with SPG row count = 0 and MSSQL row count > 0 is a silent failure. Surface it as `COUNT_FAIL`, not a warning, and do not allow downstream validation to proceed until it is resolved.

## Workflow

### Step 1: Collect Connection Details

Ask the user for, or extract from their message:

#### MSSQL source

- Server and port in `host:port` format
- Database name
- Login
- Password

#### SPG target

- SPG host or FQDN
- SPG user
- SPG password
- Target database name if not the default used by the script

#### Execution context

- Repo or workspace location containing the reload script
- Shared output directory, if orchestration outputs are expected
- Script name, if already known

If the user already provided these values elsewhere in the workflow, reuse them instead of asking again.

### Step 2: Configure the Script Without Hard-Coded Assumptions

Read the selected script and determine how it accepts configuration.

Prefer this order:

1. environment variables
2. command-line arguments
3. a small isolated configuration block in the script

Update only the minimum required configuration surface. Do not assume constant names, directory names, database names, usernames, ports, or host suffixes unless they are present in the script or explicitly supplied by the user.

Validate the following before execution:

- MSSQL host includes port as `host:port` when the script expects a combined value
- SPG host, port, database, and user align with the target environment
- any shared output directory environment variable points to the intended location

After configuration, confirm to the user:

- which script will run
- which MSSQL source it points to
- which SPG target it points to
- whether source-specific fixups are enabled

### Step 3: Run the Reload

Run from the script's actual directory, not a hard-coded path.

Generic pattern:

```bash
export SHARED_OUTPUT_DIR="<shared_dir>"
python3 "<script_path>" 2>&1
```

If the user wants the job detached, run it in the background and monitor output. Otherwise run in the foreground and stream progress.

Expected phases in output may include:

1. source and target connection checks
2. foreign key discovery and drop phase
3. table truncation
4. optional source-specific fixups
5. table-by-table copy
6. foreign key restore
7. post-load seeding
8. optional witness or API re-sync steps
9. final summary block

Do not hard-code exact phase names. Use the script's real output as the source of truth.

### Step 4: Confirm Completion

Wait for the final summary or equivalent success indicator from the script.

Report back to the user:

- total rows loaded
- tables processed
- tables skipped
- active job id, if applicable
- any unexpected warnings or errors
- whether shared handoff files were emitted

Do not assume fixed success counts. Parse the actual run output.

## Expected Warnings

Some reload flows may emit repeatable warnings that are known and acceptable for that environment.

Treat a warning as expected only if one of the following is true:

- the script documentation marks it as expected
- the repo comments or prior runbook marks it as expected
- the user confirms it is expected for this environment

Otherwise surface it as unexpected.

Examples of environment-specific warnings that may be expected:

- a foreign key cannot be restored because of duplicate referenced columns
- a fixup ran but updated zero rows because the source was already aligned
- an active record already exists from a previous run

Do not hard-code exact warning text as globally permanent unless the repo or user explicitly treats it that way.

## Troubleshooting

### Authentication failure against MSSQL

Usually indicates wrong credentials, wrong host, or wrong port. Re-check the source connection details and confirm the script's expected host format.

### Constraint drop or restore failure

May indicate stale fixup logic, schema drift, or a hard-coded constraint reference in the script. Inspect the script for dynamic discovery versus literal constraint names.

### SPG connection timeout

SPG may be hibernated or temporarily unavailable. Wake the instance using a lightweight connection, then rerun.

### Insert failure on a specific table

Often caused by source data violating target constraints. Inspect the failing table, then add or update source-specific fixups if appropriate.

### Post-load witness or API validation mismatch

If a post-load sync step exists and fails, verify the target connection is still open and validate the affected tables with targeted SQL checks.

## Stopping Points

- **Before any DDL is executed against SPG** — stop and ask the user whether schema deployment is intended (see DDL Deployment Guardrail)
- After script discovery and configuration, confirm the selected script and endpoints before modifying or running anything
- After the run completes, report the final summary and wait for follow-up

## Success Criteria

A successful load should satisfy the runtime checks for the selected script and environment, typically including:

- final summary indicates success with no fatal errors
- total rows loaded is consistent with the selected source
- required post-load state is seeded when applicable
- foreign key restore completes except for any explicitly expected warnings
- shared load metadata files are emitted when configured
- any required validation rows or witness records match the expected post-load state for that environment

Do not hard-code row counts, constraint counts, table counts, or witness values unless the user explicitly wants environment-specific assertions.

## Shared Handoff Outputs

Use a user-provided or repo-defined shared directory rather than a fixed local path.

Canonical pattern:

```bash
export SHARED_OUTPUT_DIR="<shared_dir>"
```

If the broader workflow uses shared orchestration artifacts, this skill may consume inputs such as:

- `object_inventory.json`
- `seed_profiles.yaml`
- `run_manifest.json`

When the load completes, it should emit outputs such as:

- `load_manifest.json`
- `load_summary.json`
- `spg_column_constraints.json` (pre-flight step — see below)

### Pre-flight: SPG constraint discovery

Before running the full data load in an orchestrated workflow, run the
constraint discovery script to emit column-level check constraint rules as a
shared artifact for upstream seed generation:

```bash
python3 scripts/discover_spg_constraints.py \
  --spg-host     <spg_host> \
  --spg-user     <spg_user> \
  --spg-password <spg_password> \
  --spg-database <spg_database> \
  --schema       dbo \
  --output       "$SHARED_OUTPUT_DIR/spg_column_constraints.json"
```

Emits `spg_column_constraints.json` — column-level value constraints parsed
from `pg_constraint WHERE contype = 'c'` using two regex patterns:

- OR-equality enum: `(col = 'Y'::bpchar) OR (col = 'N'::bpchar)` → `{type: enum, values: [Y, N]}`
- AND-comparison range: `(col >= 0) AND (col <= 25)` → `{type: range, min: 0, max: 25}`

The file is consumed by `mssql-ddl-realization/scripts/build_dep_graph.py`
via `--constraints-file` to drive constraint-correct seed generation.

**Why this lives here, not in mssql-ddl-realization:**
`mssql-ddl-realization` has no required dependency on any other skill.
This skill (mssql-spg-load) owns the SPG connection and therefore owns
constraint discovery. The constraints file is an optional accelerator:
when absent, realization generates best-effort values for standalone use;
when present, realization generates semantically correct values that comply
with the target schema rules.

**Standalone load use:**
When loading without a prior realization run, or when the seed data was
generated without constraint info, run `discover_spg_constraints.py` first,
then re-run `mssql-ddl-realization/scripts/seed_data.py` with the updated
`dep_graph.json` (rebuilt with `--constraints-file`), then reload to SPG.

### load_manifest.json

Capture values such as:

- workload name
- MSSQL source host and database
- SPG target host and database
- reload script used
- whether source fixups were applied
- whether active job state was seeded

### load_summary.json

Capture values such as:

- tables processed
- tables skipped
- total rows loaded
- foreign keys restored
- expected warnings
- active job id if available
- unexpected warnings or errors

## Standalone and Orchestration Behavior

This skill should work standalone first.

If upstream context files already exist, consume them. If they do not exist, proceed with user-supplied source and target details.

When used in a broader MSSQL → SPG flow:

- consume realized source context if available
- produce load metadata for downstream validation
- do not proceed to validation if the load did not complete successfully

The absence of upstream orchestration artifacts should not block execution when the required runtime inputs are already available from the user or current environment.