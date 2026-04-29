import os
import json
import time
import logging
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import simpledialog, messagebox

# === IMPORT YOUR MODULES ===
from exhaustive_result_calculation import run_calculation   # your result calculation script
from impact_report_generation import app                  # your Panel app

# === CONFIGURATION ===
RAW_DIR = Path("raw_data")
PROCESSED_DIR = Path("processed_data")
STATE_FILE = Path("last_state.json")
LOG_FILE = Path("log.txt")
PANEL_URL = "http://localhost:5006/LCA_Dashboard"  # adjust if needed


# ---------------------------
#           Logging         #
# ---------------------------
def setup_logging():
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


# ---------------------------
# Select LCI file
# ---------------------------


def select_lci_file() -> Path:
    candidates = list(RAW_DIR.glob("lci_file_*.xlsx"))

    if not candidates:
        messagebox.showerror("Error", f"No LCI files found in {RAW_DIR}")
        raise FileNotFoundError("No LCI files found")

    # If only one file → return directly
    if len(candidates) == 1:
        return candidates[0]

    # Multiple → dropdown selection window
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title("Select LCI File")

    tk.Label(root, text="Select the product LCI file to process:", padx=10, pady=10).pack()

    options = [f.name for f in candidates]
    selected_file = tk.StringVar(value=options[0])

    combo = ttk.Combobox(root, textvariable=selected_file, values=options, state="readonly", width=50)
    combo.pack(padx=15, pady=10)

    selected_path = {"path": None}

    def confirm_selection():
        filename = selected_file.get()
        selected_path["path"] = RAW_DIR / filename
        root.destroy()

    tk.Button(root, text="Confirm", command=confirm_selection, width=15).pack(pady=(5, 15))

    root.mainloop()

    if selected_path["path"] is None:
        messagebox.showerror("Error", "No file selected. Exiting.")
        raise ValueError("No LCI file selected")

    return selected_path["path"]

# ---------------------------
# State management
# ---------------------------
def lci_file_modified(lci_file: Path) -> bool:
    """Check if LCI file updated since last run."""
    last_mod_time = lci_file.stat().st_mtime
    if not STATE_FILE.exists():
        return True
    try:
        state = json.loads(STATE_FILE.read_text())
        prev_time = state.get(lci_file.name, 0)
        return last_mod_time > prev_time
    except Exception:
        return True


def save_state(lci_file: Path):
    last_mod_time = lci_file.stat().st_mtime
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
    else:
        state = {}
    state[lci_file.name] = last_mod_time
    STATE_FILE.write_text(json.dumps(state))


# ---------------------------
# Main workflow
# ---------------------------
def select_backend() -> str:
    root = tk.Tk()
    root.title("Select LCA Backend")

    tk.Label(root, text="Select the LCA backend to use:", padx=10, pady=10).pack()

    selected = tk.StringVar(value="openlca")

    for value, label in [("openlca", "OpenLCA  (requires running IPC server)"),
                          ("brightway", "Brightway  (fully in-process, no external server)")]:
        tk.Radiobutton(root, text=label, variable=selected, value=value, anchor="w").pack(
            fill="x", padx=20, pady=2
        )

    result = {"backend": None}

    def confirm():
        result["backend"] = selected.get()
        root.destroy()

    tk.Button(root, text="Confirm", command=confirm, width=15).pack(pady=(10, 15))
    root.mainloop()

    if result["backend"] is None:
        raise ValueError("No backend selected.")
    return result["backend"]


def main():
    setup_logging()
    logging.info("=== Program started ===")

    try:
        # Step 1: Select LCI file
        lci_file = select_lci_file()
        product_name = lci_file.stem.replace("lci_file_", "")
        out_dir = PROCESSED_DIR / product_name
        out_dir.mkdir(parents=True, exist_ok=True)
        logging.info("Selected product: %s → output folder: %s", product_name, out_dir)

        # Step 2: Run calculations if needed
        if lci_file_modified(lci_file):
            backend = select_backend()
            logging.info("LCI changed → recalculating with backend: %s", backend)
            run_calculation.main(lci_file, out_dir, backend=backend)
            save_state(lci_file)
        else:
            logging.info("LCI file unchanged → using cached results")

        # Step 3: Launch dashboard
        logging.info("Launching report")
        from impact_report_generation.src.utils import loaders
        loaders.set_data_dir(out_dir)
        app.run_dashboard(out_dir)  # tell app.py where to load data
        time.sleep(2)
        webbrowser.open(PANEL_URL)

    except Exception as e:
        logging.exception("Fatal error")
        print("⚠️ Error occurred. See log.txt for details.")
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()


