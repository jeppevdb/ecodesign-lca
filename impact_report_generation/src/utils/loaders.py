from functools import lru_cache
from pathlib import Path
import pandas as pd




def set_data_dir(path: Path):
    """
    Update the global data directory used by all loaders.
    Call this once from main.py with processed_data/<product>/.
    """
    global DATA_DIR
    DATA_DIR = Path(path)

    # Clear caches so new data loads correctly
    scenario_df.cache_clear()
    parameter_df.cache_clear()
    design_scenario_df.cache_clear()
    scenario_description.cache_clear()
    cutoffs.cache_clear()
    system_structure_df.cache_clear()
    system_info_df.cache_clear()
    design_change_descriptions.cache_clear()
    country_variations.cache_clear()


@lru_cache(maxsize=None)
def design_scenario_df():
    return pd.read_csv(DATA_DIR / "all_results_by_scenario.csv")


@lru_cache(maxsize=None)
def scenario_df():
    return pd.read_csv(DATA_DIR / "all_results_by_scenario_base_design.csv")


@lru_cache(maxsize=None)
def parameter_df():
    return pd.read_csv(DATA_DIR / "all_results_by_parameter_base_design.csv")


@lru_cache(maxsize=None)
def scenario_description():
    return pd.read_excel(DATA_DIR / "scenarios.xlsx")


@lru_cache(maxsize=None)
def cutoffs():
    return pd.read_excel(DATA_DIR / "cutoff_df.xlsx")


@lru_cache(maxsize=None)
def system_structure_df():
    return pd.read_excel(DATA_DIR / "system_structure_and_costs.xlsx")


@lru_cache(maxsize=None)
def system_info_df():
    return pd.read_excel(DATA_DIR / "system_info.xlsx")


@lru_cache(maxsize=None)
def design_change_descriptions():
    return pd.read_excel(DATA_DIR / "design_change_descriptions.xlsx")


@lru_cache(maxsize=None)
def country_variations():
    return pd.read_excel(DATA_DIR / "country_variations.xlsx")

# # these functions are not used for now, maybe later

# from functools import lru_cache

# @lru_cache(maxsize=None)
# def design_scenario_df():
#     return pd.read_csv(DATA / "all_results_by_scenario.csv")

# # @lru_cache(maxsize=None)
# # def design_parameter_df():
# #     return pd.read_csv(DATA / "all_lcis_by_parameter.xlsx")

# @lru_cache(maxsize=None)
# def scenario_df():
#     return pd.read_csv(DATA / "all_results_by_scenario_base_design.csv")

# @lru_cache(maxsize=None)
# def parameter_df():
#     return pd.read_csv(DATA / "all_results_by_parameter_base_design.csv")

# @lru_cache(maxsize=None)
# def scenario_description():
#     return pd.read_excel(DATA / "scenarios.xlsx")

# @lru_cache(maxsize=None)
# def cutoffs():
#     return pd.read_excel(DATA / "cutoff_df.xlsx")

# @lru_cache(maxsize=None)
# def system_structure_df():
#     return pd.read_excel(DATA / "system_structure_and_costs.xlsx")

# @lru_cache(maxsize=None)
# def system_info_df():
#     return pd.read_excel(DATA / "system_info.xlsx")

# @lru_cache(maxsize=None)
# def design_change_descriptions():
#     return pd.read_excel(DATA / "design_change_descriptions.xlsx")

# @lru_cache(maxsize=None)
# def country_variations():
#     return pd.read_excel(DATA / "country_variations.xlsx")