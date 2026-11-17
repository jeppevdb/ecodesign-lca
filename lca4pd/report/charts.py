"""Plotly figures for the report. Each function takes prepared data and returns a figure."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .data import OWN, ReportData

FONT = dict(size=14)
UNCERTAINTY_SCALE = [(0, "green"), (0.5, "yellow"), (1, "red")]
PALETTE = px.colors.qualitative.Safe + px.colors.qualitative.Pastel


def _layout(fig, title: str, height: int = 500, **kwargs):
    settings = dict(title=dict(text=title, font=dict(size=16)), font=FONT, height=height,
                    margin=dict(t=70, b=40, l=40, r=20), plot_bgcolor="white",
                    legend=dict(font=dict(size=12)))
    settings.update(kwargs)
    fig.update_layout(**settings)
    fig.update_yaxes(gridcolor="rgba(200,200,200,0.4)", zerolinecolor="rgba(0,0,0,0.5)")
    return fig


def stacked_bars(frame: pd.DataFrame, x: str, stack: str, value: str, title: str,
                 ylabel: str, xlabel: str = "", order=None, height=500):
    """Bars per ``x`` built up from ``stack``; credits go below zero."""
    grouped = frame.groupby([x, stack], sort=False)[value].sum().reset_index()
    if order is None:
        order = grouped.groupby(x)[value].sum().sort_values(ascending=False).index.tolist()
    fig = px.bar(grouped, x=x, y=value, color=stack, barmode="relative",
                 category_orders={x: list(order)}, color_discrete_sequence=PALETTE,
                 labels={value: ylabel, x: xlabel, stack: ""})
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:.4g}<extra></extra>")
    return _layout(fig, title, height, showlegend=grouped[stack].nunique() <= 25)


def grouped_bars(frame: pd.DataFrame, x: str, group: str, value: str, title: str,
                 ylabel: str, xlabel: str = "", order=None, facet: str | None = None,
                 height=480):
    grouped = frame.groupby([x, group] + ([facet] if facet else []), sort=False)[value]\
        .sum().reset_index()
    fig = px.bar(grouped, x=x, y=value, color=group, barmode="group", facet_col=facet,
                 category_orders={x: list(order)} if order is not None else None,
                 color_discrete_sequence=PALETTE, labels={value: ylabel, x: xlabel, group: ""})
    fig.update_traces(hovertemplate="%{x}<br>%{fullData.name}: %{y:.4g}<extra></extra>")
    if facet:
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1] + " case"))
    return _layout(fig, title, height)


def sunburst(frame: pd.DataFrame, title: str, colour_uncertainty: bool, height=700):
    if frame.empty:
        return _layout(go.Figure(), title + " – nothing to show", 300)
    kwargs = dict(ids=frame["id"], labels=frame["label"], parents=frame["parent"],
                  values=frame["value"], branchvalues="total",
                  hovertemplate="%{label}<br>%{value:.4g} (%{percentRoot:.1%})<extra></extra>",
                  insidetextorientation="radial")
    if colour_uncertainty:
        kwargs["marker"] = dict(colors=frame["uncertainty"].fillna(-1), cmin=1, cmax=5,
                                colorscale=UNCERTAINTY_SCALE, showscale=True,
                                colorbar=dict(title="Uncertainty<br>score"))
        kwargs["customdata"] = frame["uncertainty"].round(2)
        kwargs["hovertemplate"] = ("%{label}<br>%{value:.4g} (%{percentRoot:.1%})<br>"
                                   "uncertainty %{customdata}<extra></extra>")
    fig = go.Figure(go.Sunburst(**kwargs))
    return _layout(fig, title, height, margin=dict(t=60, b=10, l=10, r=10))


def sankey(data: ReportData, rows: pd.DataFrame, key: str, max_depth: int, title: str):
    """Flows from the elements up to the product. Credits flow the other way."""
    flows: dict[tuple[str, str], float] = {}
    for path_ids, value in zip(rows["path_ids"], rows[key]):
        path = data.path(path_ids)
        node = path[-1]
        names = [data.labels[n] for n in path]
        if data.has_children(node):
            names.append(data.labels[node] + OWN)
        names = names[:max_depth + 1]
        for child, parent in zip(names[1:], names[:-1]):
            flows[(child, parent)] = flows.get((child, parent), 0.0) + value
    links = [(s, t, v) if v > 0 else (t, s, -v) for (s, t), v in flows.items() if v]
    labels = list(dict.fromkeys([name for s, t, _ in links for name in (s, t)]))
    index = {name: i for i, name in enumerate(labels)}
    fig = go.Figure(go.Sankey(
        node=dict(label=labels, pad=12, thickness=16),
        link=dict(source=[index[s] for s, _, _ in links], target=[index[t] for _, t, _ in links],
                  value=[v for _, _, v in links],
                  hovertemplate="%{source.label} → %{target.label}: %{value:.4g}<extra></extra>"),
    ))
    return _layout(fig, title, max(450, 26 * len(labels)))


def tornado(frame: pd.DataFrame, title: str):
    fig = go.Figure()
    if frame.empty:
        return _layout(fig, title + " – no scenarios", 300)
    fig.add_bar(y=frame["Scenario"], x=frame["best (%)"], orientation="h", name="Best case",
                marker_color="green",
                hovertemplate="%{y}: %{x:+.2f} %<extra>best case</extra>")
    fig.add_bar(y=frame["Scenario"], x=frame["worst (%)"], orientation="h", name="Worst case",
                marker_color="firebrick",
                hovertemplate="%{y}: %{x:+.2f} %<extra>worst case</extra>")
    fig.add_vline(x=0, line_color="black")
    fig.update_layout(barmode="overlay", xaxis_title="Change compared with the average case (%)")
    return _layout(fig, title, max(300, 60 + 45 * len(frame)))


def category_bars(frame: pd.DataFrame, column: str, title: str, ylabel: str):
    fig = px.bar(frame, x="Impact category", y=column, color_discrete_sequence=[PALETTE[0]],
                 labels={column: ylabel, "Impact category": ""})
    fig.update_traces(hovertemplate="%{x}: %{y:.4g}<extra></extra>")
    return _layout(fig, title, 520, xaxis_tickangle=-40)


def radar(frame: pd.DataFrame, title: str):
    """Each version as a percentage of the base in every category."""
    fig = go.Figure()
    categories = [c for c in frame.columns if c != "Version"]
    for _, row in frame.iterrows():
        values = [row[c] for c in categories]
        fig.add_trace(go.Scatterpolar(
            r=values + values[:1], theta=categories + categories[:1], name=row["Version"],
            fill="toself", opacity=0.55,
            hovertemplate="%{theta}: %{r:.1f} % of base<extra>%{fullData.name}</extra>"))
    fig.update_layout(polar=dict(radialaxis=dict(ticksuffix=" %")))
    return _layout(fig, title, 620)


def design_scatter(summary: pd.DataFrame, title: str, impact_label: str):
    """Cost against impact, both as % of the base design."""
    frame = summary.copy()
    base = frame.iloc[0]
    frame["Cost (% of base)"] = frame["Cost"] / base["Cost"] * 100
    frame["Impact (% of base)"] = frame["Impact"] / base["Impact"] * 100
    fig = px.scatter(frame, x="Cost (% of base)", y="Impact (% of base)", color="Design",
                     symbol="Design", color_discrete_sequence=PALETTE,
                     labels={"Impact (% of base)": f"{impact_label} (% of base design)",
                             "Cost (% of base)": "Product cost (% of base design)"})
    fig.update_traces(marker=dict(size=18, line=dict(width=1, color="black")))
    fig.add_hline(y=100, line_dash="dash", line_color="gray")
    fig.add_vline(x=100, line_dash="dash", line_color="gray")
    return _layout(fig, title, 560)
