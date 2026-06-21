#!/bin/bash
export MSSQL_HOST="localhost"
export MSSQL_PORT="1434"
export MSSQL_USER="sa"
export MSSQL_PASSWORD="REDACTED_MSSQL_PASSWORD"
export MSSQL_DATABASE="MENU_MANAGEMENT"
export SPG_HOST="your-spg-host.snowflakecomputing.app"
export SPG_USER="snowflake_admin"
export SPG_PASSWORD="REDACTED_SPG_PASSWORD"
export SPG_DATABASE="postgres"
export VALIDATION_OUTPUT_DIR="/Users/rkhandhadia/Documents/Armtrack/Validation Results/jim"
export VALIDATION_SKIP_WRITES="false"
export REPORT_CLIENT="Armtrack MENU_MANAGEMENT"
export REPORT_AUTHOR="Rekha Khandhadia"

SCRIPT_DIR="/Users/rkhandhadia/.snowflake/cortex/skills/mssql_spg_migration_validation_testing/scripts"
cd "$SCRIPT_DIR"
python3 run.py --all 2>&1
