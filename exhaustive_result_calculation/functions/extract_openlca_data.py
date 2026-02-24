import json
from pathlib import Path
import pandas as pd
import olca_ipc as ipc
import olca_schema as o


def extract_openlca_data(lci_file_path: str, out_dir: Path, server_port: int = 8080) -> None:
    """
    1) Ensure out_dir/impact_units.json exists (querying openLCA if needed)
    2) Check for any database_uuid in standardized_lci_data missing a single_score
    3) For each database_origin, prompt to switch the openLCA IPC database,
       then calculate only those missing process & flow impacts
    4) Write updated process_results & elementary_flow_results back into the LCI Excel
    """

    # helper: check completeness of impact factors 
    def all_impact_factors_present(lci_file_path: Path) -> bool:
        standardized_data = pd.read_excel(
            lci_file_path,
            sheet_name="standardized_lci_data",
            usecols=["database_uuid"]
        )
        required_uuids = set(standardized_data["database_uuid"].dropna())

        def covered_uuids_in_sheet(sheet_name: str) -> set[str]:
            try:
                result_data = pd.read_excel(
                    lci_file_path,
                    sheet_name=sheet_name,
                    usecols=["database_uuid", "single_score"]
                )
            except ValueError:
                return set()
            return set(
                result_data.loc[result_data["single_score"].notna(), "database_uuid"]
            )

        covered_process_uuids = covered_uuids_in_sheet("process_results")
        covered_flow_uuids    = covered_uuids_in_sheet("elementary_flow_results")
        covered_uuids = covered_process_uuids.union(covered_flow_uuids)

        missing_uuids = required_uuids - covered_uuids
        if missing_uuids:
            print(f"[all_impact_factors_present] {len(missing_uuids)} missing UUID(s).")
        return not missing_uuids

    # helper: ensure impact_units.json exists (but store in processed_dir)
    def create_impact_units_json_if_missing(lci_file_path: Path) -> None:
        units_json_path = out_dir / "impact_units.json"
        print(units_json_path)
        if units_json_path.exists():
            return

        lcia_methods_table = pd.read_excel(
            lci_file_path,
            sheet_name="lcia_methods"
        )
        method_definitions = []
        for _, row in lcia_methods_table.iterrows():
            method_definitions.append({
                "method_uuid":           row["method uuid"],
                "compute_characterized": bool(row["characterized"]),
                "compute_normalized":    bool(row["normalized"]),
                "compute_single_score":  bool(row["single_score"]),
            })

        openlca_client = ipc.Client(server_port)
        units_map: dict[str, str] = {}

        for method_definition in method_definitions:
            impact_method_object = openlca_client.get(
                o.ImpactMethod,
                method_definition["method_uuid"]
            )
            if impact_method_object is None:
                print(f"Warning: ImpactMethod not found: {method_definition['method_uuid']}")
                continue

            for category_reference in impact_method_object.impact_categories:
                category_name = category_reference.name

                if method_definition["compute_characterized"]:
                    units_map[f"Characterized -{category_name}"] = str(category_reference.ref_unit)
                if method_definition["compute_normalized"]:
                    units_map[f"Normalized -{category_name}"] = "person-year equivalent"
                if method_definition["compute_single_score"]:
                    units_map[f"Normalized & weighted -{category_name}"] = "unitless"

        with open(units_json_path, "w") as json_file:
            json.dump(units_map, json_file, indent=2)
        print(f"Created impact_units.json at: {units_json_path}")

    # helper: safely read a sheet or return empty df 
    def read_or_empty(excel_file: pd.ExcelFile, sheet_name: str) -> pd.DataFrame:
        try:
            return pd.read_excel(excel_file, sheet_name=sheet_name)
        except ValueError:
            return pd.DataFrame()

    # helper: perform single lcia calculation (unchanged)
    def run_single_lcia_calculation(
        openlca_client: ipc.Client,
        product_system_id: str,
        method_definition: dict
    ) -> tuple[dict, dict, dict]:
        impact_method_object = openlca_client.get(
            o.ImpactMethod,
            method_definition["method_uuid"]
        )
        normalization_weighting_set = (
            impact_method_object.nw_sets[method_definition["nwset_index"]]
        )
        calculation_setup = o.CalculationSetup(
            target=o.Ref(ref_type=o.RefType.ProductSystem, id=product_system_id),
            impact_method=o.Ref(ref_type=o.RefType.ImpactMethod, id=method_definition["method_uuid"]),
            nw_set=o.Ref(ref_type=o.RefType.NwSet, id=normalization_weighting_set.id),
            with_regionalization=True,
        )

        calculation_result = openlca_client.calculate(calculation_setup)
        calculation_result.wait_until_ready()

        characterized_results = {
            category.name: sum(flow.amount for flow in calculation_result.get_flow_impacts_of(category))
            for category in calculation_result.get_impact_categories()
        }
        normalized_results = {entry.impact_category.name: entry.amount for entry in calculation_result.get_normalized_impacts()}
        weighted_results   = {entry.impact_category.name: entry.amount for entry in calculation_result.get_weighted_impacts()}

        calculation_result.dispose()
        return characterized_results, normalized_results, weighted_results

    # -------- Main flow --------

    # 1- create impact_units.json if not already present
    create_impact_units_json_if_missing(lci_file_path)

    # 2- check if all impact factors already present
    if all_impact_factors_present(lci_file_path):
        print("All impact factors already present; no update needed.")
        return

    # 3- load workbook
    workbook_excel = pd.ExcelFile(lci_file_path)
    standardized_data_frame = pd.read_excel(workbook_excel, sheet_name="standardized_lci_data")
    lcia_methods_frame = pd.read_excel(workbook_excel, sheet_name="lcia_methods")

    process_results_frame = read_or_empty(workbook_excel, "process_results")
    flow_results_frame    = read_or_empty(workbook_excel, "elementary_flow_results")


    # 4- determine which UUIDs still need process‐level results
    all_process_uuids = (
        standardized_data_frame[
            standardized_data_frame["database_datatype"] == "process"
        ][["database_uuid", "database_origin"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    completed_process_uuids = set(
        process_results_frame.loc[
            process_results_frame["single_score"].notna(),
            "database_uuid"
        ]
    )
    missing_processes_frame = all_process_uuids.loc[
        ~all_process_uuids["database_uuid"].isin(completed_process_uuids)
    ].reset_index(drop=True)

    # 5- determine which UUIDs still need flow‐level results
    all_flow_uuids = (
        standardized_data_frame[
            standardized_data_frame["database_datatype"] == "flow"
        ][["database_uuid", "database_origin"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    completed_flow_uuids = set(
        flow_results_frame.loc[
            flow_results_frame["single_score"].notna(),
            "database_uuid"
        ]
    )
    missing_flows_frame = all_flow_uuids.loc[
        ~all_flow_uuids["database_uuid"].isin(completed_flow_uuids)
    ].reset_index(drop=True)

    # 6- prepare method definitions
    method_definitions = []
    for _, row in lcia_methods_frame.iterrows():
        method_definitions.append({
            "method_uuid":           row["method uuid"],
            "compute_characterized": bool(row["characterized"]),
            "compute_normalized":    bool(row["normalized"]),
            "compute_single_score":  bool(row["single_score"]),
            "nwset_index":          int(row["nwset_index"])
        })

    # 7- openLCA IPC client
    openlca_client = ipc.Client(server_port)

    # 8- iterate over each distinct database_origin
    all_database_origins =(
        set(missing_processes_frame["database_origin"])
        .union(missing_flows_frame["database_origin"])
    )

    for database_name in all_database_origins:
        print(f"\n--- database: {database_name} ---")
        user_confirmation = input(
            f"Switch openLCA IPC server to '{database_name}' and type 'yes' to confirm afterwards: "
        )
        if user_confirmation.strip().lower() != "yes":
            print(f"Skipping database '{database_name}'.")
            continue

        # calculate missing processes
        subset_missing_processes = missing_processes_frame.loc[
            missing_processes_frame["database_origin"] == database_name
        ]
        for _, process_row in subset_missing_processes.iterrows():
            process_uuid = process_row["database_uuid"]
            print(f" Processing: {process_uuid}")
            process_object = openlca_client.get(o.Process, process_uuid)
            if process_object is None:
                print(f"  ! Process not found: {process_uuid}")
                continue

            product_system = openlca_client.create_product_system(process_object)
            for method_definition in method_definitions:
                if not any([
                    method_definition["compute_characterized"],
                    method_definition["compute_normalized"],
                    method_definition["compute_single_score"]
                ]):
                    continue

                char_map, norm_map, wt_map = run_single_lcia_calculation(
                    openlca_client,
                    product_system.id,
                    method_definition
                )

                existing_mask = (
                    process_results_frame["database_uuid"] == process_uuid
                )
                if not existing_mask.any():
                    process_results_frame.loc[len(process_results_frame)] = {
                        "database_uuid": process_uuid,
                        "database_origin": database_name
                    }
                    existing_mask = (
                        process_results_frame["database_uuid"] == process_uuid
                    )

                if method_definition["compute_characterized"]:
                    for category_name, value in char_map.items():
                        process_results_frame.loc[
                            existing_mask, f"Characterized -{category_name}"
                        ] = value

                if method_definition["compute_normalized"]:
                    for category_name, value in norm_map.items():
                        process_results_frame.loc[
                            existing_mask, f"Normalized -{category_name}"
                        ] = value

                if method_definition["compute_single_score"]:
                    for category_name, value in wt_map.items():
                        process_results_frame.loc[
                            existing_mask, f"Normalized & weighted -{category_name}"
                        ] = value
                    process_results_frame.loc[
                        existing_mask, "single_score"
                    ] = sum(wt_map.values())

        # calculate missing flows
        subset_missing_flows = missing_flows_frame.loc[
            missing_flows_frame["database_origin"] == database_name
        ]
        for _, flow_row in subset_missing_flows.iterrows():
            flow_uuid = flow_row["database_uuid"]
            flow_object = openlca_client.get(o.Flow, flow_uuid)
            if (flow_object is None
                    or not flow_object.flow_properties):
                print(f"  ! Flow not executable: {flow_uuid}")
                continue

            flow_property_reference = (
                flow_object.flow_properties[0].flow_property
            )
            temporary_flow = o.new_product(
                f"temporary_flow_{flow_object.name}",
                flow_property_reference
            )
            openlca_client.put(temporary_flow)

            temporary_process = o.new_process(
                f"temporary_process_{flow_object.name}"
            )
            output_reference = o.new_output(
                temporary_process,
                temporary_flow,
                1.0
            )
            output_reference.is_quantitative_reference = True
            o.new_output(temporary_process, flow_object, 1.0)
            openlca_client.put(temporary_process)

            product_system = openlca_client.create_product_system(
                openlca_client.get(
                    o.Process,
                    temporary_process.id
                )
            )

            for method_definition in method_definitions:
                if not any([
                    method_definition["compute_characterized"],
                    method_definition["compute_normalized"],
                    method_definition["compute_single_score"]
                ]):
                    continue

                char_map, norm_map, wt_map = run_single_lcia_calculation(
                    openlca_client,
                    product_system.id,
                    method_definition
                )

                existing_mask = (
                    flow_results_frame["database_uuid"] == flow_uuid
                )
                if not existing_mask.any():
                    flow_results_frame.loc[len(flow_results_frame)] = {
                        "database_uuid": flow_uuid,
                        "database_origin": database_name
                    }
                    existing_mask = (
                        flow_results_frame["database_uuid"] == flow_uuid
                    )

                if method_definition["compute_characterized"]:
                    for category_name, value in char_map.items():
                        flow_results_frame.loc[
                            existing_mask, f"Characterized -{category_name}"
                        ] = value

                if method_definition["compute_normalized"]:
                    for category_name, value in norm_map.items():
                        flow_results_frame.loc[
                            existing_mask, f"Normalized -{category_name}"
                        ] = value

                if method_definition["compute_single_score"]:
                    for category_name, value in wt_map.items():
                        flow_results_frame.loc[
                            existing_mask, f"Normalized & weighted -{category_name}"
                        ] = value
                    flow_results_frame.loc[
                        existing_mask, "single_score"
                    ] = sum(wt_map.values())

    # 9- write updated result sheets back into the same LCI Excel
    with pd.ExcelWriter(
        lci_file_path,
        mode="a",
        engine="openpyxl",
        if_sheet_exists="replace"
    ) as excel_writer:
        process_results_frame.to_excel(excel_writer, sheet_name="process_results", index=False)
        flow_results_frame.to_excel(excel_writer, sheet_name="elementary_flow_results", index=False)

    print("All missing impacts have been calculated and workbook updated.")
