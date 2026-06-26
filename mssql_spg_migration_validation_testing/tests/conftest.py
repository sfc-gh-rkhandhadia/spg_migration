"""
conftest.py — pytest configuration for the migration validation test suite.

Stubs out modules that require live DB connections at import time so that
unit tests can run offline. The stub modules expose no-op implementations
of the functions called by compare_proc_outputs.py and reporting.py.
"""
import sys
import types

def _make_stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod

# validation_db: called by compare_proc_outputs.py at module level and in main()
_vdb = _make_stub(
    'validation_db',
    create_run=lambda *a, **kw: (None, 0),
    insert_results=lambda *a, **kw: None,
    complete_run=lambda *a, **kw: None,
)
sys.modules.setdefault('validation_db', _vdb)

# reporting: called for summary table printing
_rpt = _make_stub(
    'reporting',
    print_summary_table=lambda *a, **kw: None,
)
sys.modules.setdefault('reporting', _rpt)
