#!/usr/bin/env python3
"""
run_validation_realization.py
Full validation runner for RealizationDB -> SPG migration.
Credentials embedded to avoid shell escaping issues with special chars.
"""
import os, sys, time

# ── Set all credentials as env vars ──────────────────────────────────────────
os.environ['MSSQL_HOST']     = '127.0.0.1'
os.environ['MSSQL_PORT']     = '1433'
os.environ['MSSQL_USER']     = 'sa'
os.environ['MSSQL_PASSWORD'] = '**REDACTED**'
os.environ['MSSQL_DATABASE'] = 'RealizationDB'
os.environ['SPG_HOST']       = 'bectnuwiyna7vfjiqb3pmp5wum.sfsenorthamerica-rkhandhadia-aws1.us-east-1.aws.postgres.snowflake.app'
os.environ['SPG_USER']       = 'snowflake_admin'
os.environ['SPG_PASSWORD']   = '**REDACTED-ROTATE-NOW**'
os.environ['SPG_DATABASE']   = 'postgres'
os.environ.setdefault('VALIDATION_OUTPUT_DIR', os.path.join(os.getcwd(), 'validation_output'))
os.environ['VALIDATION_SKIP_WRITES'] = 'false'

SCRIPTS_DIR = os.path.expanduser('~/.snowflake/cortex/skills/mssql_spg_migration_validation_testing/scripts')
sys.path.insert(0, SCRIPTS_DIR)

os.makedirs(os.environ['VALIDATION_OUTPUT_DIR'], exist_ok=True)

# ── Import config after env vars are set ────────────────────────────────────
from config import MSSQL_CONF, SPG_CONF, OUTPUT_DIR, check_required
check_required()

import validation_db as vdb

print("=" * 70)
print("MSSQL -> Snowflake Postgres — Migration Validation")
print(f"  Source : {MSSQL_CONF['database']} @ {MSSQL_CONF['server']}:{MSSQL_CONF['port']}")
print(f"  Target : {SPG_CONF['dbname']} @ {SPG_CONF['host'][:55]}")
print(f"  Output : {OUTPUT_DIR}")
print("=" * 70)

# ── Step 0: Ensure validation schema ─────────────────────────────────────────
print("\nEnsuring validation schema in SPG...")
vdb.ensure_schema_exists()
print("Validation schema OK")

start = time.time()

# ── Step 1: Triggers ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 1: TRIGGER VALIDATION")
print("=" * 70)
from validate_triggers import main as run_triggers
run_triggers()

# ── Step 2: Views ─────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: VIEW VALIDATION")
print("=" * 70)
from validate_batch import main as run_views
from run import _write_view_results
results, totals = run_views()
_write_view_results(results, totals)

# ── Step 3: Procedures/Functions ─────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: PROCEDURE / FUNCTION VALIDATION — MSSQL side")
print("=" * 70)
from mssql_proc_executor import main as run_mssql_procs
run_mssql_procs()

print("\n" + "=" * 70)
print("STEP 3b: PROCEDURE / FUNCTION VALIDATION — SPG side")
print("=" * 70)
from spg_proc_executor import main as run_spg_procs
run_spg_procs()

print("\n" + "=" * 70)
print("STEP 3c: COMPARING OUTPUTS")
print("=" * 70)
from compare_proc_outputs import main as compare_outputs
compare_outputs()

elapsed = time.time() - start
print(f"\n{'=' * 70}")
print(f"VALIDATION COMPLETE in {elapsed:.0f}s")
print(f"Results at: {OUTPUT_DIR}")
print("Query audit tables:")
print("  SELECT * FROM validation.v_run_summary ORDER BY run_number DESC;")
print("=" * 70)
