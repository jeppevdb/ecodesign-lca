"""Every tab, chart and table of the report is built without errors.

The report's charts are evaluated lazily; the walk below calls every bound
function with the selectors at their defaults, and again for other choices.
"""

import pytest

pn = pytest.importorskip("panel")
pytest.importorskip("plotly")

from lca4pd.calculation import calculate              # noqa: E402
from lca4pd.model.classifications import TOGGLES       # noqa: E402
from lca4pd.report.data import ReportData              # noqa: E402
from lca4pd.report.views import Report                 # noqa: E402

from test_calculation import model  # noqa: E402,F401  (fixture)


def walk(obj, seen=None, found=None):
    """Evaluate every lazily bound view inside a layout; return all panes found."""
    seen = set() if seen is None else seen
    found = [] if found is None else found
    if id(obj) in seen:
        return found
    seen.add(id(obj))
    found.append(obj)
    if isinstance(obj, pn.param.ParamFunction):
        walk(obj.object(), seen, found)
    for child in getattr(obj, "objects", []) or []:
        walk(child, seen, found)
    return found


@pytest.fixture
def full(model):  # noqa: F811
    """The lamp with every option on: scenarios, alternatives, cost, classifications."""
    p = model.p
    for toggle in TOGGLES:
        p.set_toggle(toggle, True)
    for node, price in {model.lamp: 30, model.housing: 10, model.base: 4, model.shade: 2,
                        model.led: 20, model.chip: 20}.items():
        p.update_node(node, price=price)
    hours = p.add_parameter(p.add_scenario("Use intensity"), "hours", best=0.5, worst=1.5,
                            assumption_best="2 h a day")
    p.link_parameter(hours, "entry", model.use)
    alt = p.create_alternative(model.base, "Lighter base", short_description="less steel")
    p.update_node(alt, weight=0.6, price=5)
    p.create_alternative(model.shade, "No shade", removed=True)
    p.create_alternative(model.lamp, "Whole new lamp")
    p.update_entry(model.use, ghg_category="3.11", en15804_module="B6", ped_reliability=2,
                   ped_completeness=2, ped_temporal=2, ped_geographical=2, ped_technological=2)
    p.add_entry(model.base, "production_waste", dataset_ref_id=model.recycling, amount=-0.05,
                confirm_negative=True, description="Offcut credit")
    model.report = Report(ReportData(calculate(p, model.library)))
    return model


def assert_no_failures(panes):
    texts = [str(getattr(p, "object", "")) for p in panes if isinstance(p, pn.pane.Markdown)]
    assert not any("could not be" in t for t in texts)


def test_every_tab_builds_and_every_view_renders(full):
    report = full.report.build()
    names = [name for name in report._names]
    assert names == ["Quick summary", "LCA summary", "Reference product", "Design changes",
                     "GHG Protocol & EN 15804", "About this report"]
    panes = walk(report)
    plots = [p for p in panes if isinstance(p, pn.pane.Plotly)]
    assert len(plots) >= 15
    assert_no_failures(panes)


def test_views_render_for_every_choice(full):
    """Each selector set to each of its options in turn."""
    report = full.report.build()
    panes = walk(report)
    selects = [w for w in panes if isinstance(w, pn.widgets.Select)]
    assert selects
    for widget in selects:
        for value in list(widget.values)[:20]:
            widget.value = value
    walk(report)


def test_reference_product_for_every_element(full):
    report = full.report
    element = report.element()
    sections = [report.parts(element), report.stages(element), report.categories(element),
                report.breakdown(element), report.sensitivity(element)]
    for node in element.values:
        element.value = node
        for section in sections:
            walk(section)


def test_quick_summary_names_the_levels(full):
    p = full.p
    p.update_node(full.housing, level_label="assembly")
    p.update_node(full.led, level_label="assembly")
    report = Report(ReportData(calculate(p, full.library)))
    texts = " ".join(str(o.object) for o in walk(report.quick_summary())
                     if isinstance(o, pn.pane.Markdown))
    assert "Most relevant elements – level 1 (assembly)" in texts
    assert "Most relevant elements – level 2" in texts
    p.update_node(full.led, level_label=None)              # no longer shared by all
    report = Report(ReportData(calculate(p, full.library)))
    texts = " ".join(str(o.object) for o in walk(report.quick_summary())
                     if isinstance(o, pn.pane.Markdown))
    assert "level 1 (assembly)" not in texts and "Most relevant elements – level 1" in texts
    assert "Most cost-effective design changes" in texts


def test_sections_follow_the_options(model):  # noqa: F811
    report = Report(ReportData(calculate(model.p, model.library))).build()
    assert list(report._names) == ["Quick summary", "LCA summary", "Reference product",
                                   "About this report"]
    walk(report)


def test_app_report_step(full, tmp_path):
    from lca4pd.app.views import report as report_step
    results = calculate(full.p, full.library)

    class Session:
        project = full.p
        results_path = tmp_path / "lamp.results"

        def goto(self, *args, **kwargs):
            pass

    session = Session()
    view = report_step.build(session)
    assert isinstance(view, pn.Column) and view[0].alert_type == "info"     # nothing yet
    results.save(session.results_path)
    view = report_step.build(session)
    assert isinstance(view[0], pn.Tabs)
    full.p.update_entry(full.base_steel, amount=2)
    view = report_step.build(session)
    assert view[0][0].alert_type == "warning"                               # out of date
