"""Step: the product tree. Select an element on the left, edit it on the right."""

import pandas as pd
import panel as pn

from ...model.diff import diff_alternative
from ...model.tree import Tree
from ..components import (ParameterField, W, alert, answer, card, confirm_button, guarded,
                          heading, note, question, table)
from .entries import entries_panel
from .pathways import new_pathway_form

NBSP = " "
EXCLUDE = "__exclude__"


def node_form(session, node_id=None, parent_id=None, on_done=None):
    """The form for an element, used both to create and to edit it.

    The three questions (where is it produced, end-of-life as a whole,
    use-stage inputs) are only shown where they apply.
    """
    project = session.project
    toggles = project.toggles
    node = project.get_node(node_id) if node_id else {}
    creating = node_id is None
    # The product, and an alternative of the whole product, sit at the top of the tree.
    is_root = (creating and parent_id is None) or (not creating and node["parent_id"] is None)
    if creating:
        if parent_id is None:
            asks = {"production_site": False, "use": project.stage_by_role("use") is not None,
                    "eol": project.stage_by_role("end_of_life") is not None}
        else:
            parent = project.get_node(parent_id)
            above = project.questions_for(parent_id)
            asks = {"production_site": above["production_site"]
                    and parent["production_site"] != "supplier",
                    "eol": above["eol"] and parent["eol_mode"] not in ("whole", "excluded"),
                    "use": above["use"]}
        children, own_weight = [], None
    else:
        asks = project.questions_for(node_id)
        tree = Tree(project)
        children = tree.children(node_id)
        own_weight = tree.own_weight(node_id)
        if is_root:
            asks["production_site"] = False     # the product is made by the user

    messages = pn.Column()
    currency = project.get_setting("currency")

    # ---- basic fields
    name = W.TextInput(name="Name", value=node.get("name", ""), width=320)
    quantity = W.FloatInput(name="Quantity (per one of its parent)",
                            value=node.get("quantity", 1.0), start=0, width=220,
                            visible=not is_root)
    label = W.TextInput(name="Level label (optional)", value=node.get("level_label") or "",
                        placeholder="e.g. assembly, module, part", width=220)
    number = W.TextInput(name="Internal number", value=node.get("internal_number") or "",
                         width=220, visible=toggles["internal_numbers"])
    price = W.FloatInput(name=f"Price ({currency})", value=node.get("price"), start=0, width=220,
                         visible=toggles["cost"])
    weight = W.FloatInput(name="Weight (kg)", value=node.get("weight"), start=0, width=220)
    is_total = W.Checkbox(name="This is the total weight, including all sub-elements",
                          value=bool(node.get("weight_is_total")))
    description = W.TextAreaInput(name="Description (optional)",
                                  value=node.get("description") or "", height=70,
                                  sizing_mode="stretch_width")
    weight_help = ("Weight is used for transport and end-of-life. A weight entered here counts "
                   "on top of the sub-elements' weights, unless ticked as the total.")
    if not creating and children:
        total, missing = tree.total_weight(node_id)
        weight_help += (f" Current weight including sub-elements: **{total:g} kg**."
                        if total is not None else
                        f" The weight including sub-elements is not complete yet "
                        f"({len(missing)} element(s) without weight).")
    weight_parameters = ParameterField(session, "node_weight", node_id, label="Weight affected by")
    price_parameters = ParameterField(session, "node_price", node_id, label="Price affected by")
    basics = [pn.Row(name, quantity), pn.Row(label, number, price),
              pn.Row(weight, pn.Column(pn.Spacer(height=18), is_total)),
              note(weight_help)]
    if weight_parameters.view is not None:
        basics.append(weight_parameters.view)
    if toggles["cost"] and price_parameters.view is not None:
        basics.append(price_parameters.view)
    basics.append(description)

    # ---- pathway selectors
    def pathway_select(kind, current, reason, label_text, allow_exclude=True):
        def choices():
            found = {p["name"]: p["id"] for p in project.list_pathways(kind)}
            if allow_exclude:
                found["— leave out, with a reason —"] = EXCLUDE
            return found

        options = choices()
        value = current if current in options.values() else (EXCLUDE if reason else 0)
        select = W.Select(name=label_text, options={"(choose)": 0, **options}, value=value,
                          width=320)
        why = W.TextInput(name="Reason for leaving it out", value=reason or "", width=360,
                          visible=value == EXCLUDE)
        new = W.Button(name="New pathway…", width=130)

        def created(pathway_id):
            select.options = {"(choose)": 0, **choices()}
            select.value = pathway_id

        new_area = pn.Column(sizing_mode="stretch_width")
        new.on_click(lambda event: new_pathway_form(session, kind, new_area, created))
        select.param.watch(lambda event: setattr(why, "visible", event.new == EXCLUDE), "value")
        view = pn.Column(pn.Row(select, pn.Column(pn.Spacer(height=18), new)), why, new_area,
                         sizing_mode="stretch_width")
        return select, why, view

    questions = []

    # ---- question 1: where is it produced
    site = None
    if asks["production_site"]:
        site = question({"On our own site": "on_site", "At a supplier": "supplier"},
                        node.get("production_site"), inline=True)
        supplier, supplier_reason, supplier_view = pathway_select(
            "supplier", node.get("supplier_pathway_id"), node.get("supplier_exclusion_reason"),
            "Transport from the supplier to us")
        supplier_view.visible = site.value == "supplier"
        site.param.watch(lambda event: setattr(supplier_view, "visible", event.new == "supplier"),
                         "value")
        questions.append(card(
            "Where is this element produced?", site, supplier_view,
            note("For an element from a supplier, only the transport from that supplier to your "
                 "site is modelled, and its sub-elements are not asked this question.")))
    elif not is_root:
        questions.append(note("*Where it is produced* is settled by an element higher up that "
                              "comes from a supplier."))

    # ---- question 2: end-of-life
    eol = None
    if asks["eol"]:
        eol = question({"Yes – one pathway for the whole element": "whole",
                        "No – decide for each sub-element": "split",
                        "Leave end-of-life out, with a reason": "excluded"},
                       node.get("eol_mode"))
        whole, _, whole_view = pathway_select("eol", node.get("eol_pathway_id"), None,
                                              "End-of-life pathway", allow_exclude=False)
        eol_reason = W.TextInput(name="Reason", value=node.get("eol_exclusion_reason") or "",
                                 width=420)
        own, own_reason, own_view = pathway_select(
            "eol", node.get("eol_own_pathway_id"), node.get("eol_own_exclusion_reason"),
            "Pathway for the weight that belongs to no sub-element")
        has_own = bool(children) and own_weight is not None and own_weight > 1e-9
        own_box = pn.Column(own_view)
        if has_own:
            own_box.insert(0, note(
                f"**{own_weight:g} kg** of this element belongs to none of its sub-elements "
                "(e.g. glue or fasteners entered here). It needs its own pathway."))

        def show_eol(*events):
            whole_view.visible = eol.value == "whole"
            eol_reason.visible = eol.value == "excluded"
            own_box.visible = eol.value == "split" and has_own

        eol.param.watch(show_eol, "value")
        show_eol()
        hint = ("If yes, the sub-elements are not asked. If no, each sub-element is asked in turn"
                + ("." if children or creating else
                   " – this element has no sub-elements yet, so it needs a pathway of its own "
                   "or a documented reason."))
        questions.append(card("Does one end-of-life pathway apply to this element as a whole?",
                              eol, whole_view, eol_reason, own_box, note(hint)))
    elif project.stage_by_role("end_of_life") is not None:
        questions.append(note("*End-of-life* is settled by an element higher up."))

    # ---- question 3: use
    use = None
    if asks["use"]:
        use = W.Checkbox(name="This element has use-stage inputs that are directly attributable "
                              "to it (e.g. the electricity it consumes)",
                         value=bool(node.get("has_use_inputs")))
        questions.append(card("Use stage", use))

    # ---- save
    def collect() -> dict:
        fields = {"name": name.value, "level_label": label.value, "description": description.value,
                  "weight": weight.value, "weight_is_total": is_total.value}
        if not is_root:
            fields["quantity"] = quantity.value
        if toggles["internal_numbers"]:
            fields["internal_number"] = number.value
        if toggles["cost"]:
            fields["price"] = price.value
        if site is not None:
            fields["production_site"] = answer(site)
            chosen = (supplier.value or None) if site.value == "supplier" else None
            fields["supplier_pathway_id"] = None if chosen == EXCLUDE else chosen
            fields["supplier_exclusion_reason"] = (supplier_reason.value
                                                   if chosen == EXCLUDE else None)
        if eol is not None:
            fields["eol_mode"] = answer(eol)
            fields["eol_pathway_id"] = (whole.value or None) if eol.value == "whole" else None
            fields["eol_exclusion_reason"] = eol_reason.value if eol.value == "excluded" else None
            chosen = (own.value or None) if eol.value == "split" else None
            fields["eol_own_pathway_id"] = None if chosen == EXCLUDE else chosen
            fields["eol_own_exclusion_reason"] = own_reason.value if chosen == EXCLUDE else None
        if use is not None:
            fields["has_use_inputs"] = use.value
        return fields

    def save(event):
        fields = collect()
        result = {}

        def action():
            if creating:
                result["id"] = project.add_node(parent_id, fields.pop("name"), **fields)
            else:
                project.update_node(node_id, **fields)
                result["id"] = node_id
            weight_parameters.save(result["id"])
            if toggles["cost"]:
                price_parameters.save(result["id"])

        if guarded(session, action, messages):
            session.saved("Element created" if creating else "Saved")
            session.selected_node = result["id"]
            session.changed()
            if on_done:
                on_done(result["id"])

    button = W.Button(name="Create element" if creating else "Save changes",
                      button_type="primary", width=180)
    button.on_click(save)
    buttons = [button]
    if creating and on_done:
        cancel = W.Button(name="Cancel", width=100)
        cancel.on_click(lambda event: on_done(None))
        buttons.append(cancel)
    return pn.Column(*basics, *questions, messages, pn.Row(*buttons), sizing_mode="stretch_width")


