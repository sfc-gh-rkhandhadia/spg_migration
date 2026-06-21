---
name: mssql_spg_migration_validation_testing
description: "Agentic two-sided procedure and view parity testing for MSSQL to Snowflake Postgres migrations. Validates that migrated stored procedures and views produce identical outputs, side effects, and error behavior on both SQL Server and Snowflake Postgres. Supports query-log-driven and no-log test generation modes. Also generates Snowflake-branded PowerPoint validation reports for client delivery. Triggers: mssql migration testing, sql server to postgres validation, procedure parity, stored procedure comparison, view parity testing, migration validation, MSSQL SPG, T-SQL to Postgres testing, procedure testing, side-effect validation, migration sign-off, generate report, validation report, powerpoint report, client report."
---

# MSSQL to Snowflake Postgres: Migration Validation Testing

This skill runs agentic two-sided parity testing: for every business-critical stored procedure or view, it executes both the SQL Server original and the migrated Snowflake Postgres version under identical conditions, compares all outputs and side effects, classifies mismatches, proposes fixes, and generates a migration sign-off report.

## Intent Detection

| Intent | Triggers | Route |
|--------|----------|-------|
| INVENTORY | "list procedures", "inventory", "what to test", "prioritize", "which procedures", "which views", "complexity" | `agents/01-inventory.md` |
| GENERATE | "generate tests", "test cases", "create harness", "query logs", "no logs", "test catalog", "test scenarios" | `agents/02-test-generation.md` |
| EXECUTE | "run tests", "execute", "run harness", "run procedures", "capture results", "baseline" | `agents/03-execution-harness.md` |
| NORMALIZE | "normalize", "compare outputs", "type differences", "datetime precision", "NULL handling" | `agents/04-normalization.md` |
| DIFF | "diff", "compare", "mismatch", "differences", "row-level", "cell-level", "classify" | `agents/05-diff.md` |
| REPAIR | "fix", "repair", "suggest fix", "re-test", "correct", "patch", "defect" | `agents/06-repair.md` |
| REPORT | "report", "sign-off", "readiness", "dashboard", "pass/fail", "migration ready", "summary" | `agents/07-reporting.md` |
| PPTX | "generate report", "powerpoint", "client report", "pptx", "deck", "presentation", "export report" | Run `scripts/generate_migration_report.py` |
| MARKDOWN | "markdown report", "md report", "validation report", "generate markdown", "save report", "export markdown" | Run `scripts/generate_validation_markdown.py` |

## Full Workflow

The recommended end-to-end testing workflow follows these stages in sequence:

1. INVENTORY → Discover and prioritize all procedures and views
2. GENERATE → Build test cases from query logs or generate no-log SQL harnesses
3. EXECUTE → Run source (SQL Server) and target (Snowflake Postgres) side by side
4. NORMALIZE → Standardize outputs before comparison
5. DIFF → Compare outputs and classify mismatches
6. REPAIR → Propose and apply fixes, then re-run affected tests
7. REPORT → Produce pass/fail dashboard and sign-off recommendation

For procedures classified as `batch` or `wrapper`, use contract-based validation driven by shared metadata rather than direct result-set parity alone.

For DML-sensitive and ETL-sensitive procedures, support an alternate interactive validation flow before execution when the procedure requires seeded rows, active job state, or controlled write testing.

## Quick Start

### If user has query logs available:
1. **Load** `agents/01-inventory.md` — build prioritized object list
2. **Load** `agents/02-test-generation.md` — use log-driven path
3. **Load** `agents/03-execution-harness.md` — execute both sides after applying any required seed profile and readiness checks
4. **Load** `agents/05-diff.md` — diff and classify
5. **Load** `agents/07-reporting.md` — generate sign-off

### If user has NO query logs:
1. **Load** `agents/01-inventory.md` — build prioritized object list
2. **Load** `agents/02-test-generation.md` — use no-log harness generation path
3. Deliver paired SQL harness files or scenario metadata for source and target execution
4. Apply seed profiles and readiness checks before executing stateful procedures
5. **Load** `agents/05-diff.md` → **Load** `agents/07-reporting.md`

### If user wants to fix a specific failing procedure:
* **Load** `agents/06-repair.md` directly

### If user wants a migration readiness report:
* **Load** `agents/07-reporting.md` directly

### If user wants a client-ready PowerPoint report:
* Run `scripts/generate_migration_report.py` — see **PowerPoint Report** section below

## Key References

* **Load** `references/test-catalog-schema.md` — test case data model
* **Load** `references/mismatch-taxonomy.md` — mismatch classification guide
* **Load** `references/normalization-rules.md` — type and format normalization rules
* **Load** `references/harness-templates.md` — ready-to-run SQL harness templates
* **Load** `references/sign-off-criteria.md` — production readiness checklist

## Scope

### MVP (Phase 1)
* Top 20 business-critical stored procedures
* Read-only and controlled-write procedures
* Single directly comparable result set for reader procedures
* Batch and wrapper procedures use contract-based validation where direct result-set parity is not the primary validation method
* Row count + row-level diff
* Output parameter comparison
* Side-effect row count comparison
* Views as first-class testable objects
* Alternate interactive flow for ETL and DML procedures that require seeded data or rollback-based execution

### Phase 2 (deferred)
* Multi-result-set procedures
* Highly dynamic SQL (heavy EXEC sp_executesql patterns)
* Concurrency-heavy procedures
* Large-scale transaction replay
* Performance certification

## Procedure validation modes

Before executing parity tests, classify each procedure as one of:

* `reader`
* `batch`
* `wrapper`
* `unsupported`

### Comparison mode by object type

Use:

* `rowset` for views and reader procedures
* `contract` for batch and wrapper procedures
* `excluded` for unsupported patterns

### Contract-based validation for batch procedures

For batch and stateful procedures, validate using prerequisite state and post-execution evidence rather than direct result-set parity alone.

Examples of contract checks:

* prerequisite rows exist
* procedure executes successfully
* expected status transition occurs
* expected rows are inserted or updated
* expected queue, log, or audit rows are created
* expected business aggregates or key counts match

Do not require direct result-set parity for procedures whose main purpose is side effects or operational state changes.

## Shared metadata inputs and outputs

**Canonical shared directory:** user-provided shared working directory

Validation scripts read `SHARED_DIR` (or `MSSQL_SPG_SHARED_DIR` as fallback). Do not assume a user-specific local path. The user can set it before running:
```bash
export MSSQL_SPG_SHARED_DIR="/path/to/shared"
export SHARED_DIR="$MSSQL_SPG_SHARED_DIR"
```

When used in the end-to-end orchestration flow, this skill should consume:

* `shared/object_inventory.json`
* `shared/seed_profiles.yaml`
* `shared/load_manifest.json`
* `shared/load_summary.json`
* `shared/run_manifest.json`

This skill should produce:

* `shared/validation_registry.json`
* `shared/assertion_bundles.yaml`
* `shared/parameter_templates.yaml`
* `shared/verdict_rules.yaml`

### validation_registry.json

Contains:

* object name
* object type
* procedure family
* scenario id
* comparison mode
* seed profile reference
* assertion bundle reference
* parameter template reference
* execution gate policy where stateful procedures require prerequisite setup before invocation
* write validation policy for DML-sensitive procedures
* rollback wrapper policy for procedures executed under controlled-write validation

### seed_profiles.yaml

This file is generated upstream and consumed here as an execution plan, not as descriptive metadata only.

Expected fields include:

* object scope
* procedure family
* `prereq_mssql_sql`
* `prereq_spg_sql`
* `readiness_checks_mssql`
* `readiness_checks_spg`
* `parameter_bindings`
* `cleanup_mssql_sql`
* `cleanup_spg_sql`
* expected prerequisite state notes
* optional minimal write seed SQL for controlled DML validation
* optional transaction wrapper hints for rollback-safe execution

### assertion_bundles.yaml

Contains:

* pre-check SQL
* execution templates
* post-check SQL
* side-effect assertions
* aggregate assertions

### parameter_templates.yaml

Contains:

* reusable parameter sets for scenarios
* parameter defaults only when runnable values cannot be derived from seed data
* scenario-specific bindings that should take precedence over generic typed `NULL`

### verdict_rules.yaml

Contains verdict definitions and pass-rate inclusion rules.

## Seed profile execution and gating

Before executing any stateful or contract-based procedure, the validator must:

1. Resolve the scenario from `validation_registry.json`
2. Load the referenced seed profile from `seed_profiles.yaml`
3. Execute `prereq_mssql_sql` on SQL Server if source-side runnable state is required
4. Execute `prereq_spg_sql` on Snowflake Postgres if target-side runnable state is required
5. Run `readiness_checks_mssql`
6. Run `readiness_checks_spg`
7. Proceed to procedure execution only if the readiness checks pass on the side being validated

If the readiness checks fail:

* do not execute the procedure blindly
* classify the result as `FAIL_MISSING_PREREQ`
* exclude it from converter-quality pass rate

