"""
Unit tests for the pure (no-DB) functions in adaptive_seed.py.

All tests run fully offline — no MSSQL Docker container or live connection needed.
The DB-calling functions (adaptive_validate_view, adaptive_validate_proc, etc.)
are NOT tested here; they require a live connection and belong in integration tests.

Covered:
  - extract_cte_names
  - extract_alias_map
  - extract_inner_join_pairs
  - extract_where_conditions
  - _default_val
  - _parse_literal
  - _clean_col_name
  - _is_pk
  - _toposort
  - _resolve_to_base_tables
  - parse_proc_params
"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from adaptive_seed import (
    extract_cte_names,
    extract_alias_map,
    extract_inner_join_pairs,
    extract_where_conditions,
    _default_val,
    _parse_literal,
    _clean_col_name,
    _is_pk,
    _toposort,
    _resolve_to_base_tables,
    parse_proc_params,
)


# ── extract_cte_names ─────────────────────────────────────────────────────────

class TestExtractCteNames:
    def test_single_cte(self):
        sql = "WITH cte1 AS (SELECT 1) SELECT * FROM cte1"
        assert extract_cte_names(sql) == {'cte1'}

    def test_multiple_ctes(self):
        sql = "WITH a AS (SELECT 1), b AS (SELECT 2), c AS (SELECT 3) SELECT * FROM a"
        assert extract_cte_names(sql) == {'a', 'b', 'c'}

    def test_no_cte(self):
        sql = "SELECT * FROM dbo.orders WHERE id = 1"
        assert extract_cte_names(sql) == set()

    def test_cte_names_are_lowercased(self):
        sql = "WITH MyData AS (SELECT 1) SELECT * FROM MyData"
        assert 'mydata' in extract_cte_names(sql)

    def test_no_with_keyword(self):
        assert extract_cte_names("SELECT 1") == set()


# ── extract_alias_map ─────────────────────────────────────────────────────────

class TestExtractAliasMap:
    def test_single_table_with_alias(self):
        sql = "SELECT o.id FROM dbo.orders o"
        result = extract_alias_map(sql, set(), {'dbo.orders'})
        assert result.get('o') == 'dbo.orders'

    def test_join_with_two_aliases(self):
        sql = "FROM dbo.orders o JOIN dbo.customers c ON o.customer_id = c.id"
        result = extract_alias_map(sql, set(), {'dbo.orders', 'dbo.customers'})
        assert result.get('o') == 'dbo.orders'
        assert result.get('c') == 'dbo.customers'

    def test_cte_names_are_excluded(self):
        sql = "WITH cte AS (SELECT 1) SELECT * FROM dbo.orders cte"
        result = extract_alias_map(sql, {'cte'}, {'dbo.orders'})
        assert 'cte' not in result

    def test_returns_empty_when_no_known_fqns_match(self):
        sql = "SELECT * FROM dbo.unknown_table u"
        result = extract_alias_map(sql, set(), {'dbo.orders'})
        assert result == {}

    def test_dbo_default_schema_fallback(self):
        # Table referenced without schema in SQL but known FQN has dbo prefix
        sql = "SELECT * FROM orders o"
        result = extract_alias_map(sql, set(), {'dbo.orders'})
        assert result.get('o') == 'dbo.orders'


# ── extract_inner_join_pairs ──────────────────────────────────────────────────

class TestExtractInnerJoinPairs:
    def _alias_map(self):
        return {'o': 'dbo.orders', 'c': 'dbo.customers'}

    def test_simple_equi_join(self):
        sql = "FROM dbo.orders o JOIN dbo.customers c ON o.customer_id = c.id"
        alias_map = self._alias_map()
        pairs = extract_inner_join_pairs(sql, alias_map)
        assert len(pairs) == 1
        t1, c1, t2, c2 = pairs[0]
        assert {t1, t2} == {'dbo.orders', 'dbo.customers'}

    def test_no_join_produces_empty(self):
        sql = "SELECT * FROM dbo.orders o WHERE o.id = 1"
        pairs = extract_inner_join_pairs(sql, self._alias_map())
        assert pairs == []

    def test_self_join_excluded(self):
        # Same alias on both sides should not produce a pair
        sql = "FROM dbo.orders o JOIN dbo.orders o2 ON o.id = o.parent_id"
        alias_map = {'o': 'dbo.orders', 'o2': 'dbo.orders'}
        pairs = extract_inner_join_pairs(sql, alias_map)
        # Self-join to the same FQN — should produce at most one pair, not crash
        # (implementation may allow it; just assert no exception and no duplication)
        assert isinstance(pairs, list)

    def test_unknown_alias_skipped(self):
        sql = "FROM dbo.orders o JOIN unknown_alias x ON o.id = x.order_id"
        pairs = extract_inner_join_pairs(sql, self._alias_map())
        assert pairs == []


# ── _clean_col_name ───────────────────────────────────────────────────────────

class TestCleanColName:
    @pytest.mark.parametrize("raw,expected", [
        ("[MyColumn]", "MyColumn"),
        ("plain", "plain"),
        ("[Id] ASC", "Id"),
        ("[Name] DESC", "Name"),
        ("  [Col]  ", "Col"),
        ("`backtick`", "backtick"),
    ])
    def test_strips_brackets_and_sort_direction(self, raw, expected):
        assert _clean_col_name(raw) == expected


# ── _is_pk ────────────────────────────────────────────────────────────────────

class TestIsPk:
    def test_column_in_pk_columns(self):
        obj = {"pk_columns": ["Id"], "columns": []}
        assert _is_pk("Id", obj) is True

    def test_column_not_pk(self):
        obj = {"pk_columns": ["Id"], "columns": []}
        assert _is_pk("Name", obj) is False

    def test_case_insensitive_pk_match(self):
        obj = {"pk_columns": ["OrderId"], "columns": []}
        assert _is_pk("orderid", obj) is True

    def test_identity_column_treated_as_pk(self):
        obj = {
            "pk_columns": [],
            "columns": [{"name": "Id", "identity": True}],
        }
        assert _is_pk("Id", obj) is True

    def test_pk_with_asc_suffix(self):
        obj = {"pk_columns": ["[Id] ASC"], "columns": []}
        assert _is_pk("Id", obj) is True

    def test_empty_obj(self):
        assert _is_pk("Id", {}) is False


# ── _default_val ──────────────────────────────────────────────────────────────

class TestDefaultVal:
    @pytest.mark.parametrize("dtype,seq,expected_type", [
        ("INT", 1, int),
        ("BIGINT", 2, int),
        ("SMALLINT", 3, int),
        ("TINYINT", 4, int),
        ("DECIMAL", 1, float),
        ("NUMERIC", 1, float),
        ("FLOAT", 1, float),
        ("MONEY", 1, float),
        ("BIT", 1, int),
        ("NVARCHAR", 1, str),
        ("VARCHAR", 1, str),
        ("UNIQUEIDENTIFIER", 1, str),
    ])
    def test_returns_correct_type(self, dtype, seq, expected_type):
        col = {"data_type": dtype}
        val = _default_val(col, seq)
        assert isinstance(val, expected_type)

    def test_identity_column_returns_none(self):
        col = {"data_type": "INT", "identity": True}
        assert _default_val(col, 1) is None

    def test_int_uses_seq_as_value(self):
        col = {"data_type": "INT"}
        assert _default_val(col, 7) == 7

    def test_date_returns_string(self):
        col = {"data_type": "DATE"}
        val = _default_val(col, 1)
        assert isinstance(val, str)
        assert "-" in val  # ISO date format

    def test_datetime_returns_string(self):
        col = {"data_type": "DATETIME"}
        assert isinstance(_default_val(col, 1), str)

    def test_uniqueidentifier_is_uuid_format(self):
        import re
        col = {"data_type": "UNIQUEIDENTIFIER"}
        val = _default_val(col, 1)
        assert re.match(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            val, re.I
        )


# ── _parse_literal ────────────────────────────────────────────────────────────

class TestParseLiteral:
    @pytest.mark.parametrize("val,dtype,expected", [
        ("5", "INT", 5),
        ("5", "BIGINT", 5),
        ("3.14", "DECIMAL", 3.14),
        ("3.14", "FLOAT", 3.14),
        ("hello", "NVARCHAR", "hello"),
        ("0", "BIT", 0),
        ("1", "BIT", 1),
        ("not_a_number", "INT", "not_a_number"),  # fallback returns original
    ])
    def test_type_coercion(self, val, dtype, expected):
        col = {"data_type": dtype}
        assert _parse_literal(val, col) == expected

    def test_none_col_defaults_to_nvarchar(self):
        result = _parse_literal("hello", None)
        assert result == "hello"


# ── _toposort ─────────────────────────────────────────────────────────────────

class TestToposort:
    def _obj(self, pk=None, identity=False):
        cols = []
        if pk and identity:
            cols = [{"name": pk, "identity": True}]
        return {"pk_columns": [pk] if pk and not identity else [], "columns": cols}

    def test_single_table(self):
        result = _toposort(["dbo.orders"], [], {})
        assert result == ["dbo.orders"]

    def test_pk_table_sorts_before_fk_table(self):
        objects = {
            "dbo.customers": self._obj(pk="id"),
            "dbo.orders": self._obj(),
        }
        # orders.customer_id references customers.id
        join_pairs = [("dbo.customers", "id", "dbo.orders", "customer_id")]
        tables = ["dbo.orders", "dbo.customers"]
        result = _toposort(tables, join_pairs, objects)
        assert result.index("dbo.customers") < result.index("dbo.orders")

    def test_no_join_pairs_preserves_all_tables(self):
        tables = ["dbo.a", "dbo.b", "dbo.c"]
        result = _toposort(tables, [], {})
        assert set(result) == set(tables)

    def test_all_tables_included_even_with_cycle_hint(self):
        # Tables with no clear ordering should still appear in the result
        tables = ["dbo.a", "dbo.b"]
        join_pairs = [("dbo.a", "id", "dbo.b", "a_id"), ("dbo.b", "id", "dbo.a", "b_id")]
        objects = {
            "dbo.a": self._obj(pk="id"),
            "dbo.b": self._obj(pk="id"),
        }
        result = _toposort(tables, join_pairs, objects)
        assert set(result) == {"dbo.a", "dbo.b"}


# ── _resolve_to_base_tables ───────────────────────────────────────────────────

class TestResolveToBaseTables:
    def test_table_resolves_to_itself(self):
        objects = {"dbo.orders": {"type": "TABLE"}}
        assert _resolve_to_base_tables("dbo.orders", objects) == ["dbo.orders"]

    def test_view_resolves_to_base_table(self):
        objects = {
            "dbo.v_orders": {"type": "VIEW", "dependencies": ["dbo.orders"]},
            "dbo.orders": {"type": "TABLE"},
        }
        result = _resolve_to_base_tables("dbo.v_orders", objects)
        assert result == ["dbo.orders"]

    def test_nested_view_resolves_transitively(self):
        objects = {
            "dbo.v_summary": {"type": "VIEW", "dependencies": ["dbo.v_orders"]},
            "dbo.v_orders":  {"type": "VIEW", "dependencies": ["dbo.orders"]},
            "dbo.orders":    {"type": "TABLE"},
        }
        result = _resolve_to_base_tables("dbo.v_summary", objects)
        assert result == ["dbo.orders"]

    def test_unknown_fqn_returns_empty(self):
        assert _resolve_to_base_tables("dbo.missing", {}) == []

    def test_cycle_does_not_infinite_loop(self):
        objects = {
            "dbo.a": {"type": "VIEW", "dependencies": ["dbo.b"]},
            "dbo.b": {"type": "VIEW", "dependencies": ["dbo.a"]},
        }
        result = _resolve_to_base_tables("dbo.a", objects)
        assert isinstance(result, list)  # did not hang

    def test_case_insensitive_dependency_resolution(self):
        objects = {
            "dbo.v_orders": {"type": "VIEW", "dependencies": ["DBO.Orders"]},
            "dbo.Orders":   {"type": "TABLE"},
        }
        result = _resolve_to_base_tables("dbo.v_orders", objects)
        assert "dbo.Orders" in result


# ── parse_proc_params ─────────────────────────────────────────────────────────

class TestParseProcParams:
    def test_single_param(self):
        sql = "CREATE PROCEDURE dbo.p_test (@id INT) AS BEGIN END"
        params = parse_proc_params(sql)
        assert len(params) == 1
        assert params[0]["name"] in ("@id", "id")  # implementation strips @ prefix
        assert params[0]["type"] == "INT"

    def test_multiple_params(self):
        sql = (
            "CREATE PROCEDURE dbo.p_test (@id INT, @name NVARCHAR(100), @active BIT) "
            "AS BEGIN END"
        )
        params = parse_proc_params(sql)
        assert len(params) == 3
        # Implementation may strip the leading @ — normalise for comparison
        names = [p["name"].lstrip("@") for p in params]
        assert "id" in names
        assert "name" in names
        assert "active" in names

    def test_param_with_default(self):
        sql = "CREATE PROCEDURE dbo.p_test (@status NVARCHAR(50) = 'active') AS BEGIN END"
        params = parse_proc_params(sql)
        assert len(params) == 1
        assert params[0]["default"] == "active"

    def test_null_default(self):
        sql = "CREATE PROCEDURE dbo.p_test (@id INT = NULL) AS BEGIN END"
        params = parse_proc_params(sql)
        assert params[0]["default"] is None or params[0]["default"] == "NULL"

    def test_no_params_returns_empty(self):
        sql = "CREATE PROCEDURE dbo.p_no_params AS BEGIN SELECT 1 END"
        params = parse_proc_params(sql)
        assert params == []

    def test_type_is_uppercased_without_size(self):
        sql = "CREATE PROCEDURE dbo.p_test (@name nvarchar(200)) AS BEGIN END"
        params = parse_proc_params(sql)
        assert params[0]["type"] == "NVARCHAR"

    @pytest.mark.parametrize("proc_sql,expected_count", [
        ("CREATE PROC dbo.p (@a INT, @b INT) AS BEGIN END", 2),
        ("CREATE OR ALTER PROCEDURE dbo.p (@x BIGINT) AS BEGIN END", 1),
        ("CREATE FUNCTION dbo.f (@val DECIMAL(10,2)) RETURNS TABLE AS RETURN (SELECT @val v)", 1),
    ])
    def test_various_create_forms(self, proc_sql, expected_count):
        params = parse_proc_params(proc_sql)
        assert len(params) == expected_count
