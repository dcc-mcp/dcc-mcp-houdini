"""Debug Copernicus node type names in Houdini 21."""
import hou

# Find Copernicus node type
cop2_cat = hou.nodeTypeCategories().get("Cop2")
if cop2_cat:
    types = cop2_cat.nodeTypes()
    # Check copnet specifically
    print("copnet exists:", "copnet" in types)
    print("cop2net exists:", "cop2net" in types)

    # Print all net-related types
    for name in sorted(types.keys()):
        if "cop" in name.lower() or "net" in name.lower():
            print(f"  {name} -> {types[name].description()}")

    # Print first 30 types if copnet not found
    if "copnet" not in types:
        print("\nFirst 30 types in Cop2:")
        for name in sorted(list(types.keys()))[:30]:
            print(f"  {name}")
else:
    print("Cop2 category not found")
    for cat_name in sorted(hou.nodeTypeCategories().keys()):
        print(f"  Category: {cat_name}")
