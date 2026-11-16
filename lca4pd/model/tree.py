"""Read-only, in-memory view of the product tree with weight roll-up."""

from __future__ import annotations

from collections import defaultdict


class Tree:
    def __init__(self, project):
        rows = project._rows("SELECT * FROM node ORDER BY position, id")
        self.nodes: dict[int, dict] = {row["id"]: row for row in rows}
        self._children: dict[int | None, list[int]] = defaultdict(list)
        self._alternatives: dict[int, list[int]] = defaultdict(list)
        self.root_id: int | None = None
        for row in rows:
            if row["alternative_of"] is not None:
                self._alternatives[row["alternative_of"]].append(row["id"])
            elif row["parent_id"] is None:
                self.root_id = row["id"]
            else:
                self._children[row["parent_id"]].append(row["id"])

    def children(self, node_id: int) -> list[int]:
        """Direct sub-elements, without design alternatives."""
        return self._children.get(node_id, [])

    def alternatives(self, node_id: int) -> list[int]:
        return self._alternatives.get(node_id, [])

    def ancestors(self, node_id: int) -> list[dict]:
        chain = []
        parent = self.nodes[node_id]["parent_id"]
        while parent is not None:
            chain.append(self.nodes[parent])
            parent = self.nodes[parent]["parent_id"]
        return chain

    def label(self, node_id: int) -> str:
        node = self.nodes[node_id]
        if node["alternative_of"] is not None:
            return f"{node['name']} [{node['alt_label']}]"
        return node["name"]

    def total_weight(self, node_id: int) -> tuple[float | None, list[int]]:
        """Weight of one unit of the node in kg, and the nodes whose weight is missing.

        An entered weight counts on top of the sub-elements' weights unless the
        node is ticked "this is the total".
        """
        node = self.nodes[node_id]
        children = self.children(node_id)
        if node["weight_is_total"] or not children:
            if node["weight"] is None:
                return None, [node_id]
            return node["weight"], []
        total, missing = node["weight"] or 0.0, []
        for child_id in children:
            weight, child_missing = self.total_weight(child_id)
            missing += child_missing
            if weight is not None:
                total += self.nodes[child_id]["quantity"] * weight
        return (None if missing else total), missing

    def own_weight(self, node_id: int) -> float | None:
        """Weight that belongs to the node itself and to none of its sub-elements."""
        node = self.nodes[node_id]
        children = self.children(node_id)
        if not children:
            return node["weight"]
        if not node["weight_is_total"]:
            return node["weight"] or 0.0
        if node["weight"] is None:
            return None
        below = 0.0
        for child_id in children:
            weight, _ = self.total_weight(child_id)
            below += self.nodes[child_id]["quantity"] * (weight or 0.0)
        return node["weight"] - below
