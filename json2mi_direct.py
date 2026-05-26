import importlib
import unreal
import json
import utils

importlib.reload(utils)
from utils import apply

EditorUtilityLibrary = unreal.EditorUtilityLibrary

def main(json_path):
    print("=== JSON to Material Instance (Direct) ===")
    
    # Get the selected asset from Content Browser
    selected_assets = EditorUtilityLibrary.get_selected_assets()
    if not selected_assets:
        unreal.log_error("No asset selected in the Content Browser.")
        return
        
    mi_asset = selected_assets[0]
    if not isinstance(mi_asset, unreal.MaterialInstanceConstant):
        unreal.log_error(f"Selected asset '{mi_asset.get_name()}' is not a Material Instance Constant.")
        return

    print(f"Applying JSON properties directly to: {mi_asset.get_name()}")

    # Load JSON file
    with open(json_path.file_path, "r") as fp:
        temp_buffer = json.load(fp)[0]
        if "Properties" in temp_buffer:
            data = temp_buffer["Properties"]
        else:
            print("Warning: JSON file has no properties to populate")
            data = {}

    # Apply properties to the selected Material Instance asset
    apply(mi_asset, data)

    # Save asset
    unreal.EditorAssetLibrary.save_loaded_asset(mi_asset, False)
    print("Successfully populated and saved Material Instance.")