If the seed profile is present but its executable setup fails because of harness, script, or binding issues:

* classify the result as `FAIL_HARNESS`
* exclude it from converter-quality pass rate

Cleanup should run after execution when safe and deterministic, using `cleanup_mssql_sql` and `cleanup_spg_sql`.

## Parameter handling rules

For stateful procedures:

* use `parameter_bindings` from `seed_profiles.yaml` first
* then use scenario-specific values from `parameter_templates.yaml`
* use sampled real values when log-driven test generation provides them
* do not default to typed `NULL` if runnable seeded values exist
* do not force procedures into known error paths when prerequisite state can be established from seed metadata

For procedures whose prior failures are caused by missing active job or log state, the validator must prefer prerequisite setup and readiness gating over direct invocation with generic `NULL` parameters.

## Alternate interactive flow for ETL and DML validation

Use the following alternate flow for procedures or functions that are not safe to validate as simple read-only executions.

### Case 1: `SPG_ERROR` with active job state exhausted on SPG

If the failure indicates `SPG_ERROR` caused by exhausted or missing active job state on SPG, the validator must not immediately classify it as a conversion defect.

Instead, the validator must ask the user whether ETL and DML procedures or functions should be validated, because validation requires inserting or creating test data.

Use this prompt pattern:

* This object requires ETL or DML-style validation and needs test data or active job state to be created before execution. Do you want me to create the required data and run validation?

If the user answers yes:

* create the minimum valid prerequisite data needed to execute the object
* create matching runnable state in both MSSQL and SPG when parity requires both sides to be executable
* re-run readiness checks
* execute the validation using the seeded data
* record clearly that the object was validated through controlled write-path testing
* preserve any generated evidence needed for post-check side-effect comparison

If the user answers no:

* do not execute the object
* classify the result as `SKIPPED_USER_DECLINED_DML`
* record that validation was skipped because it required data creation or inserts

### Case 2: `SKIPPED_31`

If an object is classified as `SKIPPED_31`, the validator must ask the user whether they want to run it as part of validation and must clearly warn that the test may update data in both MSSQL and SPG.

Use this prompt pattern:

* This procedure was previously skipped because it performs DML and may update data in both MSSQL and SPG. Do you want me to run it as part of validation using a transaction wrapper and rollback?

If the user answers yes:

* create a wrapper execution path in both environments
* begin a transaction
* run the DML procedure or function
* capture outputs, side effects, row counts, and any required assertion evidence
* roll back the transaction
* compare observed behavior across MSSQL and SPG
* classify using the controlled-write verdict taxonomy

If the user answers no:

* keep the object skipped
* classify the result as `SKIPPED_USER_DECLINED_DML`
* record that the object was intentionally not executed because it can update data in both environments

### Controlled-write execution rules

For all alternate-flow DML or ETL validation:

* prefer the smallest valid seed data set that exercises the intended path
* use seed metadata first if a seed profile exists
* use transaction wrappers with rollback whenever the procedure can be safely executed inside an external transaction
* if a procedure commits internally and cannot be safely wrapped, warn the user before execution and require explicit approval
* separate controlled-write validation outcomes from standard read-only parity results in reports
* store enough pre-check and post-check evidence to prove that rollback or cleanup succeeded

## Execution classification rules

Use these execution rules for stateful families such as ETL or job-driven procedures:

* if prerequisite state is missing and can be seeded from the profile, seed it before execution
* if prerequisite state is missing and no executable seed exists, classify as `FAIL_MISSING_PREREQ`
* if both MSSQL and SPG fail because live business state is absent but the failure is logically equivalent, do not classify as `FAIL_CONVERSION`
* if both sides fail only because the harness supplied unrealistic parameter values such as typed `NULL` in place of runnable inputs, classify as `FAIL_HARNESS`
* if controlled-write validation succeeds after creating prerequisite data, classify as `PASS_DML_VALIDATION`
* if controlled-write validation fails only on SPG after equivalent seeded execution, classify as `FAIL_CONVERSION`
* if the user declines a required write-path execution, classify as `SKIPPED_USER_DECLINED_DML`

Missing active job, active job log, current step, queue state, or equivalent process-control state should be treated as prerequisite-state issues, not converter defects.

## Verdict taxonomy

Use the following verdicts:

* `PASS`
* `FAIL_DATA`
* `FAIL_CONVERSION`
* `FAIL_MISSING_PREREQ`
* `FAIL_HARNESS`
* `BOTH_FAILED_SOURCE_DEFECT`
* `EXPECTED_UNSUPPORTED`
* `PASS_DML_VALIDATION`
* `SKIPPED_USER_DECLINED_DML`
* `WRITE_VALIDATION_FAILED`

