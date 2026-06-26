"""
Single-schema spot-check validator
===================================
Quick structural check for procedures, functions, and views in a single schema.
Results print to stdout; nothing is written to the validation audit tables.

Usage:
  python3 full_validation.py [schema]          # defaults to 'api'
  python3 full_validation.py dbo
  python3 full_validation.py reporting

Use this script for:
  - Fast ad-hoc parity checks against one schema during development
  - Debugging a single schema without running the full pipeline

Do NOT use this script for:
  - Production validation runs  → use run.py (or run_validation.sh)
  - Behavioral execution testing → use run.py --procs
  - Generating reports           → use generate_validation_markdown.py / generate_migration_report.py
  - Any run whose results need to be stored or compared over time

Limitations:
  - One schema per invocation; for all schemas use full_schema_audit.py
  - Checks parameter count/names and view row counts only — does not execute procedures
  - Results are not persisted to validation.validation_result
  - Uses a WARN verdict (not part of the standard taxonomy) for SPG-only columns

Alternative: python3 run.py --all
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SCHEMA = sys.argv[1] if len(sys.argv) > 1 else "api"
print(f"[NOTICE] full_validation.py is a spot-check tool (schema: {SCHEMA!r}). "
      "Results are not saved to audit tables. Use run.py for the full pipeline.")
import pymssql, psycopg2, psycopg2.extras, concurrent.futures, sys, time
from config import MSSQL_CONF, SPG_CONF, is_mssql_system_schema, is_spg_system_schema, check_required

check_required()

def ms_conn():  return pymssql.connect(**MSSQL_CONF)
def spg_conn(): return psycopg2.connect(**SPG_CONF)

# ── Step 1: Discover all objects ──────────────────────────────────────────────

def discover_mssql():
    conn = ms_conn()
    cur  = conn.cursor(as_dict=True)

    # Procedures
    cur.execute("""
        SELECT s.name AS schema_name, p.name AS obj_name, 'PROCEDURE' AS obj_type,
               LEN(sm.definition) AS def_len
        FROM sys.procedures p
        JOIN sys.schemas s ON p.schema_id = s.schema_id
        JOIN sys.sql_modules sm ON p.object_id = sm.object_id
        WHERE s.name = %s
        ORDER BY p.name
    """, (SCHEMA,))
    procs = cur.fetchall()

    # Views
    cur.execute("""
        SELECT s.name AS schema_name, v.name AS obj_name, 'VIEW' AS obj_type,
               LEN(sm.definition) AS def_len
        FROM sys.views v
        JOIN sys.schemas s ON v.schema_id = s.schema_id
        JOIN sys.sql_modules sm ON v.object_id = sm.object_id
        WHERE s.name = %s
        ORDER BY v.name
    """, (SCHEMA,))
    views = cur.fetchall()
    conn.close()

    result = {}
    for r in procs + views:
        key = r['obj_name'].lower()
        result[key] = {'name': r['obj_name'], 'type': r['obj_type'], 'def_len': r['def_len']}
    return result

def discover_spg():
    conn = spg_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Procedures and functions
    cur.execute("""
        SELECT p.proname AS obj_name,
               CASE p.prokind WHEN 'p' THEN 'PROCEDURE' WHEN 'f' THEN 'FUNCTION'
                              ELSE 'FUNCTION' END AS obj_type,
               p.pronargs AS param_count
        FROM pg_proc p
        JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = %s
        ORDER BY p.proname
    """, (SCHEMA,))
    procs = cur.fetchall()

    # Views
    cur.execute("""
        SELECT c.relname AS obj_name, 'VIEW' AS obj_type
        FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE c.relkind = 'v' AND n.nspname = %s
        ORDER BY c.relname
    """, (SCHEMA,))
    views = cur.fetchall()
    conn.close()

    result = {}
    for r in list(procs) + list(views):
        key = r['obj_name'].lower()
        result[key] = {'name': r['obj_name'], 'type': r['obj_type']}
    return result

# ── Step 2: Validation helpers ────────────────────────────────────────────────

def validate_view(ms_name, spg_name):
    try:
        ms = ms_conn()
        mc = ms.cursor()
        mc.execute("SELECT TOP 0 * FROM %s.%s" % (SCHEMA, ms_name))
        ms_cols  = [d[0].lower() for d in mc.description]
        mc.execute("SELECT COUNT(*) FROM %s.%s" % (SCHEMA, ms_name))
        ms_count = mc.fetchone()[0]
        ms.close()
    except Exception as e:
        return {'verdict': 'ERROR', 'issues': ['MSSQL_ERR: %s' % str(e)[:100]],
                'ms_rows': None, 'spg_rows': None, 'ms_cols': [], 'spg_cols': []}

    try:
        sp = spg_conn()
        sc = sp.cursor()
        sc.execute('SELECT * FROM %s."%s" LIMIT 0' % (SCHEMA, spg_name))
        spg_cols  = [d[0].lower() for d in sc.description]
        sc.execute('SELECT COUNT(*) FROM %s."%s"' % (SCHEMA, spg_name))
        spg_count = sc.fetchone()[0]
        sp.close()
    except Exception as e:
        return {'verdict': 'ERROR', 'issues': ['SPG_ERR: %s' % str(e)[:120]],
                'ms_rows': ms_count, 'spg_rows': None, 'ms_cols': ms_cols, 'spg_cols': []}

    issues, verdict = [], 'PASS'
    if ms_count != spg_count:
        issues.append('ROW_COUNT: MSSQL=%d SPG=%d' % (ms_count, spg_count))
        verdict = 'FAIL'
    ms_set, spg_set = set(ms_cols), set(spg_cols)
    only_ms  = sorted(ms_set - spg_set)
    only_spg = sorted(spg_set - ms_set)
    if only_ms:
        issues.append('COLS_ONLY_IN_MSSQL: %s' % only_ms)
        verdict = 'FAIL'
    if only_spg:
        issues.append('COLS_ONLY_IN_SPG: %s' % only_spg)
        verdict = 'FAIL' if verdict != 'PASS' else 'WARN'
    return {'verdict': verdict, 'issues': issues,
            'ms_rows': ms_count, 'spg_rows': spg_count,
            'ms_cols': len(ms_cols), 'spg_cols': len(spg_cols)}

def get_ms_params(name):
    try:
        conn = ms_conn(); cur = conn.cursor(as_dict=True)
        cur.execute("""
            SELECT p.parameter_id, p.name AS pname, t.name AS tname, p.is_output
            FROM sys.procedures pr
            JOIN sys.schemas s ON pr.schema_id = s.schema_id
            JOIN sys.parameters p ON pr.object_id = p.object_id
            JOIN sys.types t ON p.user_type_id = t.user_type_id
            WHERE s.name = %s AND LOWER(pr.name) = %s
            ORDER BY p.parameter_id
        """, (SCHEMA, name,))
        rows = cur.fetchall(); conn.close()
        return [{'name': r['pname'].lstrip('@').lower(), 'type': r['tname']} for r in rows]
    except Exception as e:
        return 'ERR:%s' % str(e)[:80]

def get_spg_params(name):
    try:
        conn = spg_conn()
        cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT pa.ordinal_position, pa.parameter_name, pa.data_type, pa.parameter_mode
            FROM information_schema.routines r
            JOIN information_schema.parameters pa ON r.specific_name = pa.specific_name
            WHERE r.routine_schema = %s AND LOWER(r.routine_name) = %s
            ORDER BY pa.ordinal_position
        """, (SCHEMA, name,))
        rows = cur.fetchall(); conn.close()
        return [{'name': (r['parameter_name'] or '').lstrip('_').lower(),
                 'type': r['data_type'] or ''}
                for r in rows if (r['parameter_mode'] or 'IN') == 'IN']
    except Exception as e:
        return 'ERR:%s' % str(e)[:80]

