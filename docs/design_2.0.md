# Tool 2.0 – agreed design

Status: design agreed step by step with the project owner. Build steps 1 (data model,
project file, validation rules; `lca4pd/model`), 2 (database import; `lca4pd/databases`,
`lca4pd/method`) and 3 (calculation; `lca4pd/calculation`) are implemented, with tests in
`tests/`.
This document is the reference for implementation. Section 12 lists what is still open.

## 1. Goals

- One interface for the whole workflow: setup, databases, modelling, calculation, report.
  No Excel data entry, no openLCA.
- Users supply their own impact-factor files (ecoinvent, BAFU, IdeMat, …). The tool ships
  no licensed data.
- Guided data entry with instant validation, a permanent overview of what is missing, and
  a full-table view as a secondary way to inspect and edit.
- Product structure of any depth instead of system → assembly → component.
- The report keeps its look and chart types.

Removed from 1.0: the openLCA IPC backend (`extract_openlca_data.py`), the Excel LCI
template as the place of data entry, the tkinter file picker. No importer for 1.0 files.

## 2. Technology

- Panel (Python) for everything; the modelling steps are added to the same app as the report.
- A project is one local SQLite file. It stores **references** to datasets only, never
  impact factors. Results are saved in a separate file next to it, so the report opens
  without the database files and the project file can be shared without any impact data.
- Excel is export-only (full LCI table, result tables).

## 3. Step 0 – Project and calculation setup

Per project (no presets). Everything here can be changed later.

- Name, functional unit, scope, reference flow.
- Markets (countries/regions) in scope; at least one.
- Life-cycle stages. Default: Raw materials, Manufacturing, Distribution, Use, End-of-Life.
  Stages can be renamed and added; distribution, use and end-of-life each stay tied to one
  stage because the pathway mechanisms depend on them.
- Optional features, each a toggle. If off, the user is never prompted for it and the
  matching report sections are hidden:
  - uncertainty (pedigree matrix)
  - GHG Protocol category
  - EN 15804 module
  - cost
  - internal part numbers
  - scenarios
  - design alternatives

Weight is not a toggle: it is required wherever a pathway uses it (section 6).

## 4. Step 1 – Databases

### Upload flow

1. Upload an Excel file; the tool proposes a reading protocol, the user confirms.
2. Preview and checks: all 16 EF 3.1 categories found with expected units, no duplicate
   keys, no non-numeric values, warning if the file looks like EF 3.0.
