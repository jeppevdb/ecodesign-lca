# 📚 LCA Glossary

This glossary walks you step-by-step through the key terms and concepts of Life-Cycle Assessment (LCA). We’ll follow the same smartphone example throughout—comparing two phones delivering identical services over a 2-year lifespan—so you can see exactly how each concept fits together.  

---

## Functional Unit  
**Official definition**  
A *functional unit* is a quantified description of the performance of a product system, used as the reference basis so that different systems can be compared on exactly the same functional output.  

**Why it matters**  
In LCA, you must compare apples to apples. If you compare two light bulbs, one might last longer but use more power; if you don’t define a clear “unit” of service, your results will be meaningless.  

**Smartphone example**  
- **Functional unit**: “A smartphone providing standard features (calls, texting, web browsing, app use) continuously over two years.”  
- By locking in “2 years of use” and “these functions,” you ensure both phones are evaluated on exactly the same promise of service—so differences in materials, energy use, or emissions reflect real performance trade-offs, not just arbitrary lifetimes or feature sets.  

---

## Reference Flow  
**Official definition**  
The *reference flow* is the physical quantity of products (or services) needed to fulfill the functional unit, linking your defined unit of function to the actual life-cycle inventory data.  

**Why it matters**  
Once you say “2 years of smartphone use,” you need to know how many physical devices that requires. The reference flow tells you “one smartphone” or “two batteries” or “X kWh of charging,” so you can gather the correct raw data.  

**Smartphone example**  
- For our 2 years of smartphone use, the reference flow could simply be “one smartphone (type A) + X kWh of electricity for charging” if the smartphone's lifespan matches the functional unit. If the lifespan is e.g. shorter (1 year), the reference flow would be "two smartphones (type B) + X kWh of electricity for charging"
- A reference flow as listed in the example is then used as a starting point to collect the more specific data required to model the exact in- and outputs per functional unit (e.g., how many kilograms of aluminum, grams of rare-earth metals, or liters of cooling water are used per reference flow in to manufacture one smartphone.)

---

## Life-Cycle Stages  
**Official definition**  
*Life-cycle stages* are the sequential phases of a product system—from raw material extraction, through manufacturing, transportation, use, and end-of-life—over which all material and energy inputs and emissions are inventoried.  

**Why it matters**  
To make sure that all relevant environmental impacts are identified, it is important to consider the entire life cycle from cradle to grave, as skipping any stage risks under-reporting impacts. Breaking the life cycle into stages also helps identify where the biggest “hotspots” are.  

**Smartphone example**  
1. **Materials** (cradle): Mining and refining metals (lithium, cobalt), producing plastics and glass  
2. **Manufacturing**: Assembly lines, circuit board soldering, screen lamination  
3. **Transportation**: Shipping phones from factory to distribution centers to stores  
4. **Use**: Daily charging (electricity mix), network usage (data centers) over two years  
5. **End-of-Life** (grave): Dismantling, recycling precious metals, disposing of plastics and batteries  

---

## OpenLCA Database Basics  
**Official definition**  
OpenLCA databases structure LCA data into **processes** (technological activities with defined inputs, outputs, and emissions) and **elementary flows** (transfers between the technosphere and the environment). 
**Why it matters**  
To calculate the impacts of the studied system, the real-world activity data needs to be translated into environmental data. This is done by breaking down the system into smaller modules that can be represented as either a process or elementary flow. Your inventory depends entirely on the quality of these data, and how well the selected process or elementary flow represent the real-world activity.

**Smartphone example**  
- A **process** could be used to represent the overall process of manufacturing of the smartphone's screen. This could e.g. be “LCD display manufacturing - China ” which models all inputs (glass, energy) and outputs (CO₂, chemical waste) that take place in order to e.g. produce 1 kg of LCD display. By multiplying the actual weight of the LCD display in the smartphone by the in- and outputs per kg, the in- and outputs per smarthpone screen can be calculated.
- If data is available regarding the direct exchanges with the environment, an **elementary flow** can be used to represent this, e.g. “CO₂ emitted to air” or “silica extracted from mine.”.

---

## How Environmental Impacts Are Measured in LCA (for Non-Experts)

When we make or use something—like a smartphone—we release all sorts of chemicals into the air, water and soil. But not all those releases “count” the same way. Life-Cycle Impact Assessment (LCIA) helps us translate raw emissions (like kilograms of methane or nitrogen dioxide) into meaningful measures of environmental harm. Here’s how it works, step by step, using **methane (CH₄)** and **nitrogen dioxide (NO₂)** as our running examples.

---

## 1. Multiple Impact Categories  
The environment can be harmed in different ways. LCA organizes these into **impact categories**, each tracking one kind of problem:

| Impact category             | What it measures                       | Key pollutant examples            |
|-----------------------------|----------------------------------------|-----------------------------------|
| **Climate change**          | “Greenhouse effect” warming our planet | CO₂, CH₄                          |
| **Acidification**           | Rain and soils becoming too acidic     | SO₂, NO₂                          |
| *(…and several others…)*    |                                        |                                   |

