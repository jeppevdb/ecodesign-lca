# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Project

```bash
python main.py
```

This opens a Tkinter file dialog to select an LCI Excel file, runs the calculation pipeline if the file has changed, then launches the Panel dashboard at `http://localhost:5006/LCA_Dashboard`.

## Dependencies

```bash
pip install -r requirements.txt
```

Key packages: `panel >= 1.6`, `holoviews`, `plotly >= 5.18`, `bokeh`, `pandas`, `numpy`, `openpyxl`.

## Architecture

The project is a two-stage pipeline:

### Stage 1 — Calculation (`exhaustive_result_calculation/`)

Driven by `run_calculation.main(lci_file, out_dir)`. Reads an LCI Excel file and:
1. Extracts metadata and OpenLCA data
2. Generates all combinations of scenarios and parameters
3. Calculates LCI variants (distribution, end-of-life, impacts) for each combination
4. Writes results to `processed_data/<product_name>/`

Output CSVs:
- `all_results_by_scenario.csv` — all LCI variants (scenarios + design changes)
- `all_results_by_scenario_base_design.csv` — base design only
- `all_results_by_parameter_base_design.csv` — parameter sensitivity

State is tracked in `last_state.json` (file modification time) to skip recalculation when unchanged.

### Stage 2 — Dashboard (`impact_report_generation/`)

Driven by `app.run_dashboard(out_dir)`. Builds a Panel `FastListTemplate` dashboard with nested tabs:

- **Executive Summary** — top-level KPIs
- **Summary** — Sankey, single-score bars, sunburst uncertainty, tables, design summary
- **Reference Product** — three-level drill-down: system → assembly → component
- **Design Changes** — same three-level structure, comparing design variants

Data loaders in `src/utils/loaders.py` use `@lru_cache`; the cache key includes the data directory path. Each tab's visualization lives in its own module under `src/tabs/`.

### Data Flow

```
raw_data/lci_file_*.xlsx
    → run_calculation (Stage 1)
    → processed_data/<product>/  (CSVs + Excel)
    → Panel dashboard (Stage 2)
```

## No Test Suite

There is no configured test runner. One isolated test file exists at `impact_report_generation/src/tabs/design_changes/test.py`.
