def calculate_impacts(final_results_df, file_path):
    """
    Calculates environmental impacts based on the selected LCI model.

    Steps:
    1. Read 'process_results' and 'elementary_flow_results' from the Excel file.
    2. Iterate over each row in final_results_df.
    3. For each row, pick the correct impacts sheet based on 'database_datatype'.
    4. Multiply 'process_amount' by matching impact factors in that sheet.
    5. Store results in new columns on a copy of final_results_df.
    6. Return the updated DataFrame.
    """
    import pandas as pd

    # load the two impact‐factor sheets
    process_impacts = pd.read_excel(file_path, sheet_name="process_results")
    flow_impacts    = pd.read_excel(file_path, sheet_name="elementary_flow_results")

    # work on a copy so we don't modify the original
    df = final_results_df.copy()

    # cache column‐lists to skip when assigning
    skip_columns = {"database_uuid", "database_origin"}

    # iterate over rows
    for idx, row in df.iterrows():
        db_uuid  = row["database_uuid"]
        db_type  = row["database_datatype"]
        amount   = float(row["process_amount"])

        if db_type == "process":
            match = process_impacts[process_impacts["database_uuid"] == db_uuid]
        elif db_type in ("flow", "elementary_flow"):
            match = flow_impacts[flow_impacts["database_uuid"] == db_uuid]
        else:
            # unknown type—skip
            continue

        if match.empty:
            # no matching impact factors—skip
            continue

        # take the first (and presumably only) matching row
        impact_row = match.iloc[0]
        for col, val in impact_row.items():
            if col not in skip_columns:
                df.at[idx, col] = amount * float(val)
    selected_lci_result = df.copy()

    return selected_lci_result