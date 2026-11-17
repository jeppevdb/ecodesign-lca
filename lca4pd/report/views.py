"""The report layout: the tabs of version 1, generalised to a tree of any depth.

    Quick summary · LCA summary · Reference product · Design changes ·
    GHG Protocol & EN 15804 · About this report

Every tab reads from one ``ReportData``. Sections for options that were
switched off (scenarios, alternatives, cost, uncertainty, classifications)
are left out.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd
import panel as pn

from ..method import ef31
from . import charts
from .data import BASE_DESIGN, OWN, SINGLE_SCORE, ReportData

W = pn.widgets
TEXTS = Path(__file__).parent / "texts"


# ------------------------------------------------------------------ helpers

def _md(text, **kwargs):
    return pn.pane.Markdown(text, sizing_mode="stretch_width", **kwargs)


def _plot(fig):
    return pn.pane.Plotly(fig, sizing_mode="stretch_width", config={"displaylogo": False})


def _fmt(value, digits=4):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "–"
    return f"{value:.{digits}g}"


def _table(frame: pd.DataFrame, name: str, height=None):
    """An interactive table with CSV and Excel downloads."""
    shown = frame.copy()
    for column in shown.columns:
        if pd.api.types.is_float_dtype(shown[column]):
            shown[column] = shown[column].map(lambda v: None if pd.isna(v) else float(f"{v:.4g}"))

    def as_xlsx():
        buffer = io.BytesIO()
        frame.to_excel(buffer, index=False)
        buffer.seek(0)
        return buffer

    csv = W.FileDownload(callback=lambda: io.BytesIO(frame.to_csv(index=False).encode("utf-8")),
                         filename=f"{name}.csv", label="CSV", button_type="light", width=80)
    xlsx = W.FileDownload(callback=as_xlsx, filename=f"{name}.xlsx", label="Excel",
                          button_type="light", width=80)
    grid = W.Tabulator(shown, show_index=False, disabled=True, layout="fit_data_table",
                       sizing_mode="stretch_width", height=height,
                       pagination="local" if len(shown) > 50 else None, page_size=50)
    return pn.Column(pn.Row(csv, xlsx), grid, sizing_mode="stretch_width")


def _details(title: str, sentence: str, frame: pd.DataFrame, name: str):
    """A heading, a sentence, and the table behind it on request (as in version 1)."""
    body = pn.Column(_table(frame, name), visible=False, sizing_mode="stretch_width")
    button = W.Button(name="Show details", button_type="light", width=120,
                      styles={"border": "2px solid #4099da", "border-radius": "4px"})

    def toggle(event):
        body.visible = not body.visible
        button.name = "Hide details" if body.visible else "Show details"

    button.on_click(toggle)
    return pn.Column(_md(f"#### {title}"), _md(sentence), button, body,
                     sizing_mode="stretch_width")


def _join(contributors) -> str:
    parts = [f"{name} ({share}%)" for name, share in contributors]
    if len(parts) <= 1:
        return "".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


class Report:
    """Builds the report for one results file."""

    def __init__(self, data: ReportData):
        self.d = data

    # --------------------------------------------------------- selectors

    def impact(self, name="Impact category"):
        return W.Select(name=name, options=self.d.impact_options(), value=SINGLE_SCORE,
                        width=290)

    def market(self, name="Market"):
        return W.Select(name=name, options=self.d.markets, width=170)

    def setting(self, name="Scenario setting"):
        return W.Select(name=name, options=self.d.settings, value="average", width=170)

    def markets_box(self):
        return W.CheckBoxGroup(name="Markets", options=self.d.markets, value=self.d.markets,
                               inline=True)

    def element(self, name="Element", design=BASE_DESIGN):
        d = self.d
        options = {}
        for node_id in d.elements(design):
            options[("  " * d.depth(node_id)) + d.labels[node_id]] = node_id
        return W.Select(name=name, options=options, value=d.root_id, width=330)

    def unit_note(self, impact):
        return pn.bind(lambda key: _md(f"Unit: **{self.d.unit(key)}** per product",
                                       margin=(25, 10, 0, 10)), impact)

    def level_name(self, level: int) -> str:
        """'level 2 (assembly)' when the elements at that depth share a level label."""
        d = self.d
        labels = [d.nodes.loc[n, "level_label"] for n in d.elements() if d.depth(n) == level]
        named = {lab for lab in labels if isinstance(lab, str) and lab}
        shared = len(named) == 1 and all(isinstance(lab, str) and lab for lab in labels)
        return f"level {level}" + (f" ({named.pop()})" if shared else "")

    # ============================================================ tabs

    def build(self):
        d = self.d
        tabs = [("Quick summary", self.quick_summary()),
                ("LCA summary", self.lca_summary()),
                ("Reference product", self.reference_product())]
        if d.toggles.get("alternatives") and d.alternatives():
            tabs.append(("Design changes", self.design_changes()))
        if d.toggles.get("ghg_protocol") or d.toggles.get("en15804"):
            tabs.append(("GHG Protocol & EN 15804", self.classifications()))
        tabs.append(("About this report", self.about()))
        return pn.Tabs(*tabs, dynamic=True, sizing_mode="stretch_width")

    # ----------------------------------------------------- quick summary

    def quick_summary(self):
        d = self.d
        impact, market, setting = self.impact(), self.market(), self.setting()

        def view(key, market, setting):
            rows = d.rows(setting=setting, market=market)
            unit = d.unit(key)
            total = d.total(rows, key)
            sections = [_md(f"**{d.label_of(key)} of one product in {market}, {setting} case: "
                            f"{_fmt(total)} {unit}.**")]
            for note in d.data_notes(rows, key):
                sections.append(pn.pane.Alert(note, alert_type="info", margin=(2, 10)))
            for level in range(1, d.levels() + 1):
                series = rows.groupby(d.at_level(rows, level))[key].sum()
                contributors, table = d.top90(series, "Element")
                name = self.level_name(level)
                sentence = (f"**Over 90% of the impact** is caused by: {_join(contributors)}."
                            if contributors else "No positive impact at this level.")
                sections.append(_details(f"Most relevant elements – {name}", sentence, table,
                                         f"most_relevant_{name.replace(' ', '_')}"))
            contributors, table = d.top90(rows.groupby("stage")[key].sum(), "Stage")
            sections.append(_details("Most relevant life-cycle stages",
                                     f"**Over 90% of the impact** is caused in: "
                                     f"{_join(contributors)}.", table, "most_relevant_stages"))
            if d.alternatives():
                summary = d.design_summary(key, setting, market).iloc[1:]
                if d.toggles.get("cost") and summary["Cost"].notna().all():
                    summary = summary.sort_values("Cost per unit of reduction")
                    lines = [f"- {r['Design']}: {_fmt(r['Cost per unit of reduction'])} "
                             f"{d.currency} per {unit} less (impact "
                             f"{-r['Impact reduction (%)']:+.1f} %, cost "
                             f"{r['Cost change']:+.4g} {d.currency})"
                             for _, r in summary.iterrows()]
                    title = "Most cost-effective design changes"
                    sentence = ("Cost per unit of impact reduction. A negative value means the "
                                "change saves money while reducing impact, or costs more while "
                                "adding impact – check the signs in brackets.\n\n"
                                + "\n".join(lines))
                else:
                    summary = summary.sort_values("Impact reduction", ascending=False)
                    lines = [f"- {r['Design']}: impact {-r['Impact reduction (%)']:+.1f} %"
                             for _, r in summary.iterrows()]
                    title = "Design changes with the largest impact reduction"
                    sentence = "\n".join(lines)
                sections.append(_details(title, sentence, summary, "design_changes"))
            return pn.Column(*sections, sizing_mode="stretch_width")

        return pn.Column(
            _md("## Quick summary\nThe key results at a glance. Choose the market, scenario "
                "setting and impact category; open the details for the numbers behind each "
                "sentence."),
            pn.Row(market, setting, impact, self.unit_note(impact)),
            pn.bind(view, impact, market, setting), sizing_mode="stretch_width")

    # ------------------------------------------------------- LCA summary

    def lca_summary(self):
        d = self.d
        sections = [("Introduction", _md(
            "## LCA summary\nA consolidated view of the results across the whole product, all "
            "markets and scenario settings. Use it to find the parts of the product worth "
            "a closer look.\n\n"
            "- **Flow of impacts:** how impacts add up from the elements to the product\n"
            "- **Most relevant elements:** ranked bars per market and scenario setting\n"
            "- **Breakdown:** sunburst of the whole tree"
            + (", coloured by data uncertainty" if d.toggles.get("uncertainty") else "") + "\n"
            "- **Tables:** results grouped in different ways, to download\n"
            + ("- **Design summary:** impact and cost of every design change\n"
               if d.alternatives() else ""))),
            ("Flow of impacts", self.flow()),
            ("Most relevant elements", self.ranked_elements()),
            ("Uncertainty distribution" if d.toggles.get("uncertainty") else "Breakdown",
             self.breakdown()),
            ("Tables", self.tables())]
        if d.alternatives():
            sections.append(("Design summary", self.design_summary()))
        return pn.Tabs(*sections, dynamic=True, sizing_mode="stretch_width")

    def flow(self):
        d = self.d
        impact, market, setting = self.impact(), self.market(), self.setting()
        depth = W.IntSlider(name="Levels shown", start=1, end=max(1, d.levels() + 1),
                            value=max(1, d.levels() + 1), width=220)

        def view(key, market, setting, depth):
            rows = d.rows(setting=setting, market=market)
            return _plot(charts.sankey(d, rows, key, depth,
                                       f"{d.label_of(key)} ({d.unit(key)}) – {market}, "
                                       f"{setting} case"))

        return pn.Column(
            _md("### Flow of impacts\nFrom the elements up to the product. Each element's own "
                "processes (e.g. assembly) are a separate flow; credits flow the other way."),
            pn.Row(market, setting, impact, depth), pn.bind(view, impact, market, setting, depth),
            sizing_mode="stretch_width")

    def ranked_elements(self):
        d = self.d
        impact = self.impact()
        level = W.Select(name="Bars", options={self.level_name(lv): lv
                                               for lv in range(1, max(2, d.levels() + 1))},
                         width=220)

        def view(key, level):
            sections = []
            unit = d.unit(key)
            for market in d.markets:
                charts_row = []
                for setting in [s for s in ("best", "average", "worst") if s in d.settings]:
                    rows = d.rows(setting=setting, market=market).copy()
                    rows["bar"] = d.at_level(rows, level)
                    rows["stack"] = d.at_level(rows, level + 1)
                    charts_row.append(_plot(charts.stacked_bars(
                        rows, "bar", "stack", key,
                        f"{setting.capitalize()} case – total {_fmt(d.total(rows, key))} {unit}",
                        f"{d.label_of(key)} ({unit})", height=430)))
                sections += [_md(f"#### Market: {market}"),
                             pn.Row(*charts_row, sizing_mode="stretch_width")]
            return pn.Column(*sections, sizing_mode="stretch_width")

        return pn.Column(
            _md("### Most relevant elements\nOne bar per element at the chosen level, built up "
                "from the elements one level below."),
            pn.Row(impact, level, self.unit_note(impact)), pn.bind(view, impact, level),
            sizing_mode="stretch_width")

    def breakdown(self, element=None):
        d = self.d
        impact, market, setting = self.impact(), self.market(), self.setting()
        coloured = bool(d.toggles.get("uncertainty"))

        def view(key, market, setting, top):
            rows = d.rows(setting=setting, market=market)
            frame = d.sunburst(rows, key, top=top)
            fig = charts.sunburst(frame, f"{d.labels[top]}: {d.label_of(key)} – {market}, "
                                         f"{setting} case", coloured)
            parts = [_plot(fig)]
            if frame.attrs.get("credits"):
                parts.insert(0, pn.pane.Alert(
                    f"Credits of {_fmt(frame.attrs['credits'])} {d.unit(key)} cannot be drawn "
                    "in a sunburst and are not shown.", alert_type="info"))
            if coloured:
                mean, unscored = d.uncertainty(d.subtree(rows, top), key)
                parts.insert(0, _md(f"Impact-weighted uncertainty score: **{_fmt(mean, 3)}** "
                                    "(1 = best, 5 = worst)"
                                    + (f"; {unscored:.0%} of the impact has no score (grey)."
                                       if unscored > 0.005 else ".")))
            return pn.Column(*parts, sizing_mode="stretch_width")

        top = element if element is not None else W.Select(options={"": d.root_id},
                                                           value=d.root_id, visible=False)
        intro = ("Each ring is one level of the tree; segment size is the share of the impact"
                 + (", colour the data uncertainty (green = reliable, red = uncertain)."
                    if coloured else "."))
        return pn.Column(_md(f"### Breakdown\n{intro} Click a segment to zoom in."),
                         pn.Row(market, setting, impact),
                         pn.bind(view, impact, market, setting, top),
                         sizing_mode="stretch_width")

    def tables(self):
        d = self.d
        settings = W.CheckBoxGroup(name="Scenario settings", options=d.settings,
                                   value=d.settings, inline=True)
        markets = self.markets_box()
        sections = []

        def section(title, description, controls, make):
            def view(settings_value, markets_value, *values):
                rows = d.rows(setting=settings_value, market=markets_value)
                frame = make(rows, *values)
                return _table(frame, title.lower().replace(" ", "_"))
            body = pn.Column(*controls, pn.bind(view, settings, markets, *controls),
                             visible=False, sizing_mode="stretch_width")
            button = W.Button(name="Show section", button_type="primary", width=140)

            def toggle(event):
                body.visible = not body.visible
                button.name = "Hide section" if body.visible else "Show section"

            button.on_click(toggle)
            sections.extend([_md(f"#### {title}\n{description}"), button, body])

        def grouped(rows, by, key, label):
            frame = rows.groupby(["setting", "market", by])[key].sum().reset_index()
            frame.columns = ["Scenario setting", "Market", label, "Impact"]
            frame["Unit"] = d.unit(key)
            return frame

        level_options = {self.level_name(lv): lv for lv in range(0, d.levels() + 1)}
        impact1, level1 = self.impact(), W.Select(name="Level", options=level_options,
                                                  value=1 if d.levels() else 0, width=220)
        section("Impact by element", "Total impact per element at a chosen level of the tree.",
                [impact1, level1],
                lambda rows, key, level: grouped(rows.assign(element=d.at_level(rows, level)),
                                                 "element", key, "Element"))
        impact2, element2 = self.impact(), self.element()
        section("Impact by life-cycle stage", "For the whole product or one element.",
                [impact2, element2],
                lambda rows, key, node: grouped(d.subtree(rows, node), "stage", key, "Stage"))
        impact3, element3 = self.impact(), self.element()
        section("Impact by dataset", "Which database datasets the impact comes from.",
                [impact3, element3],
                lambda rows, key, node: grouped(d.subtree(rows, node), "dataset", key, "Dataset"))
        element4 = self.element()

        def categories(rows, node):
            rows = d.subtree(rows, node)
            frame = rows.groupby(["setting", "market"])[list(ef31.CATEGORY_IDS)].sum()\
                .reset_index().melt(id_vars=["setting", "market"], var_name="category",
                                    value_name="Impact")
            frame["Unit"] = frame["category"].map(d.unit)
            frame["category"] = frame["category"].map(d.label_of)
            frame.columns = ["Scenario setting", "Market", "Impact category", "Impact", "Unit"]
            return frame

        section("Impact by impact category", "All 16 EF 3.1 categories.", [element4], categories)
        if d.toggles.get("cost"):
            impact5, level5 = self.impact(), W.Select(name="Level", options=level_options,
                                                      value=1 if d.levels() else 0, width=220)

            def with_cost(rows, key, level):
                frame = rows.assign(element=d.at_level(rows, level))
                frame = frame.groupby(["setting", "market", "element"])[key].sum().reset_index()
                frame.columns = ["Scenario setting", "Market", "Element", "Impact"]
                frame["Unit"] = d.unit(key)
                return frame

            section("Impact by element (with cost)", "For comparing cost and impact.",
                    [impact5, level5], with_cost)
        return pn.Column(
            _md("### Tables\nChoose the scenario settings and markets for all tables, then open "
                "a section. Every table can be downloaded."),
            pn.Row(settings, markets), *sections, sizing_mode="stretch_width")

    def design_summary(self):
        d = self.d
        impact, market, setting = self.impact(), self.market(), self.setting()
        with_cost = bool(d.toggles.get("cost"))

        def view(key, market, setting):
            summary = d.design_summary(key, setting, market)
            parts = []
            if with_cost and summary["Cost"].notna().all():
                parts.append(_plot(charts.design_scatter(
                    summary, f"Impact and cost per design change – {market}, {setting} case",
                    d.label_of(key))))
                parts.append(_md("Design changes in the lower left reduce both cost and "
                                 "impact."))
            else:
                bars = summary.assign(change=-summary["Impact reduction (%)"])
                parts.append(_plot(charts.category_bars(
                    bars.rename(columns={"Design": "Impact category"}), "change",
                    f"Change in {d.label_of(key)} compared with the base design – {market}, "
                    f"{setting} case", "Change (%)")))
            descriptions = pd.DataFrame([{"Design change": a.name,
                                          "Short description": a.short_description or "",
                                          "Description": a.long_description or ""}
                                         for a in d.alternatives()])
            parts += [_md("#### What the design changes are"), _table(descriptions,
                                                                     "design_changes"),
                      _md(f"#### Summary ({d.unit(key)}, cost in {d.currency})"),
                      _table(summary if with_cost else summary.drop(
                          columns=[c for c in summary.columns if "ost" in c]), "design_summary")]
            return pn.Column(*parts, sizing_mode="stretch_width")

        return pn.Column(_md("### Design summary"), pn.Row(market, setting, impact),
                         pn.bind(view, impact, market, setting), sizing_mode="stretch_width")

    # ------------------------------------------------- reference product

    def reference_product(self):
        d = self.d
        element = self.element("Element to analyse")
        intro = _md(
            "## Reference product\nDetailed results for the base design. Choose any element of "
            "the product – the whole product, a module, a single part – and every section below "
            "shows that element. Its parts are its sub-elements, plus its own processes such "
            "as assembly; for an element without sub-elements, its individual entries.")
        sections = [("Most relevant parts", self.parts(element)),
                    ("Life-cycle stages", self.stages(element)),
                    ("Impact categories", self.categories(element)),
                    ("Uncertainty distribution" if d.toggles.get("uncertainty") else "Breakdown",
                     self.breakdown(element))]
        if d.scenarios:
            sections.append(("Most relevant scenarios", self.sensitivity(element)))
        return pn.Column(intro, element, pn.Tabs(*sections, dynamic=True,
                                                 sizing_mode="stretch_width"),
                         sizing_mode="stretch_width")

    def parts(self, element):
        d = self.d
        impact, market, setting = self.impact(), self.market(), self.setting()

        def view(key, market, setting, node):
            unit = d.unit(key)
            rows = d.subtree(d.rows(setting=setting, market=market), node).copy()
            labels, kind = d.parts_of(rows, node)
            rows["part"] = labels
            rows["stage_"] = rows["stage"].fillna("–")
            fig1 = charts.stacked_bars(
                rows, "part", "stage_", key,
                f"{d.labels[node]} – {market}, {setting} case – total "
                f"{_fmt(d.total(rows, key))} {unit}", f"{d.label_of(key)} ({unit})",
                "Sub-elements" if kind == "elements" else "Entries and steps")
            all_rows = d.subtree(d.rows(setting=d.settings, market=d.markets), node).copy()
            all_rows["part"] = d.parts_of(all_rows, node)[0]
            fig2 = charts.grouped_bars(all_rows[all_rows["market"] == market], "part", "setting",
                                       key, f"By scenario setting – {market}",
                                       f"{d.label_of(key)} ({unit})")
            fig3 = charts.grouped_bars(all_rows[all_rows["setting"] == setting], "part",
                                       "market", key, f"By market – {setting} case",
                                       f"{d.label_of(key)} ({unit})")
            series = rows.groupby("part")[key].sum()
            contributors, _ = d.top90(series, "Part")
            parts = [_md(f"Over 90% of the impact of **{d.labels[node]}** comes from: "
                         f"{_join(contributors)}." if contributors else ""), _plot(fig1)]
            if len(d.settings) > 1:
                parts.append(_plot(fig2))
            if len(d.markets) > 1:
                parts.append(_plot(fig3))
            return pn.Column(*parts, sizing_mode="stretch_width")

        return pn.Column(pn.Row(market, setting, impact),
                         pn.bind(view, impact, market, setting, element),
                         sizing_mode="stretch_width")

    def stages(self, element):
        d = self.d
        impact = self.impact()

        def view(key, node):
            rows = d.subtree(d.rows(setting=d.settings, market=d.markets), node)
            unit = d.unit(key)
            fig = charts.grouped_bars(rows, "stage", "market", key,
                                      f"{d.labels[node]}: impact by life-cycle stage and market",
                                      f"{d.label_of(key)} ({unit})", order=d.stages,
                                      facet="setting" if len(d.settings) > 1 else None)
            return _plot(fig)

        return pn.Column(impact, pn.bind(view, impact, element), sizing_mode="stretch_width")

    def categories(self, element):
        d = self.d
        market, setting = self.market(), self.setting()
        show = W.RadioButtonGroup(options=["Weighted (Pt)", "Normalised (person-year eq.)"],
                                  value="Weighted (Pt)")

        def view(market, setting, node, column):
            rows = d.subtree(d.rows(setting=setting, market=market), node)
            table = d.normalised(rows)
            fig = charts.category_bars(table, column, f"{d.labels[node]}: impact categories – "
                                                      f"{market}, {setting} case", column)
            return pn.Column(_plot(fig), _table(table, "impact_categories"),
                             sizing_mode="stretch_width")

        return pn.Column(
            _md("Weighted: each category's contribution to the single score. Normalised: each "
                "category compared with the yearly impact of an average person."),
            pn.Row(market, setting, show), pn.bind(view, market, setting, element, show),
            sizing_mode="stretch_width")

    def sensitivity(self, element):
        d = self.d
        impact, market = self.impact(), self.market()

        def view(key, market, node):
            table = d.tornado(key, market, node)
            fig = charts.tornado(table, f"{d.labels[node]}: change in {d.label_of(key)} when one "
                                        f"scenario is in its best or worst case – {market}")
            assumptions = []
            for scenario in d.meta.get("scenarios", []):
                for parameter in scenario["parameters"]:
                    assumptions.append({
                        "Scenario": scenario["name"], "Parameter": parameter["name"],
                        "Best (×)": parameter["best"], "Worst (×)": parameter["worst"],
                        "Best case": parameter["assumption_best"] or "",
                        "Average case": parameter["assumption_average"] or "",
                        "Worst case": parameter["assumption_worst"] or ""})
            return pn.Column(_plot(fig), _md("#### Assumptions"),
                             _table(pd.DataFrame(assumptions), "scenario_assumptions"),
                             sizing_mode="stretch_width")

        return pn.Column(
            _md("All other scenarios stay at their average while one is set to its best or worst "
                "case. The longest bars are the assumptions that matter most."),
            pn.Row(market, impact), pn.bind(view, impact, market, element),
            sizing_mode="stretch_width")

    # ---------------------------------------------------- design changes

    def design_changes(self):
        d = self.d
        alternatives = {a.name: a for a in d.alternatives()}
        choice = W.Select(name="Design change", options=list(alternatives), width=330)
        impact, market, setting = self.impact(), self.market(), self.setting()

        def header(name):
            alternative = alternatives[name]
            base = d.labels[alternative.base_id]
            text = (f"**{name}** replaces **{base}**"
                    + (" by removing it." if alternative.removed else ".")
                    + (f" {alternative.short_description}." if alternative.short_description
                       else "")
                    + (f"\n\n{alternative.long_description}" if alternative.long_description
                       else ""))
            return _md(text)

        def summary(name, key, market, setting):
            table = d.compare(alternatives[name], key, setting, market)
            if not d.toggles.get("cost"):
                table = table.drop(columns=["Element cost", "Product cost"])
            if not d.toggles.get("uncertainty"):
                table = table.drop(columns=["Uncertainty"])
            product = table["Product change (%)"].iloc[1]
            text = (f"The product's {d.label_of(key).lower()} changes by **{product:+.2f} %** "
                    f"({market}, {setting} case).")
            return pn.Column(_md(text), _table(table, "design_change_summary"),
                             sizing_mode="stretch_width")

        def stacks(name, key, market):
            alternative = alternatives[name]
            parts = []
            for setting in [s for s in ("best", "average", "worst") if s in d.settings]:
                frames = []
                for label, design, node in (("Base", BASE_DESIGN, alternative.base_id),
                                            (name, name, alternative.alternative_id)):
                    rows = d.rows(design, setting, market)
                    if node == alternative.alternative_id and alternative.removed:
                        continue
                    rows = d.subtree(rows, node).copy()
                    if rows.empty:
                        continue
                    labels, _ = d.parts_of(rows, node)
                    rows["version"] = label
                    rows["part"] = labels.str.replace(r" \[.*\]", "", regex=True)
                    frames.append(rows)
                if not frames:
                    continue
                rows = pd.concat(frames)
                parts.append(_plot(charts.stacked_bars(
                    rows, "version", "part", key, f"{setting.capitalize()} case – {market}",
                    f"{d.label_of(key)} ({d.unit(key)})", order=["Base", name], height=430)))
            return pn.Row(*parts, sizing_mode="stretch_width")

        def stage_bars(name, key, market, setting):
            alternative = alternatives[name]
            base = d.subtree(d.rows(BASE_DESIGN, setting, market), alternative.base_id)
            frames = [base.assign(version="Base")]
            if not alternative.removed:
                frames.append(d.subtree(d.rows(name, setting, market),
                                        alternative.alternative_id).assign(version=name))
            return _plot(charts.grouped_bars(pd.concat(frames), "stage", "version", key,
                                             f"By life-cycle stage – {market}, {setting} case",
                                             f"{d.label_of(key)} ({d.unit(key)})",
                                             order=d.stages))

        def radar(name, market, setting):
            records = []
            base_totals = d.rows(BASE_DESIGN, setting, market)[list(ef31.CATEGORY_IDS)].sum()
            alt_totals = d.rows(name, setting, market)[list(ef31.CATEGORY_IDS)].sum()
            for label, totals in (("Base design", base_totals), (name, alt_totals)):
                record = {"Version": label}
                for category in ef31.CATEGORIES:
                    base = base_totals[category.id]
                    record[category.name] = totals[category.id] / base * 100 if base else 100.0
                records.append(record)
            return _plot(charts.radar(pd.DataFrame(records),
                                      f"Whole product, all categories as % of the base design – "
                                      f"{market}, {setting} case"))

        def sunbursts(name, key, market, setting):
            alternative = alternatives[name]
            coloured = bool(d.toggles.get("uncertainty"))
            parts = []
            for label, design, node in (("Base", BASE_DESIGN, alternative.base_id),
                                        (name, name, alternative.alternative_id)):
                if node == alternative.alternative_id and alternative.removed:
                    parts.append(_md(f"**{name}** removes the element."))
                    continue
                frame = d.sunburst(d.rows(design, setting, market), key, top=node)
                parts.append(_plot(charts.sunburst(frame, f"{label}: {d.label_of(key)}",
                                                   coloured, height=560)))
            return pn.Row(*parts, sizing_mode="stretch_width")

        tabs = pn.Tabs(
            ("Summary", pn.bind(summary, choice, impact, market, setting)),
            ("Compared by part", pn.bind(stacks, choice, impact, market)),
            ("Life-cycle stages", pn.bind(stage_bars, choice, impact, market, setting)),
            ("All impact categories", pn.bind(radar, choice, market, setting)),
            ("Breakdown", pn.bind(sunbursts, choice, impact, market, setting)),
            dynamic=True, sizing_mode="stretch_width")
        return pn.Column(
            _md("## Design changes\nEach design change compared with the element it replaces, "
                "with the rest of the product unchanged."),
            pn.Row(choice, market, setting, impact), pn.bind(header, choice), tabs,
            sizing_mode="stretch_width")

    # --------------------------------------------------- classifications

    def classifications(self):
        d = self.d
        market, setting = self.market(), self.setting()
        design = W.Select(name="Design", options=[BASE_DESIGN] + [a.name for a in
                                                                 d.alternatives()], width=260)

        def view(design, market, setting):
            rows = d.rows(design, setting, market)
            parts = []
            if d.toggles.get("ghg_protocol"):
                table = d.ghg(rows)
                parts += [_md("### GHG Protocol categories\nClimate change (EF 3.1, kg CO2 eq) "
                              "by scope category. 'Unclassified' is the part of the result whose "
                              "entries have no category yet."),
                          _plot(charts.category_bars(
                              table.rename(columns={"Category": "Impact category"}),
                              "Climate change (kg CO2 eq)", f"{market}, {setting} case",
                              "kg CO2 eq")),
                          _table(table, "ghg_protocol")]
            if d.toggles.get("en15804"):
                parts += [_md("### EN 15804 modules\nAll 16 categories by module. 'Unclassified' "
                              "is the part of the result whose entries have no module yet."),
                          _table(d.en15804(rows), "en15804_modules")]
            parts.append(pn.pane.Alert(
                "These breakdowns show how the results fall into the GHG Protocol and EN 15804 "
                "structures. They are not a GHG inventory or an EPD in themselves: those have "
                "further requirements on scope, data and verification.", alert_type="info"))
            return pn.Column(*parts, sizing_mode="stretch_width")

        return pn.Column(pn.Row(design, market, setting), pn.bind(view, design, market, setting),
                         sizing_mode="stretch_width")

    # ------------------------------------------------------------ about

    def about(self):
        d = self.d
        meta = d.meta
        settings = meta.get("settings", {})
        lines = [f"## {meta.get('project', 'Project')}"]
        for key, title in (("functional_unit", "Functional unit"),
                           ("reference_flow", "Reference flow"), ("scope", "Scope")):
            if settings.get(key):
                lines.append(f"**{title}:** {settings[key]}")
        lines.append("**Markets:** " + ", ".join(d.markets))
        lines.append("**Life-cycle stages:** " + ", ".join(s["name"] for s in meta.get("stages",
                                                                                      [])))
        lines.append("**Impact assessment method:** Environmental Footprint (EF) 3.1, 16 "
                     "categories; single score with the EF 3.1 normalisation and weighting "
                     "factors.")
        databases = []
        for database in meta.get("databases", []):
            coverage = database.get("coverage") or {}
            note = []
            if coverage.get("derived"):
                note.append("values calculated back from weighted scores")
            if coverage.get("missing_categories"):
                note.append("does not cover " + ", ".join(coverage["missing_categories"]))
            if coverage.get("partial_categories"):
                note.append("partly covers " + ", ".join(coverage["partial_categories"]))
            databases.append({"Database": database["name"],
                              "Version": database.get("version") or "",
                              "Contents": "elementary flows" if database["kind"] == "flow"
                              else "datasets", "Notes": "; ".join(note)})
        parts = [_md("\n\n".join(lines)), _md("### Databases"),
                 _table(pd.DataFrame(databases), "databases")]
        if meta.get("scenarios"):
            rows = [{"Scenario": s["name"], "Description": s["description"] or "",
                     "Parameter": p["name"], "Best (×)": p["best"], "Worst (×)": p["worst"],
                     "Best case": p["assumption_best"] or "",
                     "Average case": p["assumption_average"] or "",
                     "Worst case": p["assumption_worst"] or ""}
                    for s in meta["scenarios"] for p in s["parameters"]]
            parts += [_md("### Scenarios\nThroughout the report one of three scenario settings "
                          "can be chosen: **best case** (lowest-impact assumptions), **average** "
                          "(the values as entered) and **worst case** (highest-impact "
                          "assumptions)."), _table(pd.DataFrame(rows), "scenarios")]
        exclusions = d.results.exclusions
        parts += [_md("### Knowingly left out"),
                  _table(exclusions.drop(columns=["node_id"]), "exclusions")
                  if not exclusions.empty else _md("Nothing was recorded as left out.")]
        guides = pn.Tabs(
            ("Glossary", _md((TEXTS / "glossary.md").read_text(encoding="utf-8"))),
            ("How to read the charts", _md((TEXTS / "visualizations.md")
                                           .read_text(encoding="utf-8"))),
            dynamic=True, sizing_mode="stretch_width")
        return pn.Tabs(("Input data", pn.Column(*parts, sizing_mode="stretch_width")),
                       ("Guides", guides), dynamic=True, sizing_mode="stretch_width")


def build_report(results) -> pn.viewable.Viewable:
    return Report(ReportData(results)).build()