Different pollutants feed into different categories. For instance:
- **Methane (CH₄)** is a potent greenhouse gas, and contributes to the **Climate change** impact category.
- **Nitrogen dioxide (NO₂)** can e.g. acidify rain, contributing to the **Acidification** impact category. 
---

## 2. Characterization: Converting to Common Units  
Each pollutant gets multiplied by a **characterization factor** so we can compare apples to apples.

**Example: A smartphone’s production emits**  
- **0.20 kg of CH₄**  
- **0.20 kg of NO₂**  

**How much “impact” is that?**  
- **Climate change indicator (kg CO₂-equivalent)**  
  - CH₄ factor = **25** (1 kg CH₄ warms as much as 25 kg CO₂ does).  
  - 0.20 kg CH₄ × 25 = **5 kg CO₂eq.**  

- **Acidification indicator (kg SO₂-equivalent)**  
  - NO₂ factor = **0.7** (1 kg NO₂ acidifies as much as 0.7 kg SO₂ does).  
  - 0.20 kg NO₂ × 0.7 = **0.14 kg SO₂eq.**  

After characterization, we get:  
> • **5 kg CO₂eq.** (climate change)  
> • **0.14 kg SO₂eq.** (acidification)  

---

## 3. Normalization: Putting Impacts in Context  
Is 5 kg CO₂e a lot? We divide by a reference—typically an average person’s yearly emissions:

- Average person emits **10 000 kg CO₂eq. / year** →  
  5 ÷ 10 000 = **0.0005 “person-year eq.”** for climate change  
- Average person causes **2 kg SO₂eq. / year** →  
  0.14 ÷ 2 = **0.07 person-year eq.** for acidification  


Now each impact is a fraction of an average person’s annual “share.”

---

## 4. Weighting: Reflecting Which Impact Categories are Most Relevant 
To reflect differences in how important different impact categories are in relation to each other, a weighing factor can be applied.
Weighting lets us say, for example:
- Climate change = **twice** as important as acid rain  
- Water pollution = **equally** important as acid rain  

| Category         | Normalized score | Weight | Weighted score        |
|------------------|------------------|--------|-----------------------|
| Climate change   | 0.0005           | 2      | 0.0005 × 2 = 0.001    |
| Acidification    | 0.07             | 1      | 0.07 × 1 = 0.07       |

---

## 5. Single-Score: One Number to Rule Them All  
Finally, we add up all weighted impacts:

> **Total single-score** = 0.001 + 0.07 = **0.08 points**

This single number makes it easy to **compare** products or processes: lower score = lower overall environmental burden **(given your chosen weights)**.

---

### Why This Matters  
- **Transparency**: Shows which pollutants drive which problems.  
- **Context**: Normalization puts impacts in context of global averages.  
- **Values**: Weighting reflects policy or stakeholder priorities.  
- **Simplicity**: A single-score helps rank dozens of options at a glance.

By following these steps—**characterization**, **normalization**, **weighting**, and **aggregation**—LCA turns raw data (kgs of CH₄ or NO₂) into clear, comparable insights about environmental impacts.  

---

## Uncertainty scores 
**Official definition**  
Data uncertainty in this report is quantified via the *pedigree matrix* , which assigns a score between 1 (high certainty) and 5 (high uncertainty)for every process and elementary flow on 5 aspects: reliability, completeness, and temporal-, geographical-, & technological correlation. By calculating the average score assigned to these 5 aspects, an overall Data Quality Score can be identified. In essence, this score defines how accurately the chosen process/elementary flow represents reality. 

**Why it matters**  
No data are perfect. The uncertainty scores used in this report give a rough indicator of how reliable (or unreliable) results are. By showing the Data Quality Score alongside the total impacts, it is possible to identify where the largest sources of uncertainty are within the system

**Smartphone example**  
- If the only dataset that is available to represent the production of the smartphone's battery is a 10-year old process dataset covering an entirely different battery type, the accuracy of the results would be quite low, and the process would be assigned a bad Data Quality Score (e.g., >4)
- If a very recent dataset is available which covers the production of exactly the same battery as the one used in the smartphone, the accuracy would be higher, and the process would be assigned a good Data Quality Score (e.g., <2)

---

## Learn More  
- **ILCD Handbook - Extensive guide on LCA by the EU's Joint Research Center**  
  <https://eplca.jrc.ec.europa.eu/uploads/ILCD-Handbook-General-guide-for-LCA-DETAILED-GUIDANCE-12March2010-ISBN-fin-v1.0-EN.pdf>  
- **OpenLCA Documentation**  
  <https://greendelta.github.io/openLCA2-manual/>  
- **Ecochain Help Center - general information on LCA**  
  <https://helpcenter.ecochain.com/en/> 