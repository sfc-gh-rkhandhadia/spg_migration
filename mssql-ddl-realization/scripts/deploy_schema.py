#!/usr/bin/env python3
"""deploy_schema.py - Deploy MSSQL objects in dependency-wave order via pymssql."""

import argparse
import json
import os
import re
import sys
import time
from typing import Any

try:
    import pymssql
except ImportError:
    print("ERROR: pymssql not installed. Re-run with: uv run --project <SKILL_DIR>", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

_ERROR_MAP = [
    (re.compile(r"Invalid object name", re.I), "missing_object"),
    (re.compile(r"Cannot find.*column|Invalid column name", re.I), "invalid_identifier"),
    (re.compile(r"Column.*incompatible|type mismatch", re.I), "type_mismatch"),
    (re.compile(r"\bCLR\b|\bEXTERNAL\b|\bLINKED SERVER\b|\bOPENROWSET\b", re.I), "unsupported_syntax"),
    (re.compile(r"EXEC\s*\(\s*@", re.I), "dynamic_sql"),
]


def classify_error(msg: str) -> str:
    for pat, cat in _ERROR_MAP:
        if pat.search(msg):
            return cat
    return "unknown_error"


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(server: str, port: int, user: str, password: str, database: str = "master") -> "pymssql.Connection":
    for attempt in range(15):
        try:
            return pymssql.connect(
                server=server, port=port, user=user, password=password,
                database=database, timeout=10, login_timeout=10,
            )
        except Exception as exc:
            if attempt < 14:
                print(f"  Connection attempt {attempt + 1}/15 failed ({exc}), retrying in 5s…")
                time.sleep(5)
            else:
                print(f"ERROR: Cannot connect after 15 attempts: {exc}", file=sys.stderr)
                sys.exit(1)


# ---------------------------------------------------------------------------
# DDL execution helpers
# ---------------------------------------------------------------------------

_GO = re.compile(r"^\s*GO\s*$", re.I | re.M)
# Strip USE [db] directives and SET options that don't apply in the isolated DB
_USE_DB = re.compile(r"^\s*USE\s+\[?[\w]+\]?\s*$", re.I | re.M)
_SET_OPTS = re.compile(
    r"^\s*SET\s+(?:ANSI_NULLS|QUOTED_IDENTIFIER|ANSI_PADDING|NOCOUNT|NOEXEC"
    r"|CONCAT_NULL_YIELDS_NULL|XACT_ABORT)\s+(?:ON|OFF)\s*$",
    re.I | re.M,
)


def sanitize(ddl: str) -> str:
    """Strip USE and harmless SET directives that interfere with cross-DB deployment."""
    ddl = _USE_DB.sub("", ddl)
    # Keep SET options — they're valid; only strip USE
    return ddl


def exec_ddl(conn: "pymssql.Connection", ddl: str) -> tuple[bool, str]:
    """Execute a DDL statement (split on GO batches). Returns (ok, error_msg)."""
    ddl = sanitize(ddl)
    batches = [b.strip() for b in _GO.split(ddl) if b.strip()]
    for batch in batches:
        try:
            cur = conn.cursor()
            cur.execute(batch)
            conn.commit()
            cur.close()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            return False, str(exc)
    return True, ""


def strip_fk_constraints(ddl: str) -> str:
    """Remove FOREIGN KEY declarations so tables can be created in any order."""
    return re.sub(
        r",?\s*(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY[^,)]+REFERENCES[^,)()]+"
        r"(?:\([^)]*\))?(?:\s*ON\s+(?:DELETE|UPDATE)\s+\w+(?:\s+\w+)?)*",
        "",
        ddl,
        flags=re.IGNORECASE,
    )


# ---------------------------------------------------------------------------
# Deployment phases
# ---------------------------------------------------------------------------

def phase_schemas(objects: dict, conn: "pymssql.Connection") -> dict[str, str]:
    """Deploy SCHEMA objects first — everything else depends on them."""
    results: dict[str, str] = {}
    for fqn, obj in objects.items():
        if obj["type"] != "SCHEMA":
            continue
        ok, err = exec_ddl(conn, obj["ddl"])
        results[fqn] = "deployed" if ok else f"{classify_error(err)}: {err[:200]}"
        symbol = "OK" if ok else "FAIL"
        print(f"  [{symbol}] SCHEMA {fqn}")
    return results


def phase_types(objects: dict, conn: "pymssql.Connection",
               all_objects_list: list | None = None) -> dict[str, str]:
    """Deploy user-defined table types before procedures that reference them.

    Accepts an optional all_objects_list so that TYPE objects whose FQN collides
    with a same-named TABLE are still deployed (they won't appear in the objects
    dict since TABLE takes priority there, but they must still be created).
    """
    results: dict[str, str] = {}
    # Use the raw list when provided so every TYPE is seen regardless of dict dedup
    source = all_objects_list if all_objects_list is not None else list(objects.values())
    seen: set[str] = set()  # avoid deploying the same type FQN twice
    for obj in source:
        if obj["type"] != "TYPE":
            continue
        fqn = obj["fqn"]
        if fqn in seen:
            continue
        seen.add(fqn)
        ok, err = exec_ddl(conn, obj["ddl"])
        results[fqn] = "deployed" if ok else f"{classify_error(err)}: {err[:200]}"
        symbol = "OK" if ok else "FAIL"
        print(f"  [{symbol}] TYPE {fqn}")
    return results


def phase_tables(objects: dict, conn: "pymssql.Connection") -> dict[str, str]:
    results: dict[str, str] = {}
    for fqn, obj in objects.items():
        if obj["type"] != "TABLE":
            continue
        ddl = strip_fk_constraints(obj["ddl"])
        ok, err = exec_ddl(conn, ddl)
        results[fqn] = "deployed" if ok else f"{classify_error(err)}: {err[:200]}"
        symbol = "OK" if ok else "FAIL"
        print(f"  [{symbol}] {fqn}")
    return results


def phase_fk(objects: dict, conn: "pymssql.Connection") -> dict[str, str]:
    results: dict[str, str] = {}
    fk_pat = re.compile(
        r"(?:CONSTRAINT\s+\w+\s+)?FOREIGN\s+KEY[^,)]+REFERENCES[^,)()]+"
        r"(?:\([^)]*\))?(?:\s*ON\s+(?:DELETE|UPDATE)\s+\w+(?:\s+\w+)?)*",
        re.IGNORECASE,
    )
    for fqn, obj in objects.items():
        if obj["type"] != "TABLE":
            continue
        for fk_clause in fk_pat.findall(obj["ddl"]):
            alter = f"ALTER TABLE [{obj['schema']}].[{obj['name']}] ADD {fk_clause};"
            ok, err = exec_ddl(conn, alter)
            key = f"{fqn}::FK::{fk_clause[:40]}"
            results[key] = "applied" if ok else f"deferred({classify_error(err)}): {err[:120]}"
    return results


def phase_views_funcs_procs(
    objects: dict, waves: list[list[str]], conn: "pymssql.Connection"
) -> tuple[dict[str, str], list[dict]]:
    NON_TABLE = {"VIEW", "FUNCTION", "PROCEDURE"}
    results: dict[str, str] = {}
    wave_results: list[dict] = []

    for wave_idx, wave in enumerate(waves):
        ok_list, fail_list = [], []
        for fqn in wave:
            if fqn not in objects or objects[fqn]["type"] not in NON_TABLE:
                continue
            ok, err = exec_ddl(conn, objects[fqn]["ddl"])
            if ok:
                results[fqn] = "deployed"
                ok_list.append(fqn)
            else:
                results[fqn] = f"{classify_error(err)}: {err[:200]}"
                fail_list.append(fqn)
        if ok_list or fail_list:
            print(f"  Wave {wave_idx + 1}: {len(ok_list)} OK, {len(fail_list)} FAIL")
            wave_results.append(
                {"wave": wave_idx + 1, "succeeded": ok_list, "failed": fail_list}
            )

    return results, wave_results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def phase_triggers(objects: dict, conn: "pymssql.Connection") -> dict[str, str]:
    """Deploy TRIGGER objects after all tables, views, and procs exist.

    Triggers must be deployed last because:
    - Their target table must already exist (Phase 1)
    - They may reference stored procedures like dbo.RethrowError (Phase 3)
    """
    results: dict[str, str] = {}
    for fqn, obj in objects.items():
        if obj["type"] != "TRIGGER":
            continue
        ok, err = exec_ddl(conn, obj["ddl"])
        results[fqn] = "deployed" if ok else f"{classify_error(err)}: {err[:200]}"
        symbol = "OK" if ok else "FAIL"
        print(f"  [{symbol}] TRIGGER {fqn}  →  {obj.get('target_table', '?')}")
    return results


def check_exists(conn: "pymssql.Connection", obj: dict) -> bool:
    """Return True if the object already exists in the database."""
    schema = obj.get("schema", "")
    name   = obj.get("name", "")
    otype  = obj.get("type", "")
    cur = conn.cursor()
    try:
        if otype == "SCHEMA":
            cur.execute("SELECT 1 FROM sys.schemas WHERE name = %s", (name,))
        elif otype == "TYPE":
            cur.execute(
                "SELECT 1 FROM sys.types t "
                "JOIN sys.schemas s ON t.schema_id = s.schema_id "
                "WHERE s.name = %s AND t.name = %s",
                (schema, name),
            )
        elif otype == "TABLE":
            cur.execute(
                "SELECT 1 FROM sys.objects o "
                "JOIN sys.schemas s ON o.schema_id = s.schema_id "
                "WHERE s.name = %s AND o.name = %s AND o.type = 'U'",
                (schema, name),
            )
        elif otype == "TRIGGER":
            cur.execute(
                "SELECT 1 FROM sys.triggers t "
                "JOIN sys.objects p ON t.parent_id = p.object_id "
                "JOIN sys.schemas s ON p.schema_id = s.schema_id "
                "WHERE t.name = %s",
                (name,),
            )
        else:  # VIEW, PROCEDURE, FUNCTION
            cur.execute(
                "SELECT 1 FROM sys.objects o "
                "JOIN sys.schemas s ON o.schema_id = s.schema_id "
                "WHERE s.name = %s AND o.name = %s",
                (schema, name),
            )
        return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        cur.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Deploy MSSQL schema in dependency-wave order")
    p.add_argument("--inventory", required=True)
    p.add_argument("--dep-graph", required=True)
    p.add_argument("--ddl-source", required=True, help="Original DDL path (for reference)")
    p.add_argument("--server", default="localhost")
    p.add_argument("--port", type=int, default=1433)
    p.add_argument("--user", default="sa")
    p.add_argument("--password", required=True)
    p.add_argument("--database", default="RealizationDB")
    p.add_argument("--output", required=True)
    p.add_argument(
        "--skip-existing", action="store_true",
        help="Treat already-deployed objects as successfully deployed instead of failing. "
             "Use when the database is already populated (e.g. deployed via external tooling).",
    )
    args = p.parse_args()

    with open(args.inventory) as f:
        inventory = json.load(f)
    with open(args.dep_graph) as f:
        dep_graph = json.load(f)

    # Build objects dict keyed by FQN.  When a TABLE and a TYPE share the same
    # FQN (e.g. dbo.Addresses exists as both a TABLE and a USER-DEFINED TABLE TYPE),
    # keep TABLE over TYPE so that phase_tables() deploys the correct base table.
    # phase_types() iterates the raw inventory list directly, so the TYPE is still
    # deployed — it just won't be the canonical entry in the FQN lookup dict.
    objects: dict[str, Any] = {}
    for o in inventory["objects"]:
        fqn = o["fqn"]
        if fqn not in objects or (objects[fqn]["type"] == "TYPE" and o["type"] == "TABLE"):
            objects[fqn] = o
    # Keep the raw list for phase_types() so it can see all TYPE objects regardless
    # of whether their FQN collides with a TABLE.
    all_objects_list: list[dict] = inventory["objects"]
    waves: list[list[str]] = dep_graph["waves"]

    # Create database in master context
    print(f"Connecting to {args.server}:{args.port}…")
    conn = connect(args.server, args.port, args.user, args.password)
    try:
        cur = conn.cursor()
        # autocommit needed for CREATE DATABASE
        conn.autocommit(True)
        cur.execute(
            f"IF NOT EXISTS (SELECT 1 FROM sys.databases WHERE name = N'{args.database}') "
            f"CREATE DATABASE [{args.database}]"
        )
        cur.close()
    finally:
        conn.close()

    conn = connect(args.server, args.port, args.user, args.password, args.database)

    all_results: dict[str, str] = {}

    print("Phase 0: Schemas…")
    all_results.update(phase_schemas(objects, conn))

    print("Phase 0.5: User-defined table types…")
    all_results.update(phase_types(objects, conn, all_objects_list))

    print("Phase 1: Tables (FK-free)…")
    all_results.update(phase_tables(objects, conn))

    print("Phase 2: FK constraints…")
    all_results.update(phase_fk(objects, conn))

    print("Phase 3: Views / Functions / Procedures by wave…")
    vfp_results, wave_results = phase_views_funcs_procs(objects, waves, conn)
    all_results.update(vfp_results)

    print("Phase 3.5: Triggers…")
    all_results.update(phase_triggers(objects, conn))

    # --skip-existing: reclassify failed objects that already exist in the DB
    if args.skip_existing:
        reclassified = 0
        for fqn, result in list(all_results.items()):
            if result == "deployed":
                continue
            # FK results use a different key format — skip them
            if "::FK::" in fqn:
                continue
            obj = objects.get(fqn)
            if obj and check_exists(conn, obj):
                all_results[fqn] = "deployed"
                reclassified += 1
        if reclassified:
            print(f"  --skip-existing: reclassified {reclassified} already-present objects as deployed")

    conn.close()

    succeeded = [k for k, v in all_results.items() if v == "deployed"]
    failed = {k: v for k, v in all_results.items() if v != "deployed"}
    fail_cats: dict[str, int] = {}
    for v in failed.values():
        cat = v.split(":")[0]
        fail_cats[cat] = fail_cats.get(cat, 0) + 1

    report = {
        "database": args.database,
        "server": f"{args.server}:{args.port}",
        "results": all_results,
        "succeeded": succeeded,
        "failed": failed,
        "wave_results": wave_results,
        "summary": {
            "total_objects": len(objects),
            "deployed": len(succeeded),
            "failed": len(failed),
            "failure_categories": fail_cats,
        },
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"\nDeployment summary:")
    print(f"  Deployed: {report['summary']['deployed']}")
    print(f"  Failed:   {report['summary']['failed']}")
    for cat, cnt in fail_cats.items():
        print(f"    {cat}: {cnt}")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
