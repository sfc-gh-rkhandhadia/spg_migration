---
name: mssql-spg-orchestrator
description: "Thin orchestration layer for MSSQL to Snowflake Postgres realization, load, and validation. Use when the user wants an end-to-end DDL-to-SPG validation workflow across multiple standalone skills without merging them."
---

# MSSQL to SPG End-to-End Orchestrator

## Purpose

Coordinate the full workflow across three standalone skills:

* `/mssql-ddl-realization`
* `/mssql-spg-load`
* `/mssql_spg_migration_validation_testing`

This skill is a wrapper only. It does not replace the internal logic of any of the three skills.

## Workflow

1. **PRE-FLIGHT** (when SPG target is known): Run `mssql-spg-load`'s constraint
   discovery script to emit `spg_column_constraints.json` into the shared workspace.
   Pass this file to `build_dep_graph.py` via `--constraints-file` in step 2 so that
   the seeder generates semantically correct values (e.g. `'Y'`/`'N'` for boolean-flag
   columns) from the start.  When SPG is not yet available, skip this step — realization
   runs standalone and generates best-effort values.
2. Run `/mssql-ddl-realization`
3. Run `/mssql-spg-load`
4. Run `/mssql_spg_migration_validation_testing`
5. Assemble run metadata and final summary

## Start modes

Use this orchestrator when the starting point is any of:

* raw MSSQL DDL
* a DDL folder
* an archive
* an existing MSSQL environment

If the user explicitly wants to use an existing MSSQL environment, skip disposable source deployment. Invoke `/mssql-ddl-realization` only as needed for semantic inspection, object inventory, or seed-profile generation.

## Shared metadata contract

**Shared workspace root:** configured externally and passed through a generic environment variable.

Set before running any skill:
```bash
export WORKFLOW_SHARED_DIR="/path/to/shared-workflow"
```

All skills should resolve the shared workspace from `WORKFLOW_SHARED_DIR`. Do not hardcode an absolute fallback path in this skill. If `WORKFLOW_SHARED_DIR` is not set, stop and request the shared workspace location before continuing.

The flow should exchange these files relative to the shared workspace root:

* `object_inventory.json`
* `seed_profiles.yaml`
* `spg_column_constraints.json`  (written by pre-flight; consumed by build_dep_graph.py)
* `load_manifest.json`
* `load_summary.json`
* `validation_registry.json`
* `assertion_bundles.yaml`
* `parameter_templates.yaml`
* `verdict_rules.yaml`
* `run_manifest.json`

## Ownership model

### `/mssql-ddl-realization`

Owns:

* `object_inventory.json`
* `seed_profiles.yaml`

### `/mssql-spg-load`

Owns:

* `spg_column_constraints.json`  (pre-flight step; optional when SPG not yet available)
* `load_manifest.json`
* `load_summary.json`

### `/mssql_spg_migration_validation_testing`

Owns:

* `validation_registry.json`
* `assertion_bundles.yaml`
* `parameter_templates.yaml`
* `verdict_rules.yaml`

### `mssql-spg-orchestrator`

Owns:

* `run_manifest.json`
* workflow ordering
* final summary

## Routing rules

* If source realization metadata is missing, return to `/mssql-ddl-realization`
* If load metadata is missing, return to `/mssql-spg-load`
* If validation metadata is missing, return to `/mssql_spg_migration_validation_testing`
* Do not invent missing metadata inline

## Execution rules

* Do not proceed to `/mssql-spg-load` until required realization metadata exists
* Do not proceed to `/mssql_spg_migration_validation_testing` until load completes successfully
* If any required shared file is missing, route back to the owning skill
* Do not classify missing metadata as a validation failure

## Guardrails

* Do not hardcode workload-specific SQL in this skill
* Do not hardcode environment-specific directories or environment variable names beyond the generic shared workspace contract
* Do not merge the three skills into one monolith
* Do not duplicate realization logic, load logic, or validation logic
* Use this skill only to coordinate ordering and metadata handoff

## Success criteria

* shared metadata is produced by the correct owning skills
* load completes successfully before validation begins
* validation runs with the correct metadata handoff
* the final summary reflects realization, load, and validation outcomes without duplicating internal skill logic