import json
import os
import re

def clean_json(raw_str):
    if not raw_str: return "{}"
    match = re.search(r'\{.*\}', str(raw_str), re.DOTALL)
    return match.group(0) if match else raw_str

def save_data(filename, payload):
    tmp_filename = f"{filename}.tmp"
    with open(tmp_filename, "w") as f:
        json.dump(payload, f, indent=4)
    os.replace(tmp_filename, filename) # Atomic overwrite

def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f: return json.load(f)
        except Exception as e: 
            print(f"⚠️ Error loading {filename}: {e}. Returning empty.")
            return {}
    return {}