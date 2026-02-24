import panel as pn
import holoviews as hv
import pandas as pd
from pathlib import Path

pn.config.raw_css.append("""
.link-btn .bk-btn {
  background: none !important;
  border: none     !important;
  padding: 0       !important;
  margin: 0        !important;
  color: #007bff   !important;
  text-decoration: underline;
  cursor: pointer;
  font-size: 20px;
}
""")

# 1) Load Panel & HoloViews
pn.extension("bokeh", "plotly", "tabulator")
hv.extension("bokeh")

# =====================================================================
# Dashboard runner
# =====================================================================

def run_dashboard(data_dir: Path):
    """
    Launch the LCA Panel dashboard using results from the given data_dir.
    Example: data_dir = Path("processed_data/scooter")
    """

    # Ensure folder exists
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Processed data folder not found: {data_dir}")

    # Example: Load results from processed_data/product_name/
    # (You can pass these into your tabs as needed)
    try:
        results_by_scenario = pd.read_csv(data_dir / "all_results_by_scenario.csv")
        results_by_parameter = pd.read_csv(data_dir / "all_results_by_parameter_base_design.csv")
    except Exception as e:
        print(f"⚠️ Warning: Could not load results from {data_dir}: {e}")
        results_by_scenario, results_by_parameter = None, None

    # 2) Import tabs (adapt these to accept data_dir or datasets if needed)
    from impact_report_generation.src.tabs.executive_summary.generate_executive_summary import build_tab as exec_summary_tab
    from impact_report_generation.src.tabs.summary import build_tab as summary_tab
    from impact_report_generation.src.tabs.reference_product import build_tab as reference_product_tab
    from impact_report_generation.src.tabs.design_changes import build_tab as design_changes_tab
    # Pass data_dir to each tab if your build_tab() accepts it
    tabs = pn.Tabs(
        ("Quick summary",               exec_summary_tab()),
        ("LCA summary",                 summary_tab()),
        ("Reference product section",       reference_product_tab()),
        ("Design change section",   design_changes_tab()),
        dynamic=True
    )


    # 3) Import modal‐card factories
    from impact_report_generation.src.utils.context import (
        scenario_guide_card,
        navigation_card,
        visualization_guide_card,
        input_data_card,
        glossary_card,
    )

    # Instantiate modal cards
    guide_card  = scenario_guide_card()
    nav_card    = navigation_card()
    viz_card    = visualization_guide_card()
    input_card  = input_data_card()
    glossary    = glossary_card()

    # Modal container
    modal_container = pn.Column(sizing_mode="stretch_width")

    # Template
    from panel.template import FastListTemplate
    template = FastListTemplate(
        title="LCA Dashboard",
        accent_base_color="#4099da",
        header_background="#4099da",
        header=[],
        main=[tabs],
        modal=[modal_container],
        main_layout="card"
    )

    # === Modal Callbacks ===
    def show_modal(card):
        modal_container.clear()
        modal_container.append(card)
        template.open_modal()

    def show_navigation(event=None):
        modal_container.clear()

        # mapping from label → tab index
        nav_map = {
            "Executive Summary":                0,
            "LCA summary":     1,
            "Reference product section":              2,
            "Design change section":            3,
        }

        def make_link(label, idx):
            btn = pn.widgets.Button(
                name=label,
                button_type="default",
                css_classes=["link-btn"],
                align="start"
            )
            btn.on_click(lambda ev, i=idx: (setattr(tabs, "active", i), template.close_modal()))
            return btn

        # Sentences mapping
        sentences = [
            ("a high-level snapshot",   "Executive Summary"),
            ("to spot the biggest hotspots", "LCA summary"),
            ("to analyze the reference product in detail", "Reference product section"),
            ("to see design variants in detail",   "Design change section"),
        ]

        lines = []
        for prompt, label in sentences:
            idx = nav_map[label]
            row = pn.Row(
                pn.pane.Markdown(f"If you need {prompt}, click ", margin=(0,0,0,0)),
                make_link(label, idx),
                pn.pane.Markdown(".", margin=(0,0,0,0)),
                sizing_mode="stretch_width"
            )
            lines.append(row)

        nav_card = pn.Card(
            pn.Column(
                pn.pane.Markdown("**What kind of information are you looking for?**\n", margin=(0,0,10,0)),
                *lines,
                sizing_mode="stretch_width"
            ),
            title="🔍 Navigate Report",
            collapsible=False,
            sizing_mode="stretch_width"
        )

        modal_container.append(nav_card)
        template.open_modal()

    # === Buttons ===
    open_guide_btn = pn.widgets.Button(name="ℹ️ Scenario & country variance - explained", button_type="primary")
    open_guide_btn.on_click(lambda ev: show_modal(guide_card))

    open_nav_btn = pn.widgets.Button(name="🔍 How to navigate this report", button_type="primary")
    open_nav_btn.on_click(show_navigation)

    open_viz_btn = pn.widgets.Button(name="🔧 Visualizations - explained", button_type="primary")
    open_viz_btn.on_click(lambda ev: show_modal(viz_card))

    open_input_btn = pn.widgets.Button(name="ℹ️ Input data - explained", button_type="primary")
    open_input_btn.on_click(lambda ev: show_modal(input_card))

    open_glossary_btn = pn.widgets.Button(name="📚 LCA Glossary", button_type="primary")
    open_glossary_btn.on_click(lambda ev: show_modal(glossary))

    # Stick buttons into the header
    template.header[:] = [open_nav_btn, open_guide_btn, open_viz_btn, open_input_btn, open_glossary_btn]

    # Serve dashboard
    template.servable()
    pn.serve(template, port=5006, show=False)

