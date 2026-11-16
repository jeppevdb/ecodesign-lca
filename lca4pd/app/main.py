"""Assemble and serve the application.

    python -m lca4pd [--workspace DIR] [--port 5006] [--no-browser]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import panel as pn

from .components import LEFT_STYLE, W
from .session import Session
from .views import calculate, databases, issues, pathways, setup, start, tree

ACCENT = "#4099da"

STEPS = [
    ("setup", "1  Setup"),
    ("databases", "2  Databases"),
    ("pathways", "3  Transport and end-of-life pathways"),
    ("tree", "4  Product and entries"),
    ("calculate", "5  Calculate"),
]
VIEWS = {"start": start.build, "setup": setup.build, "databases": databases.build,
         "pathways": pathways.build, "tree": tree.build, "calculate": calculate.build}

def create_app(workspace):
    pn.extension("tabulator", "filedropper", notifications=True)
    session = Session(workspace)
    session.views = VIEWS

    title = pn.pane.Markdown("", margin=(5, 10))
    nav = pn.Column(sizing_mode="stretch_width")
    close = W.Button(name="Close project", button_type="light", sizing_mode="stretch_width")
    close.on_click(lambda event: session.close_project())
    issue_panel = issues.build(session)
    side = pn.Column(sizing_mode="stretch_width")

    def show_navigation():
        if session.project is None:
            side[:] = [pn.pane.Markdown("Open or create a project to start.")]
            return
        title.object = f"### {session.project.get_setting('name')}"
        buttons = []
        for step, label in STEPS:
            button = W.Button(name=label, sizing_mode="stretch_width", stylesheets=[LEFT_STYLE],
                              button_type="primary" if step == session.step else "default")
            button.on_click(lambda event, step=step: session.goto(step))
            buttons.append(button)
        nav[:] = buttons
        side[:] = [title, nav, pn.layout.Divider(),
                   pn.pane.Markdown("#### What is still missing", margin=(0, 10)),
                   issue_panel, pn.layout.Divider(), close]

    session.on_navigation(show_navigation)
    session.on_change(show_navigation, persistent=True)

    template = pn.template.FastListTemplate(
        title="LCA4PD", accent_base_color=ACCENT, header_background=ACCENT,
        sidebar=[side], main=[session.main], modal=[session.modal],
        sidebar_width=360, main_layout=None,
    )
    session.template = template
    session.goto("start")
    return template


def serve(workspace="workspace", port=5006, show=True):
    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    pn.serve({"/": lambda: create_app(workspace)}, port=port, show=show, title="LCA4PD",
             websocket_max_message_size=200 * 1024 * 1024,
             http_server_kwargs={"max_buffer_size": 200 * 1024 * 1024})


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m lca4pd")
    parser.add_argument("--workspace", default="workspace",
                        help="folder for projects and the database library (default: ./workspace)")
    parser.add_argument("--port", type=int, default=5006)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    serve(args.workspace, args.port, show=not args.no_browser)
