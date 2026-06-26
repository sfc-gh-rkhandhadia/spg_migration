---
name: mssql-ddl-realization
description: "Given either raw MSSQL DDL supplied by a customer or an existing MSSQL environment, create a complete dependency object graph across constraints, tables, views, functions, and procedures, inspect filter and branch logic inside the code, and generate a small but valid and consistent application dataset so that every in-scope row-producing view, function, and reader-style procedure returns at least one row set, while stateful procedures have runnable prerequisite state established for downstream validation."
---

# MSSQL DDL Realization and Semantic Data Generation

## Description

Given either raw MSSQL DDL supplied by a customer or an existing MSSQL environment, create a complete dependency object graph across constraints, tables, views, functions, and procedures, inspect filter and branch logic inside the code, and generate a small but valid and consistent application dataset so that every in-scope row-producing view, function, and reader-style procedure returns at least one row set, while stateful procedures have runnable prerequisite state established for downstream validation.

The goal of this skill is not just referential integrity. The goal is to create semantically usable application data that satisfies joins, filters, conditional branches, and alternate execution flows while keeping execution fast and the generated dataset small.

Default data volume target: no more than 200 generated rows across the realized witness dataset unless the user explicitly overrides it.

## Dependency model

This skill has no required dependency on any other skill.

It must be able to start directly from:

- raw customer-provided MSSQL DDL
- a folder of SQL files
- an archive containing DDL
- an existing MSSQL environment

If outputs from other skills already exist, they may be used as optional accelerators, but they are never required.

## When to use

Use this skill when the user wants to:

- deploy customer MSSQL DDL into a disposable SQL Server instance
- analyze dependencies across schema objects
- inspect views, functions, and procedures for filters and branch conditions
- generate coherent synthetic application data
- ensure every view, function, and procedure returns rows where appropriate
- build a semantic witness dataset for demos, migration prep, testing, or validation
- generate execution-ready prerequisite state for downstream procedure validation
- validate whether a schema is semantically realizable, not just syntactically deployable

## When not to use

Do not use this skill when the user only wants to:

- split DDL files without execution
- perform static complexity analysis only
- convert SQL dialects without runtime realization
- load production data
- benchmark production performance
- validate exact business correctness against source production systems

## Inputs supported

- raw MSSQL DDL as files or text
- a folder or archive containing DDL
- an existing MSSQL environment
- optional prioritized list of views, functions, or procedures
- optional row cap override
- optional rules for masking, excluded columns, or special seed values
- optional object inclusion or exclusion rules

## Core output

This skill should produce:

- a normalized object inventory
- a dependency object graph
- a deployment result
- a semantic seed plan
- a generated witness dataset capped at 200 rows by default
- execution-ready seed profiles for downstream validation
- validation results for each in-scope row-producing object
- a final report listing:
- validated objects
- partially validated objects
- failed objects
- unsupported objects
- unresolved blockers
- witness chains and branch coverage used to make objects return rows

## Shared handoff outputs

Use a configurable shared output directory, read from `SHARED_OUTPUT_DIR`. If the variable is unset, default to a workspace-relative shared folder such as `./shared`.

Example:

```bash
export SHARED_OUTPUT_DIR="${SHARED_OUTPUT_DIR:-./shared}"
mkdir -p "$SHARED_OUTPUT_DIR"
```

When this skill is used as part of the MSSQL to SPG orchestration flow, it should emit the following shared metadata:

- `object_inventory.json`
- `seed_profiles.yaml`

Optional additional output:

- `semantic_requirements.yaml`

### object_inventory.json

This file should contain:

- workload name
- schemas
- object names
- object types
- initial procedure family hints where obvious from code inspection

### seed_profiles.yaml

This file must be execution-ready, not just descriptive.

It should contain:

- semantic witness seed scenarios
- prerequisite business state for row-producing objects
- branch-aware seed requirements
- runtime bindings needed by downstream load or validation steps
- procedure family or validation mode hints where known
- executable prerequisite SQL for MSSQL when state must be established before execution
- executable prerequisite SQL for SPG when equivalent target-side state must be established before execution
- readiness checks for MSSQL and SPG
- cleanup SQL for MSSQL and SPG
- parameter derivation rules so downstream validation does not default to typed `NULL` when runnable inputs can be generated

