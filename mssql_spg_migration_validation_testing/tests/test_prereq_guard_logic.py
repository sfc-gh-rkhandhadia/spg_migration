"""
Tests for pure-logic functions in prereq_guard.py.

No DB connections required — only tests functions that operate on
in-memory data: pattern detection, column resolution, default value
generation, and the PrereqRestoreError exception hierarchy.
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

from prereq_guard import (
    PrereqRestoreError,
    detect_mssql_prereqs,
    detect_spg_prereqs,
    _resolve,
    _mssql_default,
    _spg_default,
    _normalise_fixed,
)


# ── PrereqRestoreError ────────────────────────────────────────────────────────

class TestPrereqRestoreError:
    def test_is_subclass_of_runtime_error(self):
        assert issubclass(PrereqRestoreError, RuntimeError)

    def test_is_subclass_of_exception(self):
        assert issubclass(PrereqRestoreError, Exception)

    def test_can_be_raised_and_caught_as_runtime_error(self):
        with pytest.raises(RuntimeError):
            raise PrereqRestoreError("test message")

    def test_can_be_caught_specifically(self):
        with pytest.raises(PrereqRestoreError):
            raise PrereqRestoreError("test message")

    def test_plain_runtime_error_is_not_prereq_restore_error(self):
        # Ensures the two exception types are distinguishable
        with pytest.raises(RuntimeError):
            raise RuntimeError("plain")
        # Plain RuntimeError should NOT be caught by PrereqRestoreError handler
        caught_as_prereq = False
        try:
            raise RuntimeError("plain")
        except PrereqRestoreError:
            caught_as_prereq = True
        except RuntimeError:
            pass
        assert not caught_as_prereq

    def test_prereq_restore_error_is_caught_by_runtime_error_handler(self):
        caught = False
        try:
            raise PrereqRestoreError("prereq message")
        except RuntimeError:
            caught = True
        assert caught


# ── detect_mssql_prereqs ──────────────────────────────────────────────────────

class TestDetectMssqlPrereqs:
    def test_detects_active_job_state_via_getjobstatusid(self):
        body = "SELECT dbo.F_MICROSLOAD_GETJOBSTATUSID(@x)"
        assert detect_mssql_prereqs(body) == ['active_job_state']

    def test_detects_active_job_state_via_getcurrentjoblogid(self):
        body = "EXEC dbo.F_MICROSLOAD_GETCURRENTJOBLOGID"
        assert detect_mssql_prereqs(body) == ['active_job_state']

    def test_deduplicates_same_key_from_two_patterns(self):
        # Both patterns map to 'active_job_state' — key appears once only
        body = "F_MICROSLOAD_GETJOBSTATUSID() AND F_MICROSLOAD_GETCURRENTJOBLOGID()"
        result = detect_mssql_prereqs(body)
        assert result.count('active_job_state') == 1

    def test_detects_definition_staging(self):
        body = "FROM stg.MICROSLOAD_DEFINITIONSTAGING WHERE ..."
        assert 'definition_staging' in detect_mssql_prereqs(body)

    def test_detects_menuitem_definition_stg(self):
        body = "INSERT INTO dbo.MENUITEMDEFINITION_STG ..."
        assert 'menuitem_definition_stg' in detect_mssql_prereqs(body)

    def test_empty_body_returns_empty(self):
        assert detect_mssql_prereqs('') == []

    def test_none_body_returns_empty(self):
        assert detect_mssql_prereqs(None) == []

    def test_unrelated_body_returns_empty(self):
        body = "SELECT * FROM Orders WHERE OrderId = @id"
        assert detect_mssql_prereqs(body) == []

    def test_case_insensitive(self):
        # Proc bodies may be stored with mixed case
        body = "select dbo.f_microsload_getjobstatusid(@x)"
        assert detect_mssql_prereqs(body) == ['active_job_state']

    def test_ordering_matches_pattern_list(self):
        # First matching pattern wins ordering
        body = "MICROSLOAD_DEFINITIONSTAGING ... F_MICROSLOAD_GETJOBSTATUSID"
        result = detect_mssql_prereqs(body)
        assert result[0] == 'active_job_state'  # F_MICROSLOAD_GETJOBSTATUSID comes first in _MSSQL_PATTERNS


# ── detect_spg_prereqs ────────────────────────────────────────────────────────

class TestDetectSpgPrereqs:
    def test_detects_active_job_state_lowercase(self):
        body = "select dbo.f_microsload_getjobstatusid(v_id)"
        assert detect_spg_prereqs(body) == ['active_job_state']

    def test_detects_printers_stg(self):
        body = "from stg.printers_stg where ..."
        assert 'printers_stg' in detect_spg_prereqs(body)

    def test_case_insensitive_because_body_is_lowercased(self):
        # detect_spg_prereqs lowercases the body before matching, so uppercase
        # input is matched correctly — SPG proc bodies may arrive with any casing.
        body = "SELECT FROM STG.PRINTERS_STG"
        assert 'printers_stg' in detect_spg_prereqs(body)

    def test_empty_returns_empty(self):
        assert detect_spg_prereqs('') == []

    def test_none_returns_empty(self):
        assert detect_spg_prereqs(None) == []


# ── _resolve ─────────────────────────────────────────────────────────────────

class TestResolve:
    def _col_map(self, *cols):
        return {c: {'name': c, 'data_type': 'varchar'} for c in cols}

    def test_returns_first_matching_candidate(self):
        col_map = self._col_map('jobactiveflag', 'isactive')
        assert _resolve(['jobactiveflag', 'isactive'], col_map) == 'jobactiveflag'

    def test_skips_non_matching_candidates(self):
        col_map = self._col_map('isactive')
        assert _resolve(['jobactiveflag', 'isactive'], col_map) == 'isactive'

    def test_returns_none_when_no_match(self):
        col_map = self._col_map('someothercol')
        assert _resolve(['jobactiveflag', 'isactive'], col_map) is None

    def test_case_insensitive_lookup(self):
        col_map = {'jobactiveflag': {'name': 'JobActiveFlag', 'data_type': 'bit'}}
        assert _resolve(['JobActiveFlag'], col_map) == 'jobactiveflag'

    def test_empty_candidates_returns_none(self):
        col_map = self._col_map('col1')
        assert _resolve([], col_map) is None

    def test_none_candidates_returns_none(self):
        col_map = self._col_map('col1')
        assert _resolve(None, col_map) is None


# ── _mssql_default ────────────────────────────────────────────────────────────

class TestMssqlDefault:
    def _info(self, dtype):
        return {'data_type': dtype, 'is_identity': False, 'is_nullable': 0}

    def test_int_returns_zero(self):
        assert _mssql_default('col', self._info('int'), {}) == '0'

    def test_bigint_returns_zero(self):
        assert _mssql_default('col', self._info('bigint'), {}) == '0'

    def test_decimal_returns_zero(self):
        assert _mssql_default('col', self._info('decimal'), {}) == '0'

    def test_bit_returns_zero(self):
        assert _mssql_default('col', self._info('bit'), {}) == '0'

    def test_datetime_returns_getdate(self):
        assert _mssql_default('col', self._info('datetime'), {}) == 'GETDATE()'

    def test_date_returns_getdate(self):
        assert _mssql_default('col', self._info('date'), {}) == 'GETDATE()'

    def test_uniqueidentifier_returns_newid(self):
        assert _mssql_default('col', self._info('uniqueidentifier'), {}) == 'NEWID()'

    def test_varchar_returns_guard_prereq_literal(self):
        assert _mssql_default('col', self._info('varchar'), {}) == "'guard-prereq'"

    def test_nvarchar_returns_guard_prereq_literal(self):
        assert _mssql_default('col', self._info('nvarchar'), {}) == "'guard-prereq'"

    def test_fixed_value_overrides_type_inference(self):
        assert _mssql_default('mycol', self._info('int'), {'mycol': '99'}) == "'99'"

    def test_getdate_fixed_value(self):
        result = _mssql_default('col', self._info('varchar'), {'col': 'GETDATE()'})
        assert result == 'GETDATE()'


# ── _spg_default ──────────────────────────────────────────────────────────────

class TestSpgDefault:
    def _info(self, dtype):
        return {'data_type': dtype, 'is_identity': False, 'is_nullable': True}

    def test_integer_returns_zero(self):
        assert _spg_default('col', self._info('integer'), {}) == '0'

    def test_bigint_returns_zero(self):
        assert _spg_default('col', self._info('bigint'), {}) == '0'

    def test_numeric_returns_zero(self):
        assert _spg_default('col', self._info('numeric'), {}) == '0'

    def test_boolean_returns_false(self):
        assert _spg_default('col', self._info('boolean'), {}) == 'false'

    def test_timestamp_returns_now(self):
        assert _spg_default('col', self._info('timestamp'), {}) == 'NOW()'

    def test_date_returns_now(self):
        assert _spg_default('col', self._info('date'), {}) == 'NOW()'

    def test_uuid_returns_gen_random_uuid(self):
        assert _spg_default('col', self._info('uuid'), {}) == 'gen_random_uuid()'

    def test_varchar_returns_guard_prereq_literal(self):
        assert _spg_default('col', self._info('character varying'), {}) == "'guard-prereq'"

    def test_fixed_value_overrides_type_inference(self):
        assert _spg_default('mycol', self._info('integer'), {'mycol': '42'}) == "'42'"

    def test_now_fixed_value(self):
        result = _spg_default('col', self._info('varchar'), {'col': 'now()'})
        assert result == 'NOW()'


# ── _normalise_fixed ──────────────────────────────────────────────────────────

class TestNormaliseFixed:
    def test_lowercases_keys(self):
        assert _normalise_fixed({'JobActiveFlag': 1}) == {'jobactiveflag': 1}

    def test_mixed_case_keys(self):
        result = _normalise_fixed({'MicrosLoadStatusId': 5, 'StartTime': 'now()'})
        assert 'microsloadstatusid' in result
        assert 'starttime' in result

    def test_values_unchanged(self):
        result = _normalise_fixed({'Col': 'SomeValue'})
        assert result['col'] == 'SomeValue'

    def test_none_returns_empty_dict(self):
        assert _normalise_fixed(None) == {}

    def test_empty_dict_returns_empty_dict(self):
        assert _normalise_fixed({}) == {}
