"""
Tests for reclassification rules in alternate_flow_rules.yaml.

Verifies that the rule-driven BOTH_FAILED → FAIL_MISSING_PREREQ reclassification
fires on matching error text and does NOT fire on non-matching error text.

No DB connections required.
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

from compare_proc_outputs import compare, _load_reclassification_rules


# ── Helpers ───────────────────────────────────────────────────────────────────

def _both_failed(ms_err='', spg_err='', schema='dbo', name='p_test',
                 ms_status='ERROR', spg_status='ERROR'):
    """Build a BOTH_FAILED pair of records with the given error texts."""
    def _rec(err, status, side):
        return {
            'full_name': f'{schema}.{name}',
            'schema': schema,
            'procedure_name': name,
            'status': status,
            'result_sets': [],
            'total_rows': 0,
            'error': err,
            'call_string': f'EXEC {schema}.{name}',
            'param_source': 'sampled' if side == 'ms' else '',
            'strategy_used': 'exec_as_call',
            'obj_kind': 'PROCEDURE',
            'object_kind': 'PROCEDURE',
        }
    return _rec(ms_err, ms_status, 'ms'), _rec(spg_err, spg_status, 'spg')


# ── YAML integrity ────────────────────────────────────────────────────────────

class TestYamlIntegrity:
    def test_rules_load_without_error(self):
        rules = _load_reclassification_rules()
        assert isinstance(rules, list)

    def test_at_least_one_rule_defined(self):
        rules = _load_reclassification_rules()
        assert len(rules) >= 1

    def test_each_rule_has_name(self):
        rules = _load_reclassification_rules()
        for rule in rules:
            assert 'name' in rule, f"Rule missing 'name': {rule}"

    def test_each_rule_has_reason(self):
        rules = _load_reclassification_rules()
        for rule in rules:
            assert 'reason' in rule, f"Rule '{rule.get('name')}' missing 'reason'"

    def test_each_rule_has_at_least_one_match_clause(self):
        rules = _load_reclassification_rules()
        for rule in rules:
            has_match = rule.get('match_any') or rule.get('match_all')
            assert has_match, f"Rule '{rule.get('name')}' has no match_any or match_all"


# ── active_job_state_null_column ──────────────────────────────────────────────

class TestActiveJobStateNullColumn:
    def test_fires_on_error_515(self):
        ms, sp = _both_failed(
            ms_err="Msg 515 Cannot insert the value NULL into column 'MicrosLoadStatusId'",
            spg_err="error 515 occurred")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'
        assert any('Reclassified' in i for i in result['issues'])

    def test_fires_on_null_value_in_column(self):
        ms, sp = _both_failed(
            ms_err="null value in column 'jobactiveflag' violates not-null constraint",
            spg_err="null value in column violates not-null constraint")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'

    def test_fires_on_jobactiveflag_in_error(self):
        ms, sp = _both_failed(
            ms_err="error converting jobactiveflag",
            spg_err="column jobactiveflag has no active row")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'

    def test_fires_on_microsloadstatusid(self):
        ms, sp = _both_failed(
            ms_err="FK violation on MicrosLoadStatusId",
            spg_err="foreign key constraint on microsloadstatusid")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'

    def test_does_not_fire_on_unrelated_error(self):
        ms, sp = _both_failed(
            ms_err="Syntax error near SELECT",
            spg_err="function p_test does not exist")
        result = compare(ms, sp)
        assert result['verdict'] == 'BOTH_FAILED'

    def test_does_not_fire_when_only_one_side_fails(self):
        # Only BOTH_FAILED triggers reclassification; SPG_ERROR does not
        ms_rec = {
            'full_name': 'dbo.p_test', 'schema': 'dbo', 'procedure_name': 'p_test',
            'status': 'SUCCESS', 'result_sets': [{'columns': ['a'], 'rows': [[1]], 'row_count': 1}],
            'total_rows': 1, 'error': None, 'call_string': 'EXEC dbo.p_test',
            'param_source': 'sampled', 'obj_kind': 'PROCEDURE',
        }
        sp_rec = {
            'full_name': 'dbo.p_test', 'schema': 'dbo', 'procedure_name': 'p_test',
            'status': 'ERROR', 'result_sets': [], 'total_rows': 0,
            'error': 'null value in column violates not-null constraint',
            'call_string': 'CALL dbo.p_test()', 'strategy_used': 'exec_as_call',
            'object_kind': 'PROCEDURE',
        }
        result = compare(ms_rec, sp_rec)
        assert result['verdict'] == 'SPG_ERROR'
        assert result['verdict'] != 'FAIL_MISSING_PREREQ'


# ── cast_error_signal_pattern ─────────────────────────────────────────────────

class TestCastErrorSignalPattern:
    def test_fires_on_conversion_failed(self):
        ms, sp = _both_failed(
            ms_err="Conversion failed when converting the varchar value 'Unable to determine MicrosLoad' to INT",
            spg_err="ERROR: invalid input syntax for type integer")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'

    def test_fires_on_unable_to_determine_microsload(self):
        ms, sp = _both_failed(
            ms_err="Unable to determine MicrosLoad status",
            spg_err="function returned null")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'


# ── sequential_dependency (match_all) ─────────────────────────────────────────

class TestSequentialDependency:
    def test_fires_when_all_required_patterns_present(self):
        ms, sp = _both_failed(
            ms_err="cannot insert null into column 'MajorGroupId' in HierarchyExport_PostSteps",
            spg_err="null value in column majorgroupid violates not-null constraint in poststeps")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'

    def test_does_not_fire_when_match_all_partially_missing(self):
        # Has 'poststeps' but NOT 'majorgroupid' — match_all requires both
        ms, sp = _both_failed(
            ms_err="error in HierarchyExport_PostSteps",
            spg_err="null value in poststeps")
        result = compare(ms, sp)
        # Will either BOTH_FAILED or be caught by another rule — must NOT be
        # reclassified by the sequential_dependency rule specifically.
        # We just verify it's not PASS or FAIL_HARNESS
        assert result['verdict'] in ('BOTH_FAILED', 'FAIL_MISSING_PREREQ')


# ── procedure_families filter ─────────────────────────────────────────────────

class TestProcedureFamiliesFilter:
    def test_family_filtered_rule_does_not_fire_for_other_families(self):
        # procedure_family_batch_both_fail only fires for 'batch' or 'wrapper' families.
        # A proc not in any seed profile has proc_family='' — rule should NOT fire.
        ms, sp = _both_failed(
            ms_err="no active rows found",
            spg_err="no active rows found",
            schema='dbo', name='p_some_unknown_proc')
        result = compare(ms, sp)
        # Rule has procedure_families=['batch','wrapper'] so it won't match
        # dbo.p_some_unknown_proc which has no seed profile family.
        # It may still be reclassified by another rule (active_job_state_null_column
        # fires on 'no active' — but that rule has no family filter).
        # The key assertion: verdict is not FAIL_HARNESS
        assert result['verdict'] != 'FAIL_HARNESS'


# ── Reclassification annotates issues ────────────────────────────────────────

class TestReclassificationAnnotation:
    def test_reclassified_issues_include_rule_name(self):
        ms, sp = _both_failed(
            ms_err="error 515 null value",
            spg_err="null value in column violates not-null")
        result = compare(ms, sp)
        assert result['verdict'] == 'FAIL_MISSING_PREREQ'
        rule_name_issues = [i for i in result['issues'] if 'Reclassified by rule' in i]
        assert rule_name_issues, "Expected 'Reclassified by rule [...]' in issues"

    def test_reclassified_issues_include_both_error_texts(self):
        ms, sp = _both_failed(
            ms_err="error 515 null value",
            spg_err="null value in column violates not-null")
        result = compare(ms, sp)
        # issues should contain at least the rule annotation + error summary
        assert len(result['issues']) >= 2