Exclude these from converter-quality pass rate:

* `FAIL_MISSING_PREREQ`
* `FAIL_HARNESS`
* `BOTH_FAILED_SOURCE_DEFECT`
* `EXPECTED_UNSUPPORTED`
* `SKIPPED_USER_DECLINED_DML`

## Python Execution Scripts

For live validation against real databases, use the scripts in `scripts/`:

```bash
# Set credentials
export MSSQL_PASSWORD='your_sa_password'
export SPG_HOST='yourhost.aws.postgres.snowflake.app'
export SPG_PASSWORD='your_spg_password'

# Run full validation
python3 scripts/validate_batch.py # views
python3 scripts/mssql_proc_executor.py # MSSQL procedures
python3 scripts/spg_proc_executor.py # SPG procedures (reads shared params)
python3 scripts/compare_proc_outputs.py # compare + write audit records

# Generate Markdown report (after validation runs)
python3 scripts/generate_validation_markdown.py \
 --out-dir "/path/to/output" \
 --client "Project Name"
```

See `scripts/README.md` for full documentation.

When used in the orchestration flow, the execution harness must consume:

* `shared/validation_registry.json`
* `shared/assertion_bundles.yaml`
* `shared/parameter_templates.yaml`
* `shared/seed_profiles.yaml`

The execution harness must apply prerequisite seed SQL and readiness checks before invoking contract-based procedures.

For alternate-flow DML validation, the execution harness must also support:

* creating minimal runnable prerequisite data
* prompting before write-path execution
* wrapping eligible DML tests in transaction + rollback on both sides
* recording rollback-safe validation evidence separately from standard parity execution

### Key Technical Patterns (learned from real migration testing)

| Pattern | Details |
|---------|---------|
| `autocommit=True` on psycopg2 | Required for SPG procedures that call COMMIT/ROLLBACK internally. Without it: `invalid transaction termination`. |
| Shared param sampling | MSSQL executor samples real data and saves to `/tmp/shared_sampled_params.json`. SPG executor loads and reuses identical values for valid comparison. |
| MSSQL typed NULLs | `DECLARE @_p0 INT = NULL; EXEC proc @param=@_p0` — CAST inline doesn't work in named param position. Use only when a seed profile or parameter template does not provide runnable values. |
| SPG typed NULLs | `param_name => NULL::integer` — named parameter syntax with type cast. Use only when a seed profile or parameter template does not provide runnable values. |
| PROCEDURE vs FUNCTION | PostgreSQL PROCEDURE cannot return result sets via CALL. Procedures that return SELECT results must be migrated as `CREATE FUNCTION ... RETURNS TABLE(...)`. |
| BOOL_INT_MISMATCH | SQL Server BIT columns migrated as INTEGER in Postgres. WHERE clauses using `WHERE bitcol` must become `WHERE intcol = 1`. |
| `call_no_resultset` strategy | When CALL succeeds but returns no columns, executor attempts SELECT * FROM func() fallback, then extracted SELECT. If all fail, marks as `SPG_NO_RESULTSET`. |
| Seed-profile execution gate | Stateful procedures must not run until prerequisite SQL from `seed_profiles.yaml` has been applied and readiness checks have passed. |
| Missing active job or log state | Missing active job, active job log, or equivalent process-control state should be classified as `FAIL_MISSING_PREREQ`, not `FAIL_CONVERSION`. |
| Harness-induced `NULL` failure | If the harness injects typed `NULL` where runnable seeded values exist, classify the outcome as `FAIL_HARNESS`, not a migration defect. |
| Controlled write validation | For DML-sensitive procedures, ask before execution, seed only minimum required data, capture behavior, and roll back when the procedure can be executed inside a wrapper transaction. |
| Non-wrapper-safe procedures | If the procedure performs internal COMMIT/ROLLBACK or cannot be safely wrapped, require explicit approval before execution and classify separately from read-only parity. |
| **`par_` prefix convention** | Some PG converters add a `par_` prefix to all procedure parameters (e.g., MSSQL `@id` → SPG `par_id`). The parameter name normalizer (`strip_p`) must strip both `par_` (4 chars) and `p_` (2 chars) before comparing. Never hardcode only one prefix variant. The `full_validation.py` `strip_p()` function must be: `if n.startswith('par_'): return n[4:]` then `if n.startswith('p_'): return n[2:]` then `return n`. |
| **OUT parameters from result-set conversion** | When the PG converter migrates a result-set-returning procedure, it adds `OUT` parameters to represent the result set columns (since Postgres procedures cannot return result sets directly). Always filter `get_spg_params()` to `IN` mode only (`parameter_mode = 'IN'`) when comparing parameter signatures. Including `OUT` parameters inflates the SPG parameter count and causes every such procedure to fail with `PARAM_COUNT` mismatch. |
| **psycopg2 transaction recovery** | If a SPG sample query fails (e.g., column name with spaces, type cast error), the psycopg2 connection enters an aborted-transaction state. All subsequent queries on the same connection will fail with `current transaction is aborted`. Always call `pc.rollback()` in the `except` block of any per-table or per-object query loop before continuing to the next iteration. |

