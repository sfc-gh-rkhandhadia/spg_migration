"""
Tests for the compare() verdict function in compare_proc_outputs.py.

All tests use plain dict fixtures — no DB connections required.
The reclassification rules are tested separately in test_reclassification.py.
"""
import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

_REQUIRED_ENV = {
    'MSSQL_HOST': 'localhost', 'MSSQL_PORT': '1433', 'MSSQL_USER': 'sa',
    'MSSQL_PASSWORD': 'test', 'MSSQL_DATABASE': 'TestDB',
    'SPG_HOST': 'test.snowflakecomputing.app', 'SPG_USER': 'snowflake_admin',
    'SPG_PASSWORD': 'test', 'SPG_DATABASE': 'postgres',
}
for k, v in _REQUIRED_ENV.items():
    os.environ.setdefault(k, v)

from compare_proc_outputs import compare


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _rs(cols=None, rows=None):
    """Build a result set dict."""
    cols = cols or ['col_a', 'col_b']
    rows = rows if rows is not None else [[1, 'x'], [2, 'y']]
    return {'columns': cols, 'rows': rows, 'row_count': len(rows)}

def _ms(status='SUCCESS', result_sets=None, error=None, total_rows=None,
        schema='dbo', name='p_test'):
    if result_sets is None and status == 'SUCCESS':
        result_sets = [_rs()]
    elif result_sets is None:
        result_sets = []
    rows = sum(r.get('row_count', 0) for r in result_sets)
    return {
        'full_name': f'{schema}.{name}',
        'schema': schema,
        'procedure_name': name,
        'status': status,
        'result_sets': result_sets,
        'total_rows': total_rows if total_rows is not None else rows,
        'error': error,
        'call_string': f'EXEC {schema}.{name}',
        'param_source': 'sampled',
        'obj_kind': 'PROCEDURE',
    }

def _spg(status='SUCCESS', result_sets=None, error=None, total_rows=None,
         schema='dbo', name='p_test', strategy='exec_as_call'):
    if result_sets is None and status == 'SUCCESS':
        result_sets = [_rs()]
    elif result_sets is None:
        result_sets = []
    rows = sum(r.get('row_count', 0) for r in result_sets)
    return {
        'full_name': f'{schema}.{name}',
        'schema': schema,
        'procedure_name': name,
        'status': status,
        'result_sets': result_sets,
        'total_rows': total_rows if total_rows is not None else rows,
        'error': error,
        'call_string': f'CALL {schema}.{name}()',
        'strategy_used': strategy,
        'object_kind': 'PROCEDURE',
    }


# ── PASS ──────────────────────────────────────────────────────────────────────

class TestPass:
    def test_identical_rows_and_columns(self):
        result = compare(_ms(), _spg())
        assert result['verdict'] == 'PASS'

    def test_empty_issues_on_pass(self):
        result = compare(_ms(), _spg())
        assert result['issues'] == []

    def test_pass_dml_proc_when_both_return_no_rows(self):
        ms = _ms(result_sets=[])
        sp = _spg(result_sets=[])
        result = compare(ms, sp)
        assert result['verdict'] == 'PASS_DML_PROC'

    def test_pass_dml_proc_via_call_no_resultset_and_ms_empty(self):
        ms = _ms(result_sets=[])
        sp = _spg(result_sets=[], strategy='call_no_resultset')
        result = compare(ms, sp)
        assert result['verdict'] == 'PASS_DML_PROC'


# ── SKIPPED ───────────────────────────────────────────────────────────────────

class TestSkipped:
    def test_both_skipped(self):
        ms = _ms(status='SKIPPED', result_sets=[])
        sp = _spg(status='SKIPPED', result_sets=[])
        result = compare(ms, sp)
        assert result['verdict'] == 'SKIPPED'


# ── FAIL — data differences ───────────────────────────────────────────────────

class TestFailData:
    def test_row_count_mismatch(self):
        ms = _ms(result_sets=[_rs(rows=[[1, 'a'], [2, 'b']])])
        sp = _spg(result_sets=[_rs(rows=[[1, 'a']])])
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL'
        assert any('ROW_COUNT' in i for i in result['issues'])

    def test_data_hash_mismatch_same_count(self):
        ms = _ms(result_sets=[_rs(rows=[[1, 'a']])])
        sp = _spg(result_sets=[_rs(rows=[[2, 'b']])])
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL'
        assert any('DATA_HASH_MISMATCH' in i for i in result['issues'])

    def test_cols_only_in_mssql(self):
        ms = _ms(result_sets=[_rs(cols=['col_a', 'col_b', 'col_extra'])])
        sp = _spg(result_sets=[_rs(cols=['col_a', 'col_b'])])
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL'
        assert any('COLS_ONLY_IN_MSSQL' in i for i in result['issues'])

    def test_cols_only_in_spg(self):
        ms = _ms(result_sets=[_rs(cols=['col_a', 'col_b'])])
        sp = _spg(result_sets=[_rs(cols=['col_a', 'col_b', 'col_extra'])])
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL'
        assert any('COLS_ONLY_IN_SPG' in i for i in result['issues'])

    def test_result_set_count_mismatch(self):
        ms = _ms(result_sets=[_rs(), _rs()])
        sp = _spg(result_sets=[_rs()])
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL'
        assert any('RESULT_SET_COUNT' in i for i in result['issues'])


# ── Error verdicts ────────────────────────────────────────────────────────────

class TestErrorVerdicts:
    def test_both_failed_no_prereq_scope(self):
        ms = _ms(status='ERROR', result_sets=[], error='syntax error')
        sp = _spg(status='ERROR', result_sets=[], error='function does not exist')
        result = compare(ms, sp)
        assert result['verdict'] == 'BOTH_FAILED'

    def test_spg_error_mssql_succeeded(self):
        ms = _ms()
        sp = _spg(status='ERROR', result_sets=[], error='relation does not exist')
        result = compare(ms, sp)
        assert result['verdict'] == 'SPG_ERROR'
        assert any('SPG exec failed' in i for i in result['issues'])

    def test_mssql_error_spg_succeeded(self):
        ms = _ms(status='ERROR', result_sets=[], error='invalid object name')
        sp = _spg()
        result = compare(ms, sp)
        assert result['verdict'] == 'MSSQL_ERROR'


# ── FAIL_HARNESS ──────────────────────────────────────────────────────────────

class TestFailHarness:
    def test_mssql_fail_harness_propagates(self):
        ms = _ms(status='FAIL_HARNESS', result_sets=[],
                 error='prereq_guard harness error: ImportError no module prereq_guard')
        sp = _spg()
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_HARNESS'

    def test_spg_fail_harness_propagates(self):
        ms = _ms()
        sp = _spg(status='FAIL_HARNESS', result_sets=[],
                  error='prereq_guard harness error: AttributeError ...')
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_HARNESS'

    def test_fail_harness_is_not_fail_missing_prereq(self):
        ms = _ms(status='FAIL_HARNESS', result_sets=[],
                 error='unexpected crash in guard')
        sp = _spg(status='FAIL_HARNESS', result_sets=[])
        result = compare(ms, sp)
        assert result['verdict'] != 'FAIL_MISSING_PREREQ'

    def test_fail_harness_includes_error_in_issues(self):
        ms = _ms(status='FAIL_HARNESS', result_sets=[],
                 error='prereq_guard harness error: something went wrong')
        sp = _spg()
        result = compare(ms, sp)
        assert result['issues']  # not empty
        assert any('harness error' in i.lower() for i in result['issues'])


# ── SPG_NO_RESULTSET ──────────────────────────────────────────────────────────

class TestSpgNoResultset:
    def test_spg_no_resultset_when_mssql_has_rows(self):
        ms = _ms(result_sets=[_rs(rows=[[1, 'a']])])
        sp = _spg(result_sets=[], strategy='call_no_resultset')
        result = compare(ms, sp)
        assert result['verdict'] == 'SPG_NO_RESULTSET'


# ── Metadata on result dict ───────────────────────────────────────────────────

class TestResultMetadata:
    def test_result_has_full_name(self):
        result = compare(_ms(), _spg())
        assert result['full_name'] == 'dbo.p_test'

    def test_result_has_schema_and_procedure_name(self):
        result = compare(_ms(), _spg())
        assert result['schema'] == 'dbo'
        assert result['procedure_name'] == 'p_test'

    def test_result_has_row_counts(self):
        result = compare(_ms(), _spg())
        assert 'ms_total_rows' in result
        assert 'spg_total_rows' in result
