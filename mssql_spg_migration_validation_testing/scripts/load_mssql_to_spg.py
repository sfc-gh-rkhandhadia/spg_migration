#!/usr/bin/env python3
"""Load data from MSSQL to SPG table-by-table using pymssql and psycopg2."""
import json
import sys
import uuid
import re
from pathlib import Path
from datetime import datetime

import pymssql
import psycopg2
import psycopg2.extras
psycopg2.extras.register_uuid()

MSSQL_HOST = "localhost"
MSSQL_PORT = 1434
MSSQL_USER = "sa"
MSSQL_PASS = "REDACTED_MSSQL_PASSWORD"
MSSQL_DB = "MENU_MANAGEMENT"

SPG_HOST = "your-spg-host.snowflakecomputing.app"
SPG_PORT = 5432
SPG_USER = "snowflake_admin"
SPG_PASS = "REDACTED_SPG_PASSWORD"
SPG_DB = "postgres"

SHARED_DIR = Path("/Users/rkhandhadia/Documents/Armtrack/shared-workflow")

inv = json.loads((SHARED_DIR / "object_inventory.json").read_text())

def mc():
    return pymssql.connect(server=MSSQL_HOST, port=MSSQL_PORT,
                           user=MSSQL_USER, password=MSSQL_PASS,
                           database=MSSQL_DB, timeout=60, login_timeout=10)

def sc():
    return psycopg2.connect(host=SPG_HOST, port=SPG_PORT, user=SPG_USER,
                            password=SPG_PASS, dbname=SPG_DB, sslmode="require")

# Connect
mconn = mc()
sconn = sc()
sconn.autocommit = True
mcur = mconn.cursor()
scur = sconn.cursor()

# Get all tables in SPG (lowercase)
scur.execute("""
    SELECT table_schema, table_name
    FROM information_schema.tables
    WHERE table_type='BASE TABLE'
      AND table_schema IN ('api','stg','dbo','err','svc_menu_management')
""")
spg_set = {(r[0], r[1]) for r in scur.fetchall()}
print(f"SPG tables: {len(spg_set)}")

# Get identity and bool columns for all SPG tables
scur.execute("""
    SELECT table_schema, table_name, column_name, data_type, identity_generation
    FROM information_schema.columns
    WHERE table_schema IN ('api','stg','dbo','err','svc_menu_management')
""")
spg_col_info = {}
for schema, tname, colname, dtype, iden in scur.fetchall():
    key = (schema, tname)
    if key not in spg_col_info:
        spg_col_info[key] = {"identity": set(), "bool": set(), "cols": []}
    if iden == 'ALWAYS':
        spg_col_info[key]["identity"].add(colname)
    if dtype == 'boolean':
        spg_col_info[key]["bool"].add(colname)
    spg_col_info[key]["cols"].append(colname)

# Drop FK constraints
scur.execute("""
    SELECT tc.table_schema, tc.table_name, tc.constraint_name
    FROM information_schema.table_constraints tc
    WHERE tc.constraint_type='FOREIGN KEY'
      AND tc.table_schema IN ('api','stg','dbo','err','svc_menu_management')
""")
fks = scur.fetchall()
fk_dropped = 0
for schema, tname, cname in fks:
    try:
        scur.execute(f'ALTER TABLE {schema}."{tname}" DROP CONSTRAINT IF EXISTS "{cname}"')
        fk_dropped += 1
    except Exception as e:
        sconn.rollback()
        sconn.autocommit = True
print(f"Dropped {fk_dropped} FK constraints")

# Truncate all tables
print("Truncating tables...")
trunc_done = 0
for schema, tname in sorted(spg_set):
    try:
        scur.execute(f'TRUNCATE TABLE {schema}."{tname}" CASCADE')
        trunc_done += 1
    except Exception as e:
        print(f"  Trunc fail {schema}.{tname}: {e}")

print(f"Truncated {trunc_done} tables")

def convert_val(v, colname, bool_cols):
    if v is None:
        return None
    if colname in bool_cols:
        return bool(int(v)) if isinstance(v, (int, float)) else bool(v)
    if isinstance(v, (bytes, bytearray)):
        return v
    if isinstance(v, uuid.UUID):
        return v
    if isinstance(v, str):
        try:
            return uuid.UUID(v)
        except (ValueError, AttributeError):
            pass
    return v