A recommended profile shape is:

```yaml
seed_profiles:
 <scenario_id>:
  object_scope:
   * "<schema>.<object_name>"
  procedure_family: "reader|batch|wrapper|unsupported"
  description: "<what business state this scenario establishes>"

  prereq_mssql_sql:
   * "INSERT ..."
   * "UPDATE ..."

  prereq_spg_sql:
   * "INSERT ..."
   * "UPDATE ..."

  readiness_checks_mssql:
   * "SELECT COUNT(*) AS cnt FROM ... WHERE ..."
  readiness_checks_spg:
   * "SELECT COUNT(*) AS cnt FROM ... WHERE ..."

  parameter_bindings:
   <param_name>: "<seeded value, derived value, or runtime token>"

  cleanup_mssql_sql:
   * "DELETE ..."
  cleanup_spg_sql:
   * "DELETE ..."

  expected_state:
   * "<state that must exist before validation execution>"

  notes:
   * "<branch or business-rule notes>"
```

## Required behavior

This skill must:

- build a dependency graph from constraints, tables, views, functions, and procedures
- inspect code-level filtering conditions and branch predicates
- add those conditions to the dependency graph as semantic requirements
- generate data that satisfies both FK-style paths and non-FK filter paths
- account for alternate flows where procedures, functions, or views may rely on conditions that do not naturally align with straightforward FK-consistent row creation
- keep the generated dataset small and fast, with a default maximum of 200 rows
- create valid, consistent application-style data rather than isolated random rows
- prove success by making each in-scope row-producing object return rows where appropriate and by establishing runnable prerequisite state for downstream validation when direct row-return is not the right success criterion
- generate execution-ready `seed_profiles.yaml` entries for stateful procedures and ETL-style flows
- emit prerequisite SQL, readiness checks, cleanup SQL, and parameter bindings whenever the downstream validator would otherwise have to guess or inject generic `NULL` values
- separate base witness dataset generation from procedure-specific runtime state generation when those are logically different

## Guardrails

- Do not assume that deployable schema means semantically usable schema.
- Do not assume FK validity alone is enough.
- Do not generate large random datasets.
- Do not generate more than 200 rows by default unless the user explicitly asks for more.
- Do not mark an object as validated unless it actually returns rows.
- Do not mark a scalar function as validated if it returns NULL — a NULL return means the function's internal filter conditions are not satisfied by the seed data.
- Do not rely on Phase B minimal-fill rows to satisfy semantic flag requirements — verify the actual flag value against the function's `WHERE` clause.
- Do not attempt to pass Table-Valued Parameters via pymssql — pymssql cannot marshal TVP args. Use `subprocess + sqlcmd` with a `DECLARE`/`INSERT`/`EXEC` batch instead.
- Do not skip the join consistency pre-check — seed data that satisfies declared FK constraints can still have broken join-column values for non-FK columns used as join keys in views and procedures.
- Do not stop at table-level seeding if filters or branch logic still produce empty results.
- Do not ignore alternate branches just because they are awkward or appear to violate the most obvious FK path.
- Do not emit descriptive seed profiles only. For stateful procedures, provide execution-ready prerequisite SQL or explicitly mark the missing executable logic as a blocker.
- Do not rely on downstream validation to infer missing prerequisite inserts from prose.
- Do not let downstream validators default to typed `NULL` for parameters if this skill can derive runnable values from seed data.
- Do not fabricate unsupported behavior. Report blockers clearly.
- Do not hardcode user-specific paths, local directories, or machine-specific absolute file locations.

## Workflow

### Step 1: Intake

Determine whether the starting point is:

- raw DDL
- a DDL folder or archive
- an existing MSSQL environment

Normalize object names, schemas, and object types. Build a canonical inventory of:

- tables
- constraints
- views
- scalar functions
- table-valued functions
- stored procedures
- triggers if relevant to row creation or branch behavior

### Step 2: Build the dependency object graph

Build a dependency graph that includes more than simple schema edges.

Required graph edge types:

- table-to-table FK and constraint dependencies
- view-to-table and view-to-view dependencies
- function-to-table, function-to-view, and function-to-function dependencies
- procedure-to-table, procedure-to-view, and procedure-to-function dependencies
- join dependencies inferred from code
- filter dependencies inferred from `WHERE`, `JOIN`, `HAVING`, `CASE`, `EXISTS`, `NOT EXISTS`, `IN`, `NOT IN`, and similar predicates
- parameter-dependent branches
- alternate execution paths that can affect whether rows are returned
- prerequisite-state dependencies for stateful procedures, including job tables, log tables, queue tables, control rows, and status lookups

The graph must capture both:

- structural dependencies
- semantic row-return requirements
- execution prerequisites for downstream validation

Table-Valued Parameter detection: when building the graph, scan every stored procedure DDL for `@param schema.TypeName READONLY` declarations. These indicate User-Defined Table Type parameters. For each such parameter:

- record the UDT name and schema in the dependency graph
- look up column definitions in `sys.table_types`
- identify the best-matching source table by column overlap to use as the TVP data source at validation time
- mark the procedure as requiring sqlcmd-based invocation because pymssql cannot marshal TVP arguments

The TVP invocation pattern that must be generated at validation time:

```sql
DECLARE @param [schema].[TypeName];
INSERT INTO @param (<udt_cols>) SELECT TOP 1 <matching_cols> FROM [src_schema].[src_table];
EXEC [proc_schema].[proc_name] @param = @param;
```

### Step 3: Extract semantic row-return conditions

For every in-scope row-producing view, function, and procedure, inspect the code and identify the exact conditions that must be true for the object to return rows or become runnable.

For scalar functions specifically, read the entire function body and extract every predicate that filters the lookup, status, control, or reference table the function reads from. Treat these predicates as hard seed requirements: the witness dataset must contain at least one row satisfying each predicate.

Examples of generic predicate patterns include:

- active or enabled flags, such as `<active_flag_column> = 1`
- status-code filters, such as `<status_column> = 'ACTIVE'`
- date-effective filters, such as `<start_date_column> <= CURRENT_TIMESTAMP` and `<end_date_column> IS NULL`
- tenant, company, partition, or business-unit scoping predicates
- required non-NULL foreign keys or business identifiers

Also identify:

- join conditions that must be satisfiable
- filters that must evaluate true for at least one execution path
- parameter combinations that lead to non-empty results
- alternate branches that must be seeded separately
- flags, date windows, type codes, and lookup values that control visibility of rows
- soft-delete filters
- null and not-null requirements
- existence and anti-existence patterns
- prerequisite-state patterns that determine whether a procedure is runnable at all, such as active parent rows, current run-log rows, queue rows, pending work items, workflow-control rows, and status or control lookups

Each discovered condition must be attached to the dependency graph as one of the following:

- a structural dependency
- a seed requirement
- a branch requirement
- a runtime prerequisite
- a parameter-derivation rule

Examples in this step are illustrative only. The implementation must derive the actual columns, values, and predicates from the realized schema and object definitions rather than assuming specific flag names, table names, or status values.

### Step 4: Provision or connect

If starting from DDL:

- create a disposable MSSQL Docker instance
- deploy objects in practical dependency-aware order
- capture object creation failures and blockers

If starting from an existing environment:

- inventory the existing deployed objects
- validate that required objects exist and are usable for seeding and validation

### Step 5: Create the seed plan

Create a minimal semantic witness dataset plan.

The plan should:

- identify root entities
- identify all required downstream rows
- identify which filter values must be satisfied
- identify when a single happy-path chain is enough
- identify when alternate branch rows are needed
- identify when a stateful procedure needs prerequisite runtime state beyond the base witness dataset
- reuse keys and reference values consistently
- prefer the smallest dataset that still covers all in-scope row-producing objects

The default target is a compact dataset of no more than 200 rows total.

The seed plan must also define scenario-level execution intent for downstream validation:

- scenario id
- object scope
- prerequisite state type
- derived parameter values
- cleanup scope
- readiness check strategy

### Step 6: Generate data

Generate data in a controlled sequence:

- parent and root rows first
- dependent rows second
- bridge and lookup rows as needed
- branch-specific rows only when required to satisfy a filter or alternate path
- parameter-supporting rows where procedures or functions require specific inputs to return rows
- procedure-prerequisite rows where downstream validation requires runnable state instead of simple row-return

The generated data must aim for:

- referential coherence
- filter satisfaction
- branch coverage
- application-style consistency
- compactness

This is not bulk test data generation. It is witness dataset generation.

### Step 6b: Join consistency pre-check

After generating seed data and before running any validation, run a join consistency check across all inner joins used by views and stored procedures.

For every join pair `t1.col1 = t2.col2` extracted from in-scope objects:

1. Execute `SELECT COUNT(*) FROM t1 INNER JOIN t2 ON t1.col1 = t2.col2`
2. If count = 0, the join is broken — diagnose by sampling values from both sides
3. Automatically fix by updating the FK side to align with an existing value from the referenced side:

    if `t2.col2` is a PK column: `UPDATE t1 SET col1 = <val from t2.col2> WHERE col1 NOT IN (SELECT col2 FROM t2)`
     if `t1.col1` is a PK column: `UPDATE t2 SET col2 = <val from t1.col1> WHERE col2 NOT IN (SELECT col1 FROM t1)`
4. After updating, verify the join resolves to at least 1 row

This step catches seed data inconsistencies that are not covered by declared FK constraints.

Guardrail: do not proceed to validation if any join used by an in-scope object still resolves to 0 rows after the fix attempt. Report the broken join as a blocker.

### Step 6c: Generate execution-ready seed profiles

After generating the witness dataset, emit execution-ready `seed_profiles.yaml`.

For each stateful procedure family or scenario:

- generate `prereq_mssql_sql` that can establish runnable source-side state
- generate `prereq_spg_sql` that can establish equivalent runnable target-side state when downstream validation requires target-side setup
- generate readiness checks for both sides
- generate cleanup SQL for both sides
- generate parameter bindings from seeded rows
- record expected prerequisite state in business terms

For ETL-style procedures such as job-driven loaders, the profile must capture runnable state explicitly. Examples include:

- active job row exists
- active job log row exists
- current step row exists
- pending work rows exist
- status lookup rows use the exact active values expected by scalar functions

#### IDENTITY-safe INSERT generation

When generating `prereq_mssql_sql`, `prereq_spg_sql`, or any INSERT statement for a staging or prerequisite table, the generated script should query `sys.columns` at runtime to determine which columns have `is_identity=1` before building the INSERT column list.

Required pattern:

```python
def get_table_columns(schema, table):
    """Returns (non_identity_cols, identity_col, existence_col) from sys.columns."""
    rc, out = sqlcmd(f"""
    SELECT c.name + '|' + CAST(c.is_identity AS VARCHAR(1)) + '|' +
    CAST(CASE WHEN EXISTS(
        SELECT 1 FROM sys.index_columns ic
        JOIN sys.indexes i ON i.object_id=ic.object_id
         AND i.index_id=ic.index_id AND i.is_unique=1
        WHERE ic.object_id=c.object_id AND ic.column_id=c.column_id
    ) THEN 1 ELSE 0 END AS VARCHAR(1)) AS col_info
    FROM sys.columns c
    JOIN sys.objects o ON c.object_id=o.object_id
    JOIN sys.schemas s ON o.schema_id=s.schema_id
    WHERE s.name='{schema}' AND o.name='{table}' AND o.type IN ('U','V')
    ORDER BY c.column_id
    """)
    # parse pipe-delimited output: col_name|is_identity|in_unique_idx
    ...
    return non_identity_cols, identity_col, existence_col

def build_insert_mssql(schema, table, witness_vals, exist_col=None, exist_val=None):
    """Build an IDENTITY-safe T-SQL INSERT without including IDENTITY columns."""
    non_id_cols, _, auto_exist_col = get_table_columns(schema, table)
    insert_cols = [c for c in non_id_cols if c.lower() in witness_vals_lower]
    ...
    return f"IF NOT EXISTS({exist_clause}) INSERT INTO [{schema}].[{table}]({col_clause}) VALUES({val_clause});"
```

Rules:

- omit IDENTITY columns entirely from the INSERT column list and VALUES unless the user explicitly requires identity insert behavior
- for `IF NOT EXISTS`, prefer a non-IDENTITY business-key column over the IDENTITY column
- for SPG, use the same introspection result to exclude generated or serial target columns
- cache `get_table_columns()` results per `(schema, table)` pair to avoid repeated roundtrips

#### Scoped log entry check for job-log tables

This rule is generic in intent but must be implemented using the actual schema, status table, log table, key column, and active-row predicate for the environment being realized.

When generating prereq SQL that inserts into a job-log or run-log table, the `IF NOT EXISTS` or `WHERE NOT EXISTS` predicate must be scoped to the specific active parent status or job row, never to the entire log table.

Generic pattern:

```sql
DECLARE @active_status_id INT = (
  SELECT TOP 1 <status_id_column>
  FROM [<status_schema>].[<status_table>]
  WHERE <active_predicate>
  ORDER BY <status_id_column> DESC
);

IF @active_status_id IS NOT NULL AND NOT EXISTS (
  SELECT 1
  FROM [<log_schema>].[<log_table>]
  WHERE <log_fk_to_status> = @active_status_id
    AND <log_open_predicate>
)
INSERT INTO [<log_schema>].[<log_table>](...)
VALUES(@active_status_id, ...);
```

Non-generic anti-pattern:

```sql
IF NOT EXISTS (
  SELECT 1
  FROM [<log_schema>].[<log_table>]
  WHERE <log_open_predicate>
)
INSERT INTO [<log_schema>].[<log_table>](...) VALUES(@active_status_id, ...);
```

An unscoped check can be satisfied by open log entries belonging to prior or unrelated jobs, causing the insert to be skipped and leaving the current active job or status row without the required log entry.

The generated implementation should derive these placeholders from the realized schema:

- `<status_schema>.<status_table>`: the table that identifies the currently active or runnable job, batch, workflow, or status row
- `<status_id_column>`: the primary status or job identifier used to link into the log table
- `<active_predicate>`: the exact condition that defines the active parent row, derived from the realized schema and object logic rather than assumed flag names, literal values, or status-code conventions
- `<log_schema>.<log_table>`: the table that stores per-run or per-job log state
- `<log_fk_to_status>`: the foreign key or join column back to the active status or job row
- `<log_open_predicate>`: the exact condition that defines an open, current, or incomplete log row

Define the generated SQL as named constants in the seed script, but ensure the constant values are derived from schema inspection rather than from hardcoded table or column names.

Example constant pattern:

```python
ACTIVE_LOG_PREREQ_MSSQL = build_scoped_log_prereq_mssql(
    status_schema=status_schema,
    status_table=status_table,
    status_id_column=status_id_column,
    active_predicate=active_predicate,
    log_schema=log_schema,
    log_table=log_table,
    log_fk_column=log_fk_column,
    log_open_predicate=log_open_predicate,
)
```

If a different schema uses different object names but the same semantic pattern, this rule should still work once the placeholders are bound from metadata or code inspection.

#### Single witness data table

Define a single witness dataset structure that drives both live seeding and seed profile generation from the same source of truth.

The structure must be generic and derived from the realized schema, not from assumed schema names, table names, or column names.

Recommended pattern:

```python
WITNESS_DATA = [
    # (
    #   source_schema,
    #   source_table,
    #   witness_values,
    #   existence_column_override,
    #   existence_value_override,
    # )
    (
        resolved_schema,
        resolved_table,
        {
            resolved_business_key_column: resolved_business_key_value,
            resolved_reference_column: resolved_reference_value,
        },
        None,
        None,
    ),
]

for schema_name, table_name, vals, ecol, eval_ in WITNESS_DATA:
    seed(build_insert_mssql(schema_name, table_name, vals, ecol, eval_), table_name)

prereq_mssql = [ACTIVE_STATUS_PREREQ_MSSQL, ACTIVE_LOG_PREREQ_MSSQL]
for schema_name, table_name, vals, ecol, eval_ in WITNESS_DATA:
    prereq_mssql.append(build_insert_mssql(schema_name, table_name, vals, ecol, eval_))

prereq_spg = [ACTIVE_STATUS_PREREQ_SPG, ACTIVE_LOG_PREREQ_SPG]
for schema_name, table_name, vals, ecol, eval_ in WITNESS_DATA:
    _, id_col, _ = get_table_columns(schema_name, table_name)
    prereq_spg.append(
        build_insert_spg(
            schema_name,
            table_name.lower(),
            {k.lower(): v for k, v in vals.items()},
            id_col.lower() if id_col else None,
            ecol,
            eval_,
        )
    )
```

Requirements:

- derive `resolved_schema` and `resolved_table` from the realized object graph or deployment inventory
- derive witness columns from actual join keys, filter predicates, business keys, and parameter-binding needs
- prefer semantically meaningful witness values over arbitrary placeholders
- use the same `WITNESS_DATA` structure for both live seeding and generated prereq SQL so both execution paths stay consistent
- avoid hardcoding any schema-specific object names such as staging prefixes or domain-specific table names unless they were discovered from the realized environment at runtime

### Step 7: Handle alternate flows

Some procedures, functions, and views may contain conditions that are not satisfied by a normal FK-happy-path dataset.

Examples include:

- negative status checks
- exclusion predicates
- anti-joins
- special flag combinations
- alternate `CASE` branches
- date-effective logic
- branch-specific lookup values

The skill must account for these alternate flows even when the data required for those flows is not the most obvious continuation of the main FK chain.

If supporting one branch would break another branch, the skill should:

- create separate witness rows for each branch when possible
- keep branch rows minimal
- clearly document which rows support which object or branch

### Step 8: Validate row-return behavior

For each in-scope row-producing object:

- execute the view
- invoke the function
- invoke the procedure when safe and deterministic
- confirm that at least one row is returned where row-return is the correct validation target
- record the witness chain and branch conditions that made it work

For stateful procedures whose downstream validation depends on prerequisite state rather than direct row-return, validate that the skill can establish runnable state and emit executable prerequisite SQL and parameter bindings.

Scalar function validation rule: scalar functions must be validated by confirming they return a non-NULL value, not merely that they execute without error. A scalar function that executes successfully but returns NULL is classified as EMPTY and requires additional seed data to satisfy its internal filter conditions.

Specifically:

- inspect the function body for predicates that filter lookup, status, control, reference, or configuration tables
- ensure the witness dataset includes at least one row satisfying those exact predicate values in the referenced tables
- treat active flags, enabled flags, status codes, date-effective windows, tenant scopes, business-unit scopes, and required non-NULL business keys as possible hard validation requirements
- apply the same logic to any scalar function that reads from a table or view whose rows are filtered before the return value is derived

For views, TVFs, and row-producing procedures, validation must confirm that the returned rows come from a traceable witness path that satisfies the required joins, filters, and parameter combinations.

For stateful procedures, validation may succeed through runnable prerequisite-state establishment even when direct row-return is not the primary success criterion, but the emitted prerequisite SQL, readiness checks, cleanup SQL, and parameter bindings must be executable and traceable.

A validation result should include:

- object name
- object type
- execution outcome
- whether rows were returned for views and TVFs, whether a non-NULL value was returned for scalars, or whether runnable prerequisite state was established for stateful procedures
- key seed rows involved
- filters satisfied
- branch used
- derived parameters used, if applicable
- blocker reason if unsuccessful

Examples in this step are illustrative only. The implementation must derive the actual tables, predicates, parameter values, and success criteria from the realized schema and object definitions rather than assuming specific object names, flag names, or status values.

### Step 9: Produce final report

If this skill is part of the end-to-end MSSQL to SPG flow, persist shared handoff metadata for downstream steps.

Required outputs:

- `object_inventory.json`
- `seed_profiles.yaml`

These outputs are consumed by:

- `/mssql-spg-load`
- `/mssql_spg_migration_validation_testing`

Do not require downstream skills to rediscover semantic witness requirements that were already derived here.

The final report must clearly separate:

- validated
- partially validated
- failed
- unsupported

It must also show:

- total rows generated
- whether the effective row cap used for the run was respected
- which objects needed alternate branch seeding
- which objects required execution-ready prerequisite state
- which objects were satisfied by standard dependency chains
- which objects still need manual interpretation

## Row cap policy

The row cap should come from the user request or prompt context whenever it is provided explicitly.

The skill should:

- use the user-specified row cap when one is provided
- otherwise derive the intended row-volume constraint from the prompt or calling workflow context
- only fall back to an implementation default when no row-cap guidance is available from the user or prompt
- prefer fewer rows whenever possible
- reuse shared witness rows across multiple dependent objects
- avoid branch duplication unless necessary

If the effective row cap is unclear and row volume materially affects behavior, the skill should ask the user or calling workflow for the limit rather than silently assuming a fixed number.