def strip_p(n):
    if n.startswith('par_'): return n[4:]
    if n.startswith('p_'):   return n[2:]
    return n

def validate_proc(ms_name, spg_name):
    ms_p  = get_ms_params(ms_name)
    spg_p = get_spg_params(spg_name)

    if isinstance(ms_p, str):  return {'verdict':'ERROR','issues':['MSSQL_ERR:%s'%ms_p],'ms_p':'?','spg_p':'?'}
    if isinstance(spg_p, str): return {'verdict':'ERROR','issues':['SPG_ERR:%s'%spg_p],'ms_p':len(ms_p),'spg_p':'?'}

    issues, verdict = [], 'PASS'
    if len(ms_p) != len(spg_p):
        issues.append('PARAM_COUNT: MSSQL=%d SPG=%d' % (len(ms_p), len(spg_p)))
        verdict = 'FAIL'
    else:
        all_ms  = [p['name'] for p in ms_p]
        all_spg = [strip_p(p['name']) for p in spg_p]
        if set(all_ms) == set(all_spg) and all_ms != all_spg:
            mismatches = ['pos%d: MSSQL=%s SPG=%s' % (i+1, a, b)
                          for i,(a,b) in enumerate(zip(all_ms, all_spg)) if a != b]
            issues.append('PARAM_ORDER_SWAPPED (%d positions): %s%s' % (
                len(mismatches), str(mismatches[:2])[1:-1],
                '...' if len(mismatches) > 2 else ''))
            verdict = 'FAIL'
        elif set(all_ms) != set(all_spg):
            diff = [('pos%d MSSQL=%s SPG=%s' % (i+1, a, b))
                    for i,(a,b) in enumerate(zip(all_ms, all_spg)) if a != b]
            issues.append('PARAM_NAMES_DIFFER: %s%s' % (
                str(diff[:2])[1:-1], '...' if len(diff) > 2 else ''))
            verdict = 'FAIL'
        # else: only p_ prefix diffs — convention, PASS
    return {'verdict': verdict, 'issues': issues, 'ms_p': len(ms_p), 'spg_p': len(spg_p)}