### Audit Tables (SPG)

All validation runs are persisted in SPG:

```sql
SELECT * FROM validation.v_run_summary ORDER BY run_number DESC;
SELECT * FROM validation.validation_result WHERE run_number = <n>
 AND test_verdict NOT IN ('SKIPPED','PASS') ORDER BY test_verdict, object_name;
```

## PowerPoint Report — Client Delivery

`scripts/generate_migration_report.py` generates a Snowflake-branded `.pptx` directly from live validation data.
Results are pulled from `validation.validation_result` and `validation.validation_run` in SPG at runtime — every run produces a fresh, accurate deck.

### Slide Structure (27 slides, consistent every run)

| # | Slide | Content |
|---|-------|---------|
| 1 | Cover | Client name, author, date — parametric |
| 2 | Validation Methodology | What was tested + how (2-column layout) |
| 3 | Migration at a Glance | 4 KPI stat callouts (objects, pass rate, schemas) |
| 4–5 | Object Count by Schema + Type | MSSQL / SPG / Passed / Failed / Pass% table |
| 6 | Pass Rate Visual | Horizontal progress bars per schema + type |
| 7 | Failure Categories | 3-column breakdown: Missing / SPG Error / Both Failed |
| 8 | Remediation Priorities | Top 5 fixes ranked by impact (chevron pattern) |
| 9 | **APPENDIX** | Dark navy chapter divider |
| 10–26 | Failed Object Details | Paginated tables per schema (api → dbo → stg) |
| 27 | Thank You | Closing slide |

### Usage

```bash
cd ~/.snowflake/cortex/skills/mssql_spg_migration_validation_testing/scripts

python3 generate_migration_report.py \
 --client "Client Name" \
 --author "Your Name" \
 --spg-host "your_spg_host" \
 --spg-password "your_spg_password" \
 --mssql-host "your_mssql_host" \
 --mssql-port "your_mssql_port" \
 --mssql-user "your_mssql_user" \
 --mssql-password "your_mssql_password" \
 --mssql-db "YourDatabase" \
 --run-numbers "1,2,3"
```

Or via environment variables:

```bash
export SPG_HOST="your_spg_host"
export SPG_PASSWORD="your_spg_password"
export MSSQL_HOST="your_mssql_host"
export MSSQL_PORT="your_mssql_port"
export MSSQL_USER="your_mssql_user"
export MSSQL_PASSWORD="your_mssql_password"
export MSSQL_DATABASE="YourDatabase"
export CLIENT_NAME="Client Name"
export AUTHOR="Your Name"

python3 generate_migration_report.py
```

Output saves to `~/Google Drive/My Drive/` or `~/Downloads/` if Google Drive Desktop is not installed.
Filename format: `Migration_Validation_{ClientName}_{YYYYMMDD}.pptx` — no spaces or commas.

### What Data Is Pulled Live

| Source | What |
|--------|------|
| MSSQL `sys.objects` | Actual object counts by schema + type (# MSSQL column) |
| SPG `pg_class` + `pg_proc` | Actual deployed object counts (# SPG column) |
| `validation.validation_result` | Pass / fail / error per object |
| `validation.validation_run` | Run metadata (date, totals) |
| `validation.v_run_summary` | Aggregated pass/fail per run |

### Requirements

```bash
pip install python-pptx psycopg2-binary pymssql
```

Snowflake template must exist at one of:

* `./templates/snowflake_template.pptx`
* `~/.snowflake/cortex/skills/pptx/snowflake_template.pptx`

## Positioning

This skill is:

> Agentic two-sided procedure parity testing for MSSQL to Snowflake Postgres

It is not generic SnowConvert verification for Snowflake SQL. The focus is on behavioral equivalence between running SQL Server and running Snowflake Postgres for the same business operation.