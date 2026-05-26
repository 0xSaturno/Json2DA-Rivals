import json
import unreal
import importlib
import utils

importlib.reload(utils)
from utils import try_create_asset
from pathlib import Path

def format_asset_refs_recursive(val):
    """Recursively formats {ObjectName, ObjectPath} dictionaries to Type'Path' format for Unreal."""
    if isinstance(val, dict):
        if 'ObjectPath' in val and 'ObjectName' in val:
            obj_name_str = val["ObjectName"]
            obj_path_str = val["ObjectPath"]
            if "'" in obj_name_str:
                obj_type, obj_name = obj_name_str.split("'")[:2]
            else:
                obj_type = "Object"
                obj_name = obj_name_str
            full_path = obj_path_str.split(".")[0] + "." + obj_name
            return f"{obj_type}'{full_path}'"
        else:
            return {k: format_asset_refs_recursive(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [format_asset_refs_recursive(item) for item in val]
    else:
        return val

def fmodel_dt_json_to_ue_dt_json(json_path):
    with open(json_path.file_path, "r") as fp:
        my_dict = json.load(fp)[0]
        
    assert my_dict["Type"] == "DataTable"
    dt_name = my_dict["Name"]
    package_path = my_dict.get("Package", "")
    
    # Resolve the RowStruct path
    row_struct_info = my_dict.get('Properties', {}).get('RowStruct', {})
    row_struct = None
    if row_struct_info:
        obj_name_str = row_struct_info.get('ObjectName', '')
        obj_path_str = row_struct_info.get('ObjectPath', '')
        if "'" in obj_name_str:
            _, struct_name = obj_name_str.split("'")[:2]
        else:
            struct_name = obj_name_str
        base_path = obj_path_str.split('.')[0]
        full_struct_path = f"{base_path}.{struct_name}"
        row_struct = unreal.load_object(None, full_struct_path)

    # Process and format rows recursively
    out_list = []
    for row_name, row_data in my_dict['Rows'].items():
        out_dict = {'Name': row_name}
        for col_name, col_val in row_data.items():
            out_dict[col_name] = format_asset_refs_recursive(col_val)
        out_list.append(out_dict)

    # Write to a temporary file
    temp_json_path = str(Path(json_path.file_path).parent / 'temp_dt_import.json')
    with open(temp_json_path, 'w') as fout:
        json.dump(out_list, fout, indent=2)

    return row_struct, dt_name, package_path, temp_json_path

def main(json_path):
    print("=== JSON to DataTable Importer ===")
    
    # 1. Parse JSON and format rows
    row_struct, dt_name, package_path, temp_json = fmodel_dt_json_to_ue_dt_json(json_path)
    
    if not row_struct:
        unreal.log_error("Could not resolve or load RowStruct for the DataTable.")
        return

    # Determine asset destination path from package path in JSON
    # e.g., "/Game/Marvel/UI/Blueprints/Battle/RichText_KillTable_BP"
    dest_dir = '/'.join(package_path.split('/')[:-1])
    if not dest_dir:
        # Fallback to selected assets' directory if package path is missing
        sel_assets = unreal.EditorUtilityLibrary.get_selected_assets()
        if sel_assets:
            dest_dir = '/'.join(sel_assets[0].get_path_name().split('/')[:-1])
        else:
            dest_dir = "/Game/Marvel/UI/Blueprints/Battle"

    full_asset_path = f"{dest_dir}/{dt_name}"
    print(f"Target DataTable Asset: {full_asset_path}")

    # 2. Check if asset exists; if not, create it using factory
    if unreal.EditorAssetLibrary.does_asset_exist(full_asset_path):
        asset = unreal.load_asset(full_asset_path)
    else:
        print(f"Creating new DataTable with RowStruct: {row_struct.get_name()}")
        factory = unreal.DataTableFactory()
        factory.struct = row_struct
        asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
        asset = asset_tools.create_asset(dt_name, dest_dir, unreal.DataTable, factory)

    if not asset:
        unreal.log_error(f"Failed to load or create DataTable at {full_asset_path}")
        return

    # 3. Populate rows from JSON
    success = unreal.DataTableFunctionLibrary.fill_data_table_from_json_file(asset, temp_json)
    if success:
        print("Successfully filled DataTable rows.")
    else:
        unreal.log_error("Failed to populate DataTable rows from temp JSON.")

    # 4. Save and cleanup
    unreal.EditorAssetLibrary.save_loaded_asset(asset, False)
    Path(temp_json).unlink(missing_ok=True)
    print("DataTable successfully saved.")