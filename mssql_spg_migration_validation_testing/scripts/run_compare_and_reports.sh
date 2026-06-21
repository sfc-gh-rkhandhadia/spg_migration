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
export REPORT_CLIENT="Armtrack MENU_MANAGEMENT"
export REPORT_AUTHOR="Rekha Khandhadia"
export SHARED_DIR="/Users/rkhandhadia/Documents/Armtrack/shared-workflow"

OUTPUT_DIR="/Users/rkhandhadia/Documents/Armtrack/Validation Results/jim"
SCRIPT_DIR="/Users/rkhandhadia/.snowflake/cortex/skills/mssql_spg_migration_validation_testing/scripts"
TODAY=$(date +%Y%m%d)

cd "$SCRIPT_DIR"

echo "=== Step 1: Comparing procedure outputs ==="
python3 compare_proc_outputs.py 2>&1

echo ""
echo "=== Step 2: Generating Markdown report ==="
# Delete any existing file so it gets freshly regenerated
rm -f "${OUTPUT_DIR}/Migration_Validation_${TODAY}.md"
python3 generate_validation_markdown.py \
  --out-dir "${OUTPUT_DIR}" \
  --client "Armtrack MENU_MANAGEMENT" 2>&1

echo ""
echo "=== Step 3: Generating PowerPoint report ==="
# Delete existing so generate_migration_report doesn't skip it
rm -f "${HOME}/Downloads/Migration_Validation_${TODAY}.pptx"
rm -f "${HOME}/Downloads/Migration_Validation_${TODAY}.md"
python3 generate_migration_report.py 2>&1

echo ""
echo "=== Step 4: Copying PPTX to output directory ==="
cp "${HOME}/Downloads/Migration_Validation_${TODAY}.pptx" \
   "${OUTPUT_DIR}/Migration_Validation_ArmtrackMENU_${TODAY}.pptx" && \
   echo "Copied PPTX to: ${OUTPUT_DIR}/Migration_Validation_ArmtrackMENU_${TODAY}.pptx"

echo ""
echo "=== Final files in output directory ==="
ls -lh "${OUTPUT_DIR}"/Migration_Validation_*.{md,pptx} 2>/dev/null
