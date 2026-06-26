"""
Tests for schema filter functions in config.py.

These run without any DB connection — pure Python logic.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

# Set required env vars to satisfy config.py module-level _require() calls
_REQUIRED_ENV = {
    'MSSQL_HOST': 'localhost', 'MSSQL_PORT': '1433', 'MSSQL_USER': 'sa',
    'MSSQL_PASSWORD': 'test', 'MSSQL_DATABASE': 'TestDB',
    'SPG_HOST': 'test.snowflakecomputing.app', 'SPG_USER': 'snowflake_admin',
    'SPG_PASSWORD': 'test', 'SPG_DATABASE': 'postgres',
}
for k, v in _REQUIRED_ENV.items():
    os.environ.setdefault(k, v)

from config import is_mssql_system_schema, is_spg_system_schema


# ── MSSQL ─────────────────────────────────────────────────────────────────────

class TestMssqlSystemSchema:
    def test_blocks_sys(self):
        assert is_mssql_system_schema('sys')

    def test_blocks_information_schema_upper(self):
        assert is_mssql_system_schema('INFORMATION_SCHEMA')

    def test_blocks_information_schema_lower(self):
        # Case-insensitive after our fix
        assert is_mssql_system_schema('information_schema')

    def test_blocks_information_schema_mixed(self):
        assert is_mssql_system_schema('Information_Schema')

    def test_allows_dbo(self):
        assert not is_mssql_system_schema('dbo')

    def test_allows_api(self):
        assert not is_mssql_system_schema('api')

    def test_allows_reporting(self):
        assert not is_mssql_system_schema('reporting')

    def test_allows_stg(self):
        assert not is_mssql_system_schema('stg')

    def test_allows_customer_schema(self):
        assert not is_mssql_system_schema('acuity_data')


# ── SPG / Postgres ────────────────────────────────────────────────────────────

class TestSpgSystemSchema:
    # Exact matches
    def test_blocks_pg_catalog(self):
        assert is_spg_system_schema('pg_catalog')

    def test_blocks_pg_toast(self):
        assert is_spg_system_schema('pg_toast')

    def test_blocks_information_schema(self):
        assert is_spg_system_schema('information_schema')

    def test_blocks_cron_exact(self):
        # pg_cron extension schema
        assert is_spg_system_schema('cron')

    def test_blocks_lake_exact(self):
        # Snowflake lake internal schema
        assert is_spg_system_schema('lake')

    def test_blocks_incremental_exact(self):
        assert is_spg_system_schema('incremental')

    def test_blocks_map_type_exact(self):
        assert is_spg_system_schema('map_type')

    # Prefix matches
    def test_blocks_pg_prefix(self):
        assert is_spg_system_schema('pg_temp_1')
        assert is_spg_system_schema('pg_toast_12345')

    def test_blocks_snowflake_prefix(self):
        assert is_spg_system_schema('snowflake_cdc')
        assert is_spg_system_schema('snowflake_internal')

    def test_blocks_extension_prefix(self):
        assert is_spg_system_schema('extension_btree')

    def test_blocks_dunder_pg_prefix(self):
        assert is_spg_system_schema('__pg_replication__')

    def test_blocks_dunder_lake_prefix(self):
        assert is_spg_system_schema('__lake__metadata')

    # Default exclude (public)
    def test_blocks_public_by_default(self):
        assert is_spg_system_schema('public')

    # Customer schemas that MUST be allowed
    def test_allows_dbo(self):
        assert not is_spg_system_schema('dbo')

    def test_allows_api(self):
        assert not is_spg_system_schema('api')

    def test_allows_reporting(self):
        assert not is_spg_system_schema('reporting')

    def test_allows_stg(self):
        assert not is_spg_system_schema('stg')

    # These were incorrectly blocked before the cron/lake/incremental prefix fix
    def test_allows_cron_billing(self):
        assert not is_spg_system_schema('cron_billing')

    def test_allows_cron_jobs(self):
        assert not is_spg_system_schema('cron_jobs')

    def test_allows_lake_data(self):
        assert not is_spg_system_schema('lake_data')

    def test_allows_lake_operations(self):
        assert not is_spg_system_schema('lake_operations')

    def test_allows_incremental_staging(self):
        assert not is_spg_system_schema('incremental_staging')

    def test_allows_map_type_lookup(self):
        assert not is_spg_system_schema('map_type_lookup')

    def test_case_insensitive_prefix(self):
        # is_spg_system_schema lowercases before checking
        assert is_spg_system_schema('PG_Catalog')
        assert is_spg_system_schema('Information_Schema')