# ── Step 3: Run everything ────────────────────────────────────────────────────

print("Discovering objects from both systems...")
ms_objects  = discover_mssql()
spg_objects = discover_spg()

ms_names  = set(ms_objects.keys())
spg_names = set(spg_objects.keys())

matched      = ms_names & spg_names
only_in_ms   = ms_names - spg_names  # missing in SPG
only_in_spg  = spg_names - ms_names  # new in SPG (not in MSSQL)

print(f"MSSQL {SCHEMA} schema : {len(ms_objects)} objects "
      f"({sum(1 for v in ms_objects.values() if v['type']=='PROCEDURE')} procs, "
      f"{sum(1 for v in ms_objects.values() if v['type']=='VIEW')} views)")
print(f"SPG   {SCHEMA} schema : {len(spg_objects)} objects "
      f"({sum(1 for v in spg_objects.values() if v['type'] in ('PROCEDURE','FUNCTION'))} procs/funcs, "
      f"{sum(1 for v in spg_objects.values() if v['type']=='VIEW')} views)")
print("Matched          : %d" % len(matched))
print("Missing in SPG   : %d" % len(only_in_ms))
print("New in SPG only  : %d" % len(only_in_spg))
print("\nRunning validation on %d matched objects...\n" % len(matched))
sys.stdout.flush()

results = []

BATCH = 12

def run_one(name):
    ms_info  = ms_objects[name]
    spg_info = spg_objects[name]
    obj_type = ms_info['type']  # trust MSSQL type

    if obj_type == 'VIEW':
        r = validate_view(name, name)
        r.update({'name': name, 'type': 'VIEW', 'ms_name': ms_info['name'], 'spg_name': spg_info['name']})
    else:
        r = validate_proc(name, name)
        r.update({'name': name, 'type': obj_type, 'ms_name': ms_info['name'], 'spg_name': spg_info['name']})
    return r

all_names = sorted(matched)
all_results = []

for i in range(0, len(all_names), BATCH):
    batch = all_names[i:i+BATCH]
    with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH) as pool:
        futs = {pool.submit(run_one, n): n for n in batch}
        for fut in concurrent.futures.as_completed(futs):
            all_results.append(fut.result())
    sys.stdout.flush()

