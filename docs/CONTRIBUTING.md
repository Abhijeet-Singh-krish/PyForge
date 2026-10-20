# Contributing to PyForge

1. All curriculum changes must pass `python3 -m pyforge.validate_curriculum`.
2. All backend or sandbox changes must pass `python3 -m unittest discover -s tests -p "test_*.py" -v` and `python3 scripts/production_checklist.py`.
3. Never commit secrets, disable sandbox restrictions, or expose `hidden_tests` in client API responses.
