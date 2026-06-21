# SPG Migration Tools

Tools and skills for migrating SQL Server (MSSQL) databases to Snowflake Postgres (SPG).

## Skills

### `mssql_spg_migration_validation_testing`

End-to-end validation of an MSSQL → SPG migration:

- **Behavioral validation** — executes stored procedures, functions, views, and triggers on both MSSQL and SPG and compares results
- **Schema validation** — checks table/view/procedure/function/trigger/index/constraint coverage in SPG vs MSSQL
- **Markdown report** — two-part report: Part 1 (DDL structure) and Part 2 (behavioral execution parity)
- **PowerPoint report** — 23-slide deck with KPIs, schema coverage, pass rate charts, remediation priorities

#### Key scripts

| Script | Purpose |
|--------|---------|
| `run.py` | Main validation runner |
| `compare_proc_outputs.py` | Compares MSSQL vs SPG procedure/function/view outputs |
| `mssql_proc_executor.py` | Executes objects against SQL Server |
| `spg_proc_executor.py` | Executes objects against Snowflake Postgres |
| `generate_validation_markdown.py` | Generates two-part markdown validation report |
| `generate_migration_report.py` | Generates PowerPoint migration report |
| `alternate_flow_rules.yaml` | Rule-driven reclassification of BOTH_FAILED → FAIL_MISSING_PREREQ |
| `load_mssql_to_spg.py` | Loads data from MSSQL into SPG (FK-safe, no DDL) |
| `run_validation.sh` | Wrapper to run full validation suite |
| `run_compare_and_reports.sh` | Wrapper to regenerate comparison + markdown + PPTX reports |

#### Environment variables

```bash
MSSQL_HOST=localhost
MSSQL_PORT=1434
MSSQL_USER=sa
MSSQL_PASSWORD=...
MSSQL_DB=MENU_MANAGEMENT

SPG_HOST=<host>.snowflakecomputing.app
SPG_USER=snowflake_admin
SPG_PASSWORD=...
SPG_DATABASE=postgres

MSSQL_SPG_SHARED_DIR=/path/to/shared-workflow
```