# Sort: FAILs first, then by type, then name
order = {'FAIL':0,'ERROR':1,'WARN':2,'PASS':3}
all_results.sort(key=lambda r: (order.get(r['verdict'],9), r['type'], r['name']))

# ── Step 4: Print full report ──────────────────────────────────────────────────

SEP = "=" * 110
print(SEP)
print("COMPLETE VALIDATION REPORT — %s schema" % SCHEMA)
print(SEP)

# Views section
view_results = [r for r in all_results if r['type'] == 'VIEW']
proc_results = [r for r in all_results if r['type'] in ('PROCEDURE','FUNCTION')]

print("\n%s" % ("─"*110))
print("VIEWS  (%d tested)" % len(view_results))
print("─"*110)
print("%-55s %-6s %10s %10s  %-8s  ISSUES" % ("VIEW","TYPE","MSSQL_ROWS","SPG_ROWS","VERDICT"))
print("─"*110)
for r in view_results:
    ms_r  = r.get('ms_rows',  '?')
    spg_r = r.get('spg_rows', '?')
    print("%-55s %-6s %10s %10s  %-8s" % (
        SCHEMA+'.'+r['name'], r['type'],
        str(ms_r) if ms_r is not None else 'ERR',
        str(spg_r) if spg_r is not None else 'ERR',
        r['verdict']))
    for iss in r['issues']:
        print("  └─ %s" % iss)

# Procedures section
print("\n%s" % ("─"*110))
print("PROCEDURES / FUNCTIONS  (%d tested)" % len(proc_results))
print("─"*110)
print("%-60s %-9s %6s %6s  %-8s  ISSUES" % ("PROCEDURE","TYPE","MS_P","SPG_P","VERDICT"))
print("─"*110)
for r in proc_results:
    print("%-60s %-9s %6s %6s  %-8s" % (
        SCHEMA+'.'+r['name'], r['type'],
        str(r.get('ms_p','?')), str(r.get('spg_p','?')), r['verdict']))
    for iss in r['issues']:
        print("  └─ %s" % iss)

# Missing in SPG
print("\n%s" % ("─"*110))
print("MISSING IN SPG  (%d objects in MSSQL with no match in SPG)" % len(only_in_ms))
print("─"*110)
for n in sorted(only_in_ms):
    info = ms_objects[n]
    print("  MISSING  %-55s  %s" % (SCHEMA+'.'+info['name'], info['type']))

# New in SPG only
print("\n%s" % ("─"*110))
print("NEW IN SPG ONLY  (%d objects in SPG not in MSSQL)" % len(only_in_spg))
print("─"*110)
for n in sorted(only_in_spg):
    info = spg_objects[n]
    print("  SPG_ONLY  %-55s  %s" % (SCHEMA+'.'+info['name'], info['type']))

# Summary
v_pass  = sum(1 for r in view_results if r['verdict']=='PASS')
v_fail  = sum(1 for r in view_results if r['verdict']=='FAIL')
v_warn  = sum(1 for r in view_results if r['verdict']=='WARN')
v_err   = sum(1 for r in view_results if r['verdict']=='ERROR')
p_pass  = sum(1 for r in proc_results if r['verdict']=='PASS')
p_fail  = sum(1 for r in proc_results if r['verdict']=='FAIL')
p_err   = sum(1 for r in proc_results if r['verdict']=='ERROR')

print("\n" + SEP)
print("SUMMARY")
print(SEP)
print("VIEWS      : PASS=%-4d FAIL=%-4d WARN=%-4d ERROR=%-4d MISSING=%-4d" % (
    v_pass, v_fail, v_warn, v_err,
    sum(1 for n in only_in_ms if ms_objects[n]['type']=='VIEW')))
print("PROCEDURES : PASS=%-4d FAIL=%-4d ERROR=%-4d MISSING=%-4d" % (
    p_pass, p_fail, p_err,
    sum(1 for n in only_in_ms if ms_objects[n]['type']=='PROCEDURE')))
print("SPG NEW    : %d objects exist in SPG but not in MSSQL" % len(only_in_spg))
print(SEP)
