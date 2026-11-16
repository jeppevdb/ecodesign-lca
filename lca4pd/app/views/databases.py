"""Step: databases. Users upload their own impact-factor files; nothing licensed ships with the tool."""

import asyncio
from pathlib import Path

import pandas as pd
import panel as pn

from ...databases import ProtocolMismatch, describe_headings, link, read_file
from ...method import ef31
from ..components import W, alert, card, confirm_button, guarded, heading, note, table

ACCEPTED = (".xlsx", ".xlsm", ".ods")
_KIND = {"process": "Impact factors per dataset", "flow": "Elementary flows (direct emissions)"}


def _report_view(report):
    """What was read from a file: coverage per category and anything noteworthy."""
    coverage = pd.DataFrame([
        {"Impact category": c.name, "Unit": c.unit,
         "Datasets with a value": f"{report['coverage'].get(c.id, 0):.0%}"}
        for c in ef31.CATEGORIES])
    messages = [alert(text, "warning" if level == "warning" else "info")
                for level, text in report["messages"]]
    return pn.Column(*messages, table(coverage, height=250), sizing_mode="stretch_width")


def build(session):
    project, library = session.project, session.library
    content = pn.Column(sizing_mode="stretch_width")
    messages = pn.Column()
    preview = pn.Column(sizing_mode="stretch_width")

    # ------------------------------------------------------------- lists
    def show():
        in_project = project.list_databases()
        used_hashes = {db["file_hash"] for db in in_project}
        rows = []
        for db in in_project:
            stored = library.database(db["file_hash"])

            def remove(db=db):
                if guarded(session, lambda: project.remove_database(db["id"]), messages):
                    show()
                    session.changed()

            header = (f"**{db['name']}** — {_KIND[db['kind']]}"
                      + (f", version {db['version']}" if db["version"] else ""))
            parts = [pn.Row(pn.pane.Markdown(header, margin=(8, 10)),
                            confirm_button("Remove from project", remove, width=190))]
            if stored is None:
                parts.append(alert(
                    "The file of this database is not on this computer. Upload it below to "
                    "calculate; the project itself only stores which datasets are used.",
                    "warning"))
            else:
                parts.append(note(f"{stored['items']:,} entries, read from `{stored['file_name']}`"))
                parts.append(pn.Card(_report_view(stored["report"]), title="What was read",
                                     collapsed=True, sizing_mode="stretch_width"))
                others = {other["name"]: other["file_hash"] for other in library.databases()
                          if other["kind"] == db["kind"] and other["file_hash"] not in used_hashes}
                if others:
                    choice = W.Select(options=others, width=280)
                    button = W.Button(name="Replace with this version", width=200)

                    def replace(event, db=db, choice=choice):
                        report = link.replace(project, library, db["id"], choice.value)
                        lines = [f"{report.unchanged} dataset(s) found unchanged."]
                        for title, names in (("Found under a new identifier", report.relinked),
                                             ("Renamed", report.renamed),
                                             ("Unit changed – marked as missing", report.unit_changed),
                                             ("Not in the new file – marked as missing", report.missing)):
                            if names:
                                lines.append(f"**{title}:** " + "; ".join(names))
                        show()
                        messages[:] = [alert("\n\n".join(lines), "info")]
                        session.changed()

                    button.on_click(replace)
                    parts.append(pn.Row(choice, button))
            rows.append(pn.Column(*parts, styles={"border-bottom": "1px solid #ddd"},
                                  sizing_mode="stretch_width"))
        if not rows:
            rows = [note("No database is used in this project yet.")]

        available = [db for db in library.databases() if db["file_hash"] not in used_hashes]
        library_rows = []
        for db in available:
            def use(event, db=db):
                link.register(project, library, db["file_hash"])
                show()
                session.changed()

            button = W.Button(name="Use in this project", button_type="primary", width=190)
            button.on_click(use)
            library_rows.append(pn.Row(
                pn.pane.Markdown(f"**{db['name']}** — {_KIND[db['kind']]}, {db['items']:,} entries"
                                 + (f", version {db['version']}" if db["version"] else ""),
                                 margin=(8, 10)), button))
        content[:] = [
            card("Databases used in this project", *rows),
            *([card("Already on this computer", note(
                "Imported earlier, for this or another project."), *library_rows)]
              if library_rows else []),
        ]

    # ------------------------------------------------------------ upload
    # No file-type filter in the browser: it goes by the type the operating system
    # reports, which for .xlsx differs between computers. The extension is checked here.
    dropper = W.FileDropper(multiple=False, max_file_size="1000MB", chunk_size=5_000_000,
                            layout="compact", sizing_mode="stretch_width")
    busy = pn.indicators.LoadingSpinner(value=False, size=30, visible=False)
    status = pn.pane.Markdown("", margin=(8, 10))

    async def uploaded(event):
        if not event.new:
            return
        file_name, data = next(iter(event.new.items()))
        if Path(file_name).suffix.lower() not in ACCEPTED:
            preview[:] = [alert(f"**{file_name}** is not an Excel (.xlsx) or OpenDocument "
                                "(.ods) file.")]
            dropper.value = {}
            return
        path = session.uploads_dir / Path(file_name).name
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        preview[:] = []
        messages[:] = []
        busy.visible = busy.value = True
        status.object = f"Reading `{file_name}` … large files can take a minute."
        try:
            parsed = await asyncio.to_thread(read_file, path)
        except ProtocolMismatch as error:
            headings = ""
            if path.suffix.lower() != ".ods":
                headings = describe_headings(path)
            preview[:] = [
                alert(f"**{file_name} was not recognised.** {error}"),
                pn.Card(pn.pane.Markdown(f"```\n{headings}\n```"),
                        title="Headings found in the file (no data)", collapsed=True),
            ]
            return
        except Exception as error:
            preview[:] = [alert(f"**{file_name} could not be read:** {error}")]
            return
        finally:
            busy.visible = busy.value = False
            status.object = ""
            path.unlink(missing_ok=True)
            dropper.value = {}
        show_preview(parsed)

    def show_preview(parsed):
        report = parsed.report
        default = Path(parsed.file_name).stem
        name = W.TextInput(name="Name in the tool", value=default, width=320)
        version = W.TextInput(name="Version", value=report.version or "", width=200)
        add = W.Button(name="Import and use in this project", button_type="primary", width=260)
        discard = W.Button(name="Discard", width=100)
        local = pn.Column()

        def do_import(event):
            def action():
                library.add(parsed, name.value.strip() or default, version.value.strip() or None)
                link.register(project, library, parsed.file_hash)
            if guarded(session, action, local):
                preview[:] = []
                show()
                session.changed()
                session.saved("Database imported")

        add.on_click(do_import)
        discard.on_click(lambda event: preview.clear())
        summary = {"coverage": report.coverage, "messages": report.messages}
        preview[:] = [card(
            f"Check before importing: {parsed.file_name}",
            pn.pane.Markdown(
                f"Recognised as **{report.protocol}** — {_KIND[parsed.kind].lower()}; "
                f"**{report.datasets:,}** entries read"
                + (f" from sheet '{report.sheet}'." if report.sheet else ".")),
            _report_view(summary), local, pn.Row(name, version),
            pn.Row(add, discard))]

    dropper.param.watch(uploaded, "value")
    upload_card = card(
        "Upload a database file",
        note("Upload the Excel file with impact results that you received from the database "
             "provider (ecoinvent, BAFU, IdeMat), or the EF 3.1 file with elementary flows and "
             "characterisation factors (.ods or .xlsx) for direct emissions. The file is read "
             "into a library on this computer and is never copied into the project."),
        dropper, pn.Row(busy, status))

    show()
    return pn.Column(messages, content, upload_card, preview, sizing_mode="stretch_width")