mssql_tables = [
    (o["schema"], o["name"])
    for o in inv["objects"]
    if o["type"] == "TABLE"
]

rows_loaded = {}
skipped = []
count_fails = []
total = 0

print(f"\nLoading {len(mssql_tables)} tables...")
for i, (schema, name) in enumerate(mssql_tables):
    name_lc = name.lower()
    if (schema, name_lc) not in spg_set:
        skipped.append(f"{schema}.{name}")
        continue

    spg_key = (schema, name_lc)
    info = spg_col_info.get(spg_key, {"identity": set(), "bool": set(), "cols": []})
    bool_cols = info["bool"]
    identity_cols = info["identity"]
    spg_cols = info["cols"]

    # Get MSSQL source
    try:
        mcur.execute(f"SELECT TOP 5000 * FROM [{schema}].[{name}]")
        rows = mcur.fetchall()
        src_count = len(rows)
    except Exception as e:
        skipped.append(f"{schema}.{name} (fetch: {e})")
        continue

    if src_count == 0:
        rows_loaded[f"{schema}.{name}"] = 0
        continue

    src_cols = [d[0] for d in mcur.description]

    # Match src cols to spg cols (case-insensitive)
    spg_cols_lower_map = {c.lower(): c for c in spg_cols}
    matched = []
    for idx, scol in enumerate(src_cols):
        spg_col = spg_cols_lower_map.get(scol.lower())
        if spg_col:
            matched.append((idx, spg_col))

    if not matched:
        skipped.append(f"{schema}.{name} (no col match)")
        continue

    col_indices = [x[0] for x in matched]
    col_names = [x[1] for x in matched]
    has_identity = any(c in identity_cols for c in col_names)

    quoted_cols = ", ".join(f'"{c}"' for c in col_names)
    placeholders = ", ".join(["%s"] * len(col_names))
    if has_identity:
        insert_sql = f'INSERT INTO {schema}."{name_lc}" ({quoted_cols}) OVERRIDING SYSTEM VALUE VALUES ({placeholders})'
    else:
        insert_sql = f'INSERT INTO {schema}."{name_lc}" ({quoted_cols}) VALUES ({placeholders})'

    loaded = 0
    for row in rows:
        vals = [convert_val(row[idx], col_names[j].lower(), bool_cols)
                for j, idx in enumerate(col_indices)]
        try:
            scur.execute(insert_sql, vals)
            loaded += 1
        except Exception as e:
            sconn.rollback()
            sconn.autocommit = True
            print(f"  FAIL {schema}.{name}: {str(e)[:120]}")
            break

    rows_loaded[f"{schema}.{name}"] = loaded
    total += loaded

    if (i+1) % 50 == 0:
        print(f"  Progress: {i+1}/{len(mssql_tables)} tables, {total:,} rows so far")

print(f"\n{'='*60}")
print(f"Tables loaded: {len(rows_loaded)}")
print(f"Total rows: {total:,}")
print(f"Skipped: {len(skipped)}")
if skipped[:5]:
    for s in skipped[:5]:
        print(f"  {s}")

summary = {
    "workload": "MENU_MANAGEMENT",
    "mssql_source": f"{MSSQL_HOST}:{MSSQL_PORT}",
    "spg_target": SPG_HOST,
    "tables_loaded": len(rows_loaded),
    "tables_skipped": len(skipped),
    "total_rows": total,
    "skipped_tables": skipped,
    "count_fails": count_fails,
    "rows_per_table": rows_loaded,
    "completed_at": datetime.utcnow().isoformat() + "Z"
}
(SHARED_DIR / "load_summary.json").write_text(json.dumps(summary, indent=2))
(SHARED_DIR / "load_manifest.json").write_text(json.dumps({
    "workload": "MENU_MANAGEMENT",
    "mssql_host": f"{MSSQL_HOST}:{MSSQL_PORT}", "mssql_db": MSSQL_DB,
    "spg_host": SPG_HOST, "spg_db": SPG_DB,
    "tables_loaded": len(rows_loaded), "total_rows": total,
    "fks_dropped": fk_dropped,
    "completed_at": datetime.utcnow().isoformat() + "Z"
}, indent=2))
print("load_summary.json and load_manifest.json written")
mconn.close()
sconn.close()
