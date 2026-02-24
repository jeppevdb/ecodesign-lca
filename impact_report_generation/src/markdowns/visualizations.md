# Visualization Guide

Welcome! This guide explains **what** each graph shows and **how** you can interact with it—even if you’ve never used these plots (or done an LCA) before.

---

## 1. Sankey Diagram

A Sankey diagram displays **flows** between stages or categories:

- **Nodes** (rectangles or circles) represent life-cycle stages (e.g. raw material, production, use, end-of-life).  
- **Bands** between nodes show the magnitude of flow (e.g. kg CO₂ eq or mass of material). The **thicker** the band, the larger the flow.  
- **Splits** (one node → many) and **joins** (many → one) are immediately visible.

**When to use it:**  
Great for tracing where the biggest impacts “travel” through your product’s life cycle.

**How to read it:**  
1. Look at a band’s thickness to compare flows.  
2. Hover over a band to see exact values and percentages of the total.

---

## 2. Bar Charts

Bar charts compare values across categories or groups:

- **Single bars** show one value per category (e.g. total CO₂ for each stage).  
- **Stacked bars** break each bar into colored segments (e.g. materials vs. transport) so you see both totals and composition.  
- **Grouped bars** place bars side-by-side for different scenarios (e.g. baseline vs. best-case) for direct comparison.  
- **Ranked bars** are sorted (largest to smallest) to highlight the top contributors.

**When to use it:**  
Quickly compare totals or see how different parts add up.

**How to read it:**  
1. Find the axis labels (bottom/side) to know what each bar stands for.  
2. In stacked bars, look at both the overall height and each colored segment.  
3. Hover to get exact numbers.

---

## 3. Radar (Spider) Chart

A radar chart maps multiple variables on spokes radiating from a center:

- Each **spoke** is one impact category (e.g. climate, eutrophication, resource use).  
- The **distance** from the center shows the magnitude.  
- Connecting the data points creates a web shape.

**When to use it:**  
Compare profiles across several categories at once (e.g. baseline vs. design variant).

**How to read it:**  
1. Check each axis label for the category.  
2. A larger area of the total web means higher impacts overall.  
3. Hover a point to see the exact value.

---

## 4. Sunburst Diagram

Sunbursts show hierarchical data with concentric rings:

- **Center** ring = top level (entire system).  
- **Next ring** = assemblies.  
- **Outer ring** = components.  

The size of a slice is proportional to its share of the parent’s total **environmental impacts** for the selected impact category, and the colour of each slice indicates the weighted **uncertainty score** (scale 1 = low uncertainty, 5 = high uncertainty; green → yellow → red).

In the system-, assembly- and component-level analysis sections, multiple sunbursts are generated for each selected country under the **average**, **best**, and **worst** scenario settings. Displaying them side by side lets you compare how scenario & country variations affect the breakdown of impacts & uncertainty.

**When to use it:**  
Reveal how your total impact breaks down, level by level, and assess uncertainty at each level.

**How to read it:**  
1. Hover a slice to see its value, its percentage of the parent total, and its uncertainty score.  
2. Larger slices = bigger impact.  
3. Compare the three diagrams (average, best, worst) for the same country to understand sensitivity to changing assumptions.


## 5. Scatter Plot

Scatter plots chart two numerical variables against each other:

- **X-axis** represent the percentual change in costs; the **Y-axis** represents the percentual change in environmental impacts for the selected category.  
- Each **point** represents the results for either the **base design** or a system version where a **system, assembly or component variation** has been implemented.

**When to use it:**  
Identify how the different design variations that have been modeled compare to each other. The 

**How to read it:**  
1. Identify a point’s coordinates.  
2. Hover to see its exact values and label.

---

# How to interact with these visualizations

Our charts use **HoloViews**, which adds powerful built-in interaction:

### A. Multi-Selector Filters  
- **Assembly / Component Selector**: Check or uncheck items to include/exclude them.
- **Impact Category Selector**: Pick the category you want (e.g. Global Warming, Eutrophication).  
- **Region Selector**: (If available) switch the geographic context to see how use-phase impacts change.  
- **Scenario Selector**: Toggle between baseline, best-case, and worst-case assumptions instantly.

### B. Hover Tooltips  
Move your mouse over any bar, slice, band, or point to reveal a tooltip with:  
- Exact numerical values (e.g. kg CO₂ eq)  
- Percentage of the total  
- Metadata like material or process names

### C. Zoom & Pan  
- **Mouse wheel / Pinch**: Zoom in/out on the plot.  
- **Click & drag**: Pan around when zoomed.

### D. Box Zoom & Reset  
- **Box-zoom icon**: Click it, then draw a rectangle to zoom into a region.  
- **Home / Reset icon**: Click to return to the full view.

### E. Exporting & Saving  
- **Camera / Save icon**: Click to download the current view as a PNG image.  
- **CSV Download**: Some tables include a download button to save the underlying data.

---

With these tools, you can explore, compare, and export insights at any level—whether you need a quick snapshot or a deep dive.  