If the skill cannot satisfy all in-scope row-producing objects within the effective row cap, it should:

- maximize coverage within the limit
- report uncovered objects
- explain which branches or filters caused the limit pressure

## Validation rules

An object is considered validated only if:

- it compiles or executes successfully
- it returns at least one row where row-return is the correct validation target
- the supporting seed rows are traceable
- the successful path is explainable through the dependency graph and seed plan

An object is considered partially validated if:

- it deploys or compiles
- some branches can be exercised
- but at least one required row-return path is unresolved
- or execution-ready prerequisite state can be described but not emitted as runnable seed SQL

An object is considered failed if:

- it cannot be deployed or executed
- or it still returns no rows after reasonable branch-aware seed generation
- or required runnable prerequisite state for downstream validation cannot be established

An object is considered unsupported if:

- it depends on dynamic behavior, external side effects, or other runtime patterns that cannot be safely or deterministically realized within the skill

## Testing the skill

### Goal of testing

Verify that the skill creates the right graph, the right witness data, the right execution-ready seed profiles, and the right row-return behavior quickly and repeatably.

### Minimum test set

Use a small MSSQL schema containing:

- a few parent-child tables
- at least one FK path
- at least one view with filters
- at least one function
- at least one procedure
- at least one branch or alternate flow that is not satisfied by the simplest FK-only dataset
- at least one stateful procedure that requires prerequisite runtime state

### Test phases

#### 1. Graph test

Confirm the graph includes:

- constraint edges
- object dependencies
- join conditions
- filter conditions
- branch conditions
- alternate flow requirements
- prerequisite-state dependencies

#### 2. Seed plan test

Confirm the seed plan:

- stays within the 200-row cap
- identifies witness rows correctly
- distinguishes happy-path rows from alternate-branch rows
- distinguishes base witness data from procedure prerequisite state
- does not rely only on FK relationships

#### 3. Seed profile execution test

Confirm `seed_profiles.yaml` contains executable content for stateful procedures:

- `prereq_mssql_sql`
- `prereq_spg_sql` where applicable
- readiness checks
- cleanup SQL
- parameter bindings

Confirm the emitted parameter bindings do not force downstream validation to default to typed `NULL` when runnable values exist.

#### 4. Execution test

Confirm every in-scope view, function, and procedure returns at least one row, or is explicitly classified as failed or unsupported.

For stateful procedures, confirm the skill emits runnable prerequisite-state setup even if direct row-return is not the primary validation target.

#### 5. Regression test

Re-run the skill against:

- raw DDL input
- existing environment input
- a schema with filters that require alternate rows
- a schema with ETL-style procedures that require active-job or active-log state

Confirm results are stable and repeatable.

### Pass criteria

The skill passes when:

- the dependency graph contains both structural and semantic edges
- the generated dataset stays within 200 rows by default
- each in-scope row-producing object returns rows or has a clear blocker classification
- execution-ready seed profiles are emitted for stateful procedures
- alternate branches are handled when required
- repeated runs produce consistent outcomes

## Example prompts

- Build a disposable SQL Server environment from this customer DDL and generate a witness dataset so every view and procedure returns rows.
- Use this existing MSSQL environment, inspect the code paths in views, functions, and procedures, and generate no more than 200 rows of consistent application data.
- Create a dependency graph from this DDL, include filtering conditions from the code, and seed data so each row-producing object has at least one end-to-end witness chain.
- Generate a compact semantic dataset for this SQL Server schema, including alternate branch rows when normal FK paths are not enough.
- Generate execution-ready seed profiles for stateful procedures so downstream MSSQL and SPG validation can apply prerequisite state before execution.

## Success criteria

The skill succeeds when:

- it accepts raw DDL or an existing environment directly
- it builds a dependency graph that includes code-level filter and branch logic
- it generates a compact, coherent witness dataset within the effective row cap defined by the user request, prompt context, or calling workflow
- it emits execution-ready `seed_profiles.yaml` for downstream validation
- it satisfies both straightforward dependency chains and alternate flows where needed
- every in-scope row-producing view, function, and reader-style procedure returns at least one row, or is explicitly classified with a blocker reason, while stateful procedures have runnable prerequisite state established for downstream validation
- the resulting report is clear enough to support downstream testing, migration prep, demos, or manual review

&nbsp;