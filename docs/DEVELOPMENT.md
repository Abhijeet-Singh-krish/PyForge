# Local Development Guide

Run the validation, database migration, and test suite locally:
```bash
PYTHONPATH=. python3 -m pyforge.validate_curriculum
PYTHONPATH=. python3 -m unittest discover -s tests -p "test_*.py" -v
PYTHONPATH=. python3 scripts/production_checklist.py
```