def alternative_details(session, alternative_id: int, on_done):
    """Name and descriptions of a design alternative."""
    project = session.project
    node = project.get_node(alternative_id)
    local = pn.Column()
    label = W.TextInput(name="Name of the alternative", value=node["alt_label"] or "", width=360)
    short = W.TextInput(name="Short description", value=node["alt_short_description"] or "",
                        sizing_mode="stretch_width")
    long = W.TextAreaInput(name="Long description", value=node["alt_long_description"] or "",
                           height=110, sizing_mode="stretch_width")
    save = W.Button(name="Save", button_type="primary", width=120)

    def do_save(event):
        if guarded(session, lambda: project.update_node(
                alternative_id, alt_label=label.value, alt_short_description=short.value,
                alt_long_description=long.value), local):
            session.saved()
            session.changed()
            on_done(alternative_id)

    save.on_click(do_save)
    return pn.Column(label, short, long, local, save, sizing_mode="stretch_width")


def new_alternative_form(session, base_id: int, on_done):
    project = session.project
    base = project.get_node(base_id)
    local = pn.Column()
    label = W.TextInput(name="Name of the alternative", width=360,
                        placeholder="e.g. Aluminium housing")
    short = W.TextInput(name="Short description", sizing_mode="stretch_width")
    long = W.TextAreaInput(name="Long description (optional)", height=90,
                           sizing_mode="stretch_width")
    start = W.RadioBoxGroup(options={
        f"A copy of '{base['name']}' as it is now, to change afterwards": "copy",
        "An empty element, to build from scratch": "empty",
        f"Nothing: this redesign removes '{base['name']}'": "removed"}, value="copy")
    create = W.Button(name="Create alternative", button_type="primary", width=180)
    cancel = W.Button(name="Cancel", width=100)

    def do_create(event):
        made = {}

        def action():
            made["id"] = project.create_alternative(
                base_id, label.value_input or label.value, copy=start.value == "copy",
                removed=start.value == "removed", short_description=short.value,
                long_description=long.value)

        if guarded(session, action, local):
            session.changed()
            on_done(made["id"])

    create.on_click(do_create)
    cancel.on_click(lambda event: on_done(None))
    return pn.Column(
        note("An alternative is another version of this element and everything below it. It is "
             "calculated against the base design, with the rest of the product unchanged. Later "
             "changes to the base element are not carried over to the alternative."),
        label, short, long, pn.pane.Markdown("**Start from**", margin=(10, 10, 0, 10)), start,
        local, pn.Row(create, cancel), sizing_mode="stretch_width")


def build(session):
    project = session.project
    with_alternatives = project.toggles["alternatives"]
    collapsed: set[int] = session.__dict__.setdefault("collapsed_nodes", set())
    left = pn.Column(width=420)
    right = pn.Column(sizing_mode="stretch_width")
    state = {"ids": [], "mode": "edit"}

    def statuses():
        """Worst open item per element; blockers also mark the elements above."""
        result: dict[int, str] = {}
        entry_node = {}
        for issue in session.issues():
            node_id = None
            if issue.target_type == "node":
                node_id = issue.target_id
            elif issue.target_type == "entry":
                if issue.target_id not in entry_node:
                    entry_node[issue.target_id] = project.get_entry(issue.target_id)["node_id"]
                node_id = entry_node[issue.target_id]
            if node_id is None:
                continue
            if issue.severity == "blocker":
                result[node_id] = "blocker"
            else:
                result.setdefault(node_id, "warning")
        return result

    def show_tree():
        tree = Tree(project)
        if tree.root_id is None:
            left[:] = [note("The tree is empty.")]
            return
        status = statuses()
        below: set[int] = set()
        for node_id, level in status.items():
            if level != "blocker":
                continue
            # Mark the elements above; inside an alternative, stop at the alternative itself.
            current = tree.nodes[node_id]
            while current["alternative_of"] is None and current["parent_id"] is not None:
                current = tree.nodes[current["parent_id"]]
                below.add(current["id"])
        rows, ids = [], []

        def add(node_id, depth):
            node = tree.nodes[node_id]
            children = [] if node["is_removed"] else tree.children(node_id)
            mark = {"blocker": "⛔", "warning": "⚠️"}.get(status.get(node_id))
            if mark is None:
                mark = "⛔" if node_id in below else "✅"
            elif status.get(node_id) == "warning" and node_id in below:
                mark = "⛔"
            if node["alternative_of"] is not None:
                text = f"⇄ {node['alt_label']}" + (" (removed)" if node["is_removed"] else "")
            else:
                text = node["name"]
            if node["quantity"] != 1 and not node["is_removed"]:
                text = f"{node['quantity']:g} × {text}"
            rows.append({"fold": ("▸" if node_id in collapsed else "▾") if children else "",
                         "Element": NBSP * 4 * depth + text, "Status": mark})
            ids.append(node_id)
            if node_id not in collapsed:
                for child in children:
                    add(child, depth + 1)
            if with_alternatives and node["alternative_of"] is None:
                for alternative in tree.alternatives(node_id):
                    add(alternative, depth)

        add(tree.root_id, 0)
        state["ids"] = ids
        grid = table(pd.DataFrame(rows), selectable=1, widths={"fold": 34, "Status": 70},
                     titles={"fold": " "},
                     height=min(34 * len(rows) + 40, 640))
        if session.selected_node in ids:
            grid.selection = [ids.index(session.selected_node)]

        def clicked(event):
            node_id = ids[event.row]
            if event.column == "fold" and tree.children(node_id):
                collapsed.symmetric_difference_update({node_id})
                show_tree()
                return
            session.selected_node = node_id
            state["mode"] = "edit"
            show_node()

        grid.on_click(clicked)
        legend = "⛔ something is still needed here or below · ⚠️ worth checking · ✅ complete"
        if with_alternatives:
            legend += " · ⇄ design alternative of the element above it"
        left[:] = [grid, note(legend)]

    def refresh(selected=None):
        if selected is not None:
            session.selected_node = selected
        state["mode"] = "edit"
        show_tree()
        show_node()

    def show_node():
        root = project.root()
        if root is None:
            right[:] = [heading("Start with the product itself"),
                        note("The product is the top of the tree. Its parts are added below it, "
                             "in as many levels as the product needs."),
                        node_form(session, on_done=refresh)]
            return
        node_id = session.selected_node
        if node_id is None or node_id not in state["ids"]:
            node_id = session.selected_node = root["id"]
        node = project.get_node(node_id)
        is_alternative = node["alternative_of"] is not None

        if state["mode"] == "add":
            right[:] = [heading(f"New sub-element of '{node['name']}'"),
                        node_form(session, parent_id=node_id,
                                  on_done=lambda new_id: refresh(new_id))]
            return
        if state["mode"] == "alternative":
            right[:] = [heading(f"New design alternative for '{node['name']}'"),
                        new_alternative_form(session, node_id, refresh)]
            return

        path = " › ".join([a["name"] for a in reversed(project.ancestors(node_id))] + [node["name"]])
        title = node["name"]
        if is_alternative:
            base = project.get_node(node["alternative_of"])
            title = f"⇄ {node['alt_label']}"
            path = f"Design alternative of '{base['name']}' ({path})"

        def delete():
            fallback = node["alternative_of"] or node["parent_id"]
            project.delete_node(node_id)
            session.changed()
            refresh(fallback)

        actions, move_row = [], []
        if not node["is_removed"]:
            add = W.Button(name="Add sub-element", button_type="primary", width=160)
            add.on_click(lambda event: (state.update(mode="add"), show_node()))
            actions.append(add)
        if is_alternative:
            actions.append(confirm_button("Delete alternative", delete, width=170))
        elif node["parent_id"] is not None:
            copy = W.Button(name="Copy", width=90)

            def duplicate(event):
                made = {}
                if guarded(session, lambda: made.update(id=project.duplicate_node(node_id))):
                    session.changed()
                    refresh(made["id"])

            copy.on_click(duplicate)
            subtree = set(project._subtree_ids(node_id))
            targets = {}
            for other in state["ids"]:
                candidate = project.get_node(other)
                if other in subtree or other == node["parent_id"] or candidate["is_removed"]:
                    continue
                name = (f"⇄ {candidate['alt_label']}" if candidate["alternative_of"] is not None
                        else candidate["name"])
                targets[f"{name}  (#{other})"] = other
            actions += [copy, confirm_button("Delete", delete, width=170)]
            if targets:
                target = W.Select(options=targets, width=230)
                move = W.Button(name="Move below", width=110)

                def do_move(event):
                    if guarded(session, lambda: project.move_node(node_id, target.value)):
                        session.changed()
                        refresh(node_id)

                move.on_click(do_move)
                move_row = [move, target]
        if with_alternatives and not is_alternative and not project.in_alternative(node_id):
            alternative = W.Button(name="Add design alternative", width=190)
            alternative.on_click(lambda event: (state.update(mode="alternative"), show_node()))
            actions.append(alternative)

        def entries_changed():
            session.focus = {"tab": "entries"}
            show_node()

        tabs = []
        if not node["is_removed"]:
            entries = entries_panel(session, node_id, on_changed=entries_changed)
            count = len(project.list_entries(node_id))
            tabs += [("Element", node_form(session, node_id=node_id, on_done=refresh)),
                     (f"Entries ({count})", entries)]
        if is_alternative:
            lines = diff_alternative(project, node_id)
            differences = (pn.pane.Markdown("\n".join(f"- {line}" for line in lines))
                           if lines else
                           alert("This alternative is identical to the base element so far.",
                                 "warning"))
            tabs += [("About this alternative", alternative_details(session, node_id, refresh)),
                     (f"Differences from the base ({len(lines)})", pn.Column(
                         note("What this alternative changes, compared with the base element "
                              "as it is now."), differences))]
        active = 1 if (session.focus.get("entry") or session.focus.get("tab") == "entries") \
            and not node["is_removed"] else 0
        session.focus = {}
        right[:] = [pn.pane.Markdown(f"### {title}\n{path}", margin=(0, 10)),
                    pn.Row(*actions), pn.Row(*move_row),
                    pn.Tabs(*tabs, active=active, sizing_mode="stretch_width")]

    def on_change():
        show_tree()

    session.on_change(on_change)
    show_tree()
    show_node()
    return pn.Row(left, right, sizing_mode="stretch_width")
