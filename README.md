LCA4PD calculation model - run with "python main.py"

## Version 2.0 (in development, branch `claude/tool-2-0-redesign-uzq1yf`)

Version 2.0 does everything in one interface: setup, databases, modelling, calculation.
No Excel data entry and no openLCA. The design is described in `docs/design_2.0.md`.

Requirements: Python 3.11 or newer.

    pip install -r requirements.txt
    python -m lca4pd

This opens the tool in your browser. Projects and the database library are stored in a
`workspace/` folder next to where you start it (change with `--workspace DIR`). That folder
is ignored by git: databases you upload stay on your computer.

You bring your own data: upload the Excel file with impact results from your database
provider (BAFU, IdeMat, ecoinvent) in the step "Databases", and the EF 3.1 file with
elementary flows and characterisation factors if you want to enter direct emissions.

To check a database file without starting the tool:

    python -m lca4pd.databases inspect path/to/file.xlsx

Run the tests with `pip install -r requirements-dev.txt` and `python -m pytest`.

Built so far: data model and checks, database import, calculation, the guided interface
including scenarios, design alternatives and the full overview table, and the report.
