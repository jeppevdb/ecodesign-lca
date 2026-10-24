import pandas as pd
# 1. File paths & settings
csv_file = "all_results_by_scenario_base_design.csv"
excel_tpl = "openlca_full_system_{}.xlsx" # will fill in 'best','average','worst'
scenarios = ["best", "average", "worst"]
sheet_name = "Impacts"
cat_col = "Impact category"
val_col = "Result"
# 2. Load & sum Python (CSV) results by scenario_setting & characterized impact category
df_csv = pd.read_csv(csv_file)
df_csv = df_csv[df_csv["country"] == "EU"] # Filter for EU only
char_cols = sorted([c for c in df_csv.columns if c.startswith("Characterized -")])
df_csv_sum = df_csv.groupby("scenario_setting")[char_cols].sum()
# 3. Prepare an empty DataFrame indexed by stripped category names
categories = [c.replace("Characterized -", "") for c in char_cols]
output = pd.DataFrame(index=categories)
# 4. For each scenario, pull Python & OpenLCA values, compute % difference, and store
for scen in scenarios:
 # --- Python values ---
 py = df_csv_sum.loc[scen, char_cols]
 py.index = py.index.str.replace("Characterized -", "")
 
 # openLCA values, skip first header row
 df_olca = pd.read_excel(
 excel_tpl.format(scen),
 sheet_name=sheet_name,
 skiprows=1
 )
 olca = df_olca.set_index(cat_col)[val_col]
 olca = olca.reindex(categories, fill_value=0)
 
 # Percent difference 
 diff = (olca - py) / py * 100
 
 #Assign into output 
 output[f"{scen} - python"] = py.values
 output[f"{scen} - openlca"] = olca.values
 output[f"{scen} - difference (%)"]= diff.values
# 5. Finalize & write to Excel
output = output.reset_index().rename(columns={"index": "impact_category"})
output.to_excel("validation_results.xlsx", index=False)