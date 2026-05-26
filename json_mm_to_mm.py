import importlib
import unreal
import json

# Local modules
import MaterialExpressions
import materialutil
importlib.reload(MaterialExpressions)
importlib.reload(materialutil)
from materialutil import connectNodesUntilSingle
from utils import try_create_asset

AssetTools = unreal.AssetToolsHelpers.get_asset_tools()
MEL = unreal.MaterialEditingLibrary
EditorAssetLibrary = unreal.EditorAssetLibrary
EditorUtilityLibrary = unreal.EditorUtilityLibrary

mat = EditorUtilityLibrary.get_selected_assets()[0]

Y_GAP = 175

def create_node(ty, yPos, name, defaultValue, slot_name):
    node = MEL.create_material_expression(mat, ty, 0, yPos * Y_GAP)
    node.set_editor_property("ParameterName", name)
    if defaultValue is not None:
        node.set_editor_property(slot_name, defaultValue)
    return node


def generateInputNodes(data: dict):
    """
    Generates the input nodes for Scalar, Vector, Texture, and Switch parameters.
    """
    all_final_nodes = []

    # ----- SCALAR parameters -----
    for p in data.get("ScalarParameterValues", []):
        scalar_node = create_node(
            MaterialExpressions.ScalarParameter, 
            len(all_final_nodes), 
            p["ParameterInfo"]["Name"], 
            p["ParameterValue"], 
            "DefaultValue"
        )
        all_final_nodes.append(scalar_node)

    # ----- VECTOR parameters -----
    for p in data.get("VectorParameterValues", []):
        color_val = unreal.LinearColor(
            p["ParameterValue"]["R"], 
            p["ParameterValue"]["G"], 
            p["ParameterValue"]["B"], 
            p["ParameterValue"]["A"]
        )
        vector_node = create_node(
            MaterialExpressions.VectorParameter, 
            len(all_final_nodes), 
            p["ParameterInfo"]["Name"], 
            color_val, 
            "DefaultValue"
        )
        all_final_nodes.append(vector_node)

    # ----- TEXTURE parameters -----
    for p in data.get("TextureParameterValues", []):
        if p["ParameterValue"] is None:
            continue
        obj_type, obj_name = p["ParameterValue"]["ObjectName"].split("'")[:2]
        obj_path = p["ParameterValue"]["ObjectPath"]
        full_path = obj_path.split(".")[0] + "." + obj_name

        # Attempt to load the texture
        asset = unreal.load_asset(f"{obj_type}'{full_path}'")
        if asset is None:
            # Try to create asset if missing
            folder = "/".join(obj_path.split(".")[0].split("/")[:-1])
            asset = try_create_asset(folder, obj_name, obj_type)
            if asset is not None:
                unreal.EditorAssetLibrary.save_loaded_asset(asset, False)

        # Create node
        node = create_node(
            MaterialExpressions.TextureSampleParameter2D,
            len(all_final_nodes),
            p["ParameterInfo"]["Name"],
            asset,
            "Texture"
        )
        node.set_editor_property("SamplerSource", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
        all_final_nodes.append(node)

    # ----- SWITCH parameters -----
    for i, switch_value in enumerate(data.get("StaticSwitchValues", [])):
        switch_name = data["SwitchParameterNames"][i] if i < len(data["SwitchParameterNames"]) else f"SwitchParam_{i}"
        switch_node = MEL.create_material_expression(mat, MaterialExpressions.StaticSwitchParameter, 0, len(all_final_nodes) * Y_GAP)
        switch_node.set_editor_property("ParameterName", switch_name)
        switch_node.set_editor_property("DefaultValue", switch_value)
        all_final_nodes.append(switch_node)

    return all_final_nodes


def convert_material_json_to_instance_data(full_json: dict) -> dict:
    """
    Converts  large Material JSON structure into a mock "Material Instance" data dictionary 
    
    This approach is simplified. We:
      - Pair the earliest ParameterInfoSet entries with ScalarValues.
      - Then pair next entries with VectorValues.
      - Assign textures from TextureValues as "TextureParam_0", "TextureParam_1", etc.
      - Add switch parameters from StaticSwitchValues and RuntimeEntries[7].
    """

    # Grab "CachedExpressionData" from your JSON
    cached_data = full_json.get("CachedExpressionData", {})
    scalar_param_info = cached_data.get("RuntimeEntries", {}).get("ParameterInfoSet", [])
    vector_param_info = cached_data.get("RuntimeEntries[1]", {}).get("ParameterInfoSet", [])
    texture_param_info = cached_data.get("RuntimeEntries[3]", {}).get("ParameterInfoSet", [])
    switch_param_info = cached_data.get("RuntimeEntries[7]", {}).get("ParameterInfoSet", [])

    # All the scalar & vector arrays
    scalar_values = cached_data.get("ScalarValues", [])
    vector_values = cached_data.get("VectorValues", [])
    texture_values = cached_data.get("TextureValues", [])
    static_switch_values = cached_data.get("StaticSwitchValues", [])

    # Prepare the final structure
    instance_data = {
        "ScalarParameterValues": [],
        "VectorParameterValues": [],
        "TextureParameterValues": [],
        "StaticSwitchValues": static_switch_values,
        "SwitchParameterNames": [switch["Name"] for switch in switch_param_info]  # Extract names of switches
    }

    # Map Scalar Values
    for i, value in enumerate(scalar_values):
        param_name = scalar_param_info[i].get("Name", f"ScalarParam_{i}") if i < len(scalar_param_info) else f"ScalarParam_{i}"
        instance_data["ScalarParameterValues"].append({
            "ParameterInfo": {"Name": param_name},
            "ParameterValue": value
        })

    # Map Vector Values
    for i, value in enumerate(vector_values):
        param_name = vector_param_info[i].get("Name", f"VectorParam_{i}") if i < len(vector_param_info) else f"VectorParam_{i}"
        instance_data["VectorParameterValues"].append({
            "ParameterInfo": {"Name": param_name},
            "ParameterValue": {
                "R": value["R"], 
                "G": value["G"], 
                "B": value["B"], 
                "A": value["A"]
            }
        })

    # Map Texture Values
    for i, tex in enumerate(texture_values):
        asset_path_name = tex.get("AssetPathName", "")
        if not asset_path_name:
            continue
        obj_name = asset_path_name.split("/")[-1].split(".")[0]
        param_name = texture_param_info[i].get("Name", f"TextureParam_{i}") if i < len(texture_param_info) else f"TextureParam_{i}"
        instance_data["TextureParameterValues"].append({
            "ParameterInfo": {"Name": param_name},
            "ParameterValue": {
                "ObjectName": f"Texture2D'{obj_name}'",
                "ObjectPath": asset_path_name
            }
        })

    return instance_data


def main(json_path):
    print("=== JSON Full Material → Dummy Master Material ===")

    # 1) Read the big Material JSON
    with open(json_path.file_path, "r", encoding="utf-8") as fp:
        # It's an array, so we take the first element
        full_material_data = json.load(fp)[0]

    # 2) Convert that big JSON to the instance-like format
    instance_data = convert_material_json_to_instance_data(full_material_data)

    # 3) Clear out existing nodes
    MEL.delete_all_material_expressions(mat)

    # 4) Generate new param nodes
    nodes = generateInputNodes(instance_data)

    # 5) Hook them up to Base Color as an example
    final_node = connectNodesUntilSingle(mat, nodes)
    MEL.connect_material_property(final_node, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # 6) Save
    unreal.EditorAssetLibrary.save_loaded_asset(mat, True)
    print("Done! Created parameter nodes from the full Material JSON.")