3. Cross-check where possible (file single score vs. the tool's own, or internal sums).
4. Register with name, version and file fingerprint. Several databases can be active.
5. Replacing a database re-links entries by dataset key and lists what disappeared or changed.

Each database gets a **coverage table** (which categories it really provides). Gaps and
derived values are flagged in the missing-items panel and in the report.

### Method

- EF 3.1, 16 impact categories. Climate change sub-indicators are **not** read for now.
- Normalised, weighted and single-score results are computed by the tool from characterised
  values using the EF 3.1 normalisation and weighting factors.
- Direct emissions (elementary flows) are supported. The characterisation-factor list is an
  uploadable file, so it can be updated; whether a copy is bundled depends on a licence
  check by the project owner.

### Protocols

A protocol is a configuration file, not code: sheet, header rows, key/name/location/unit
columns, mapping of the file's category names to EF 3.1, and the value mode. User-defined
protocols are a later feature.

Two value modes are needed:

| Mode | Meaning |
|---|---|
| `characterised` | File gives native units (kg CO2-eq, …). |
| `weighted_points` | File gives normalised-and-weighted points per category; the tool calculates back: characterised = points × normalisation factor ÷ weighting factor. Values are labelled as derived. |

Findings from the supplied files:

**BAFU 2026 v1** (`characterised`)
- Sheet `BAFU_2026 v1`, method names in row 1, headers in row 2, data from row 3; 11,947 datasets.
- Columns: Product, Category, Sub-category, Unit, then IPCC 2021, Ecological Scarcity 2021
  and EF 3.1 blocks. "Land use" exists under two methods, so the protocol must read the
  method row, not only the header.
- No dataset ID: the product name is the key. Location is the suffix after ` - `.
- No EF single score; cross-check is fossil + biogenic + land use = total climate change
  (holds for all datasets).
- Some names have broken character encoding; 111 datasets have category `#N/A`.

**IdeMat 2026** (`weighted_points`)
- Sheet `Idemat2026 midpoints`, three header rows, section-heading rows between data rows;
  2,658 datasets.
- EF 3.1 total in column 72, the 16 categories in columns 73–88 (0-based), all in points.
- Back-calculation checked on climate change against IdeMat's carbon footprint column:
  all 2,589 comparable datasets within 1 %. Category points sum to the EF total everywhere.
- Water use is zero for 2,543 datasets: effectively not covered.
- Key: full code including date (column 0). The short code (column 2) is duplicated for
  7 datasets; it is used only for re-linking after a version update.
- Licence: CC BY-NC, excludes sellers of LCA software. Relevant if the tool is ever sold.

**ecoinvent** – protocol to be written from public documentation of the cumulative LCIA
file and tested locally by the project owner (file cannot be shared).

## 5. Step 2a – Gate-to-customer distribution

Defined once per market before the tree is built: one or more transport legs (dataset +
distance). Applied to the product's total weight.

## 6. Step 2b – Product tree

A tree of nodes of any depth. Entries can sit on **any** node.

### Node fields

| Field | Shown | Notes |
|---|---|---|
| Name | always | unique among siblings |
| Quantity | always | number of this node per one unit of its parent; default 1 |
| Level label | always, optional | free text, display only |
| Internal number | if enabled | company part/assembly number |
| Price | if cost enabled | the actual price of the node, always entered |
| Weight | where needed | entered value is an extra on top of the children's weights unless "this is the total" is ticked |
| Description | optional | |

### Questions asked when a node is created

1. **Where is it produced?** On site → nothing more; its children get the same question.
   At a supplier → select or create a named supplier pathway (transport legs); it applies to
   the node's whole weight and the children are not asked. Only transport from the direct
   supplier to the own site is modelled.
2. **Does one end-of-life pathway apply to the element as a whole?** Yes → select or create
   the pathway; children are not asked. No → the question moves to the children.
   - A node without children must have a pathway or a documented exclusion.
   - A node that answers no but has weight of its own (not from children) needs a pathway
     for that own weight.
3. **Does it have use-stage inputs directly attributable to it?** Only then is the "use"
   entry type offered on the node.

### Rules

- Entry amounts are per one unit of the node; quantities multiply up the tree.
- Cost check: children's prices + the node's own cost entries should equal the node's price;
  a difference is a warning.
- Weight check: entered weight against the summed mass of material inputs; warning.
- Copy only (duplicate a node with everything below it). No linked reuse and no parts-list
  import in 2.0, but the data model must not prevent either.

## 7. Step 3 – Entries

Flow: select node → add entry → choose type → type-specific form → validated and saved.

| Type | Holds |
|---|---|
| Production input | dataset + amount; marked as Raw materials or Manufacturing |
| Production waste | waste-treatment dataset + amount |
| Production emission | elementary flow from the characterisation-factor list + amount |
| Cost | a cost item (e.g. assembly labour) |
| Documented exclusion | description and reason; not calculated, listed in the report |
| Use | only on flagged nodes; one amount, one dataset per market; direct emissions allowed |

Common fields: description, dataset via search across all databases (never typed), amount
with optional note on how it was derived, unit fixed by the dataset with conversion within
the same kind of unit, life-cycle stage. If enabled: parameter links, pedigree scores,
GHG Protocol category, EN 15804 module.

No helper calculators and no amounts linked to other entries.

Market-specific datasets exist only in gate-to-customer distribution, use entries and
end-of-life pathways.

Checks: dataset selected and still present; amount numeric; unit compatible; negative
amount needs confirmation.

## 8. Step 4 – Scenarios (optional)

- A scenario has a name, description and one or more parameters that always switch together.
- A parameter has best and worst multipliers with written assumptions. **Average is always 1**:
  the entered value is the average case.
- A parameter can act on: entry amounts, pathway legs, node weight, node price.
- Linked by pick-list from the entry/leg/node, and listed with resulting values on the
  parameter page.
- One set of values for all markets.
- Checks: values complete; parameter that affects nothing; end-of-life shares still sum to
  100 % in best and worst cases; after calculation, best higher than worst is flagged.

## 9. Step 5 – Design alternatives (optional)

- Any node can have alternatives: a second version of the node and everything below it,
  with name, short and long description. Everything may differ from the base.
- Start as a copy of the base (default) or empty. Base edits do not propagate; a computed
  differences view shows what the alternative changes.
- An alternative can be "removed" (part eliminated).
- No alternatives inside alternatives.
- Calculated one at a time against the base. Named combinations come later; the data model
  stores a design as a set of substitutions so combinations need no restructuring.

## 10. Steps 6 and 7 – Overview table and missing-items panel

### Full LCI overview

- One row per entry; two views:
  - *as entered* – editable for amount, note, description, stage and classification fields;
    dataset via the search dialog; structure not editable here; same checks as the forms;
    bulk edit of one field across selected rows.
  - *as calculated* – read-only, for a chosen market, scenario setting and design, with
    quantities multiplied through and pathways expanded.
- Filter, sort, group; Excel export only.

### Missing-items panel

Visible in every step; each item links to where it is fixed.

Blockers (calculation not possible; the way around a gap is a documented exclusion):
- no database, or a dataset no longer in its database
- entry without dataset or amount
- node with no entries and no children
- weight missing where a pathway needs it
- market without gate-to-customer distribution
- end-of-life gap
- use entry without a dataset for a market
- parameter without best or worst value

Warnings (calculation runs):
- cost mismatch; weight vs. material mass mismatch
- node flagged for use-stage inputs but without any
- parameter that affects nothing; alternative identical to its base
- database coverage gaps and derived values
- enabled optional fields left empty (shown in the report as unclassified / not scored)

## 11. Step 8 – Calculation and report

### Calculation

- Every design × best/average/worst × every market, plus one-at-a-time parameter variation
  for the base design.
- Pathway impacts are attributed to where the weight came from: if a node's weight is the
  sum of its children's weights each child gets its share; weight entered on the node itself
  keeps the impact on that node.
- Results are cached with a fingerprint of model and databases; the report flags stale results.

### Report

| Area | 2.0 |
|---|---|
| Reference product | one section with a node picker instead of three fixed levels |
| Design changes | one list of alternatives, compared at their own level and at product level |
| Sunburst, Sankey | as deep as the tree, with a depth limit |
| Own entries of a node with children | separate slice, e.g. "Housing – own processes" |
| Executive summary | top contributors shown for each level of the tree |
| Impact categories | 16 EF 3.1 categories + single score, read from the method |
| Classification views (new) | by GHG Protocol category (climate change) and by EN 15804 module, with unclassified share |
| Data-quality notes (new) | results relying on derived values or coverage gaps |

Sections for switched-off options are hidden.

## 12. Open points

- ecoinvent protocol is unverified until tested on a real file.
- Source and bundling of the EF 3.1 normalisation/weighting factors and the
  characterisation-factor list (licence check pending for the latter).
- Exact pick-lists for GHG Protocol categories and EN 15804 modules.

## 13. Later, kept in mind in the data model

- Component library shared across projects; linked reuse of nodes.
- Parts-list (bill of materials) import.
- Named combinations of design alternatives.
- User-defined database protocols.
- Climate change sub-indicators.
- Generated GHG Protocol and EPD reports.

## 14. Data model sketch

- `project` – settings, toggles, stages, markets.
- `database` – name, version, protocol, file fingerprint, coverage.
- dataset reference – (database, dataset key) plus cached name, unit, location for display.
- `node` – parent, quantity, label, internal number, price, weight, weight-is-total,
  produced on site, supplier pathway, end-of-life answers and pathways, use flag;
  for alternatives: the base node it replaces, descriptions, removed flag.
- `entry` – node, type, stage, description, dataset or flow reference, amount, unit, note,
  optional classification and pedigree fields; per-market datasets for use entries.
- `pathway` (supplier, gate-to-customer, end-of-life) and `pathway_leg` (dataset, amount per
  kg or distance, market where relevant, same optional fields as entries).
- `scenario`, `parameter`, `parameter_link` (target: entry, leg, node weight, node price).
- `design` – a named set of (base node → alternative) substitutions.
- results cache.

## 15. Proposed build order

1. Data model, project file and validation rules, with tests (no interface).
2. Database import: protocol engine, BAFU and IdeMat protocols, EF 3.1 normalisation and
   weighting, characterisation-factor upload, coverage table; then the ecoinvent protocol.
3. Calculation engine on the tree: quantities, pathways, markets, scenarios, alternatives,
   and the "as calculated" inventory; tested against a small hand-calculated example.
4. Guided interface: setup, databases, pathways, tree, entries, missing-items panel.
5. Scenarios, design alternatives, overview table.
6. Report generalised to the tree and to EF 3.1.
7. Classification views and data-quality notes.

## 16. Choices made while building step 1

These go beyond what was discussed and are open to change.

- **Scope:** removing the distribution, use or end-of-life stage from the project switches
  off the matching questions and checks (e.g. a cradle-to-gate study).
- **Documented exclusion** is also accepted in place of a supplier pathway, of an
  end-of-life pathway for a whole element, and of the pathway for an element's own weight.
- **Weight check:** warns when raw-material inputs add up to less than 90 % or more than
  150 % of the element's own weight. **Cost check:** tolerance 0.5 %.
- **Pedigree:** five indicators scored 1–5 (reliability, completeness, temporal,
  geographical, technological). The 1.0 template's sixth column is not carried over.
- **Internal numbers:** the same number on elements with different names is flagged;
  the same number on same-named elements is treated as deliberate reuse.
- **Copying an element** does not copy its design alternatives.
- Weights are in kg; prices in the project currency (default EUR).
- Pick-lists: GHG Protocol scope 1, 2 and 3.1–3.15; EN 15804 modules A1–A5, B1–B7, C1–C4, D.

## 17. Build step 2 – database import, as built

- **Formats** are TOML files in `lca4pd/databases/protocols/` (BAFU, IdeMat, ecoinvent).
  Columns are found by heading text, not position. The EF 3.1 flow list has its own reader.
  `.xlsx` and `.ods` are both read. Needs Python 3.11 or newer.
- **Library:** imported factors are stored in a local SQLite file outside the project
  (`Library(directory)`), shared by all projects on the machine. A project refers to a
  database by the fingerprint of the uploaded file. If the file is not in the library the
  missing-items check reports the blocker `database_not_loaded`.
- **Datasets are picked, never typed** (`link.pick`); search covers name, location,
  category and identifier, and can be limited to a kind of unit.
- **Replacing a database** re-links by identifier, then by the version-independent code
  where the database has one (IdeMat short code). Datasets that are gone or changed to
  another kind of unit are marked missing.
- **Left out on import, and reported:** rows with text in place of numbers, datasets
  without any EF 3.1 result, datasets without a unit, and identifiers that occur twice.
- **Coverage:** a category that is non-zero for fewer than 10 % of datasets counts as not
  covered, fewer than 50 % as partly covered.
- **Elementary flows:** country-specific factors are skipped; every flow that has them
  also has a global factor, which is used.
- **EF 3.1 normalisation and weighting factors** are bundled in `lca4pd/method/ef31.py`
  (public JRC reference values). Climate change was verified against IdeMat's data and
  four further normalisation factors against published tables; the JRC site could not be
  reached from the development session, so the remaining values should be checked once
  against the JRC source.
- **ecoinvent:** the protocol follows the publicly described layout and is not verified.
  Check a real file with `python -m lca4pd.databases inspect <file>`; if it is not
  recognised the command prints the file's headings without data.

Measured on the supplied files: BAFU 11,824 datasets read in 5 s; IdeMat 2,633 in 3 s;
EF 3.1 flow list 89,070 flows in about 1 minute; library size 61 MB; search under 0.1 s.

## 18. Build step 3 – calculation, as built

`calculate(project, library)` refuses to run while there are blockers, then returns:

- **inventory** – one row per entry or pathway leg, per run, scaled to one product, with
  the element it is attributed to, its place in the tree, stage, dataset, amount,
  classification fields, the 16 characterised results and the single score. This is the
  "as calculated" view.
- **costs** – the price of every element per run (when cost is switched on).
- **nodes** and **exclusions** – the tree, and everything deliberately left out with reasons.

Runs: every design × best/average/worst × every market, plus best and worst of each
scenario on its own for the base design (their average is the base average run).

Choices made while building it:

- **Supplier transport** is counted in the Raw materials stage (Manufacturing if that
  stage was removed).
- **Weight parameters** scale the weight entered on an element; totals, transport and
  end-of-life follow.
- **Cost:** entered prices stay authoritative. A change below an element (alternative,
  removed part, price parameter) is carried upwards as a difference. A price parameter
  scales the whole price of the element it is linked to.
- **Results file:** separate from the project (see section 2), with a fingerprint of the
  project so the report can tell when results are out of date.
- After a calculation, scenarios whose best case scores higher than their worst case are
  listed (`Results.scenario_direction_warnings`).

Checked against a lamp example worked out by hand (`tests/test_calculation.py`). A product
with 249 elements, 800 entries, 16 designs, 3 markets and 10 scenarios (204 runs) takes
about 3 seconds.
