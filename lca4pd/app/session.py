"""State of one browser session: the open project, the library, where the user is."""

from __future__ import annotations

import re
from pathlib import Path

import panel as pn

from ..databases import Library
from ..model import Project, check_project
from ..model.checks import Issue

PROJECT_SUFFIX = ".lca4pd"
RESULTS_SUFFIX = ".results"


class Session:
    def __init__(self, workspace):
        self.workspace = Path(workspace)
        self.projects_dir = self.workspace / "projects"
        self.uploads_dir = self.workspace / "uploads"
        for directory in (self.projects_dir, self.uploads_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.library = Library(self.workspace / "library")
        self.project: Project | None = None
        self.project_path: Path | None = None

        self.step = "start"
        self.selected_node: int | None = None
        self.focus: dict = {}                 # what a view should open on arrival
        self.main = pn.Column(sizing_mode="stretch_width")
        self.modal = pn.Column(sizing_mode="stretch_width")
        self.template = None
        self.views: dict = {}                 # step name -> function(session) -> viewable
        self._listeners: list = []            # called after project data changed
        self._navigation_listeners: list = []
        self._issues: list[Issue] | None = None

    # ------------------------------------------------------------- projects

    def project_files(self) -> list[Path]:
        return sorted(self.projects_dir.glob(f"*{PROJECT_SUFFIX}"))

    def new_project(self, name: str) -> None:
        slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_") or "project"
        path = self.projects_dir / f"{slug}{PROJECT_SUFFIX}"
        counter = 2
        while path.exists():
            path = self.projects_dir / f"{slug}_{counter}{PROJECT_SUFFIX}"
            counter += 1
        self._set_project(Project.create(path, name), path)

    def open_project(self, path) -> None:
        self._set_project(Project.open(path), Path(path))

    def _set_project(self, project: Project, path: Path) -> None:
        self.close_project(navigate=False)
        self.project, self.project_path = project, path
        root = project.root()
        self.selected_node = root["id"] if root else None
        self.changed()
        self.goto("setup")

    def close_project(self, navigate: bool = True) -> None:
        if self.project is not None:
            self.project.close()
        self.project = self.project_path = self.selected_node = None
        self._issues = None
        if navigate:
            self.changed()
            self.goto("start")

    @property
    def results_path(self) -> Path | None:
        return self.project_path.with_suffix(RESULTS_SUFFIX) if self.project_path else None

    # --------------------------------------------------------------- change

    def on_change(self, callback, persistent: bool = False) -> None:
        """Call ``callback`` whenever project data changed. Views register on build."""
        self._listeners.append((callback, persistent))

    def on_navigation(self, callback) -> None:
        self._navigation_listeners.append(callback)

    def changed(self) -> None:
        self._issues = None
        for callback, _ in list(self._listeners):
            callback()

    def issues(self) -> list[Issue]:
        if self.project is None:
            return []
        if self._issues is None:
            self._issues = check_project(self.project, self.library)
        return self._issues

    # ----------------------------------------------------------- navigation

    def goto(self, step: str, **focus) -> None:
        if self.project is None:
            step = "start"
        self.step, self.focus = step, focus
        if "node" in focus:
            self.selected_node = focus["node"]
        self._listeners = [(cb, keep) for cb, keep in self._listeners if keep]
        try:
            view = self.views[step](self)
        except Exception as error:      # show the problem instead of a blank page
            view = pn.pane.Alert(f"This screen could not be shown: {error}", alert_type="danger")
        self.main[:] = [view]
        for callback in self._navigation_listeners:
            callback()

    # ---------------------------------------------------------------- modal

    def open_modal(self, content) -> None:
        self.modal[:] = [content]
        self.template.open_modal()

    def close_modal(self) -> None:
        self.template.close_modal()
        self.modal[:] = []

    # --------------------------------------------------------------- notify

    @staticmethod
    def saved(text: str = "Saved") -> None:
        if pn.state.notifications is not None:
            pn.state.notifications.success(text, duration=1500)

    @staticmethod
    def error(text: str) -> None:
        if pn.state.notifications is not None:
            pn.state.notifications.error(text, duration=6000)
