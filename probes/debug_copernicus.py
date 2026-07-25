"""Investigate Copernicus node types in Houdini 21."""
import hou

# First: list all node type categories
print("=== Node Type Categories ===")
for name in sorted(hou.nodeTypeCategories().keys()):
    cat = hou.nodeTypeCategories()[name]
    print(f"  {name}: {cat.name()}")

# Check if there's a Copernicus-specific category
print("\n=== Searching for Copernicus ===")
for cat_name in sorted(hou.nodeTypeCategories().keys()):
    cat = hou.nodeTypeCategories()[cat_name]
    for type_name in sorted(cat.nodeTypes().keys()):
        if "copernicus" in type_name.lower() or "cop" == type_name.lower()[:3]:
            print(f"  [{cat_name}] {type_name}")

# Check what contexts are available
print("\n=== Available contexts ===")
for ctx_name in ["/img", "/cop2", "/cop", "/obj", "/mat", "/out", "/shop", "/stage", "/tasks", "/ch", "/vex"]:
    try:
        node = hou.node(ctx_name)
        if node:
            print(f"  {ctx_name}: valid, type={node.type().name()}")
        else:
            print(f"  {ctx_name}: None")
    except Exception as e:
        print(f"  {ctx_name}: error={e}")

# Try creating a COP network in /img
print("\n=== Trying to create COP network in /img ===")
img = hou.node("/img")
if img:
    print(f"  /img type: {img.type().name()}")
    print(f"  /img children: {[c.name() for c in img.children()]}")

    # Check what node types can be created in /img
    cop2_cat = hou.nodeTypeCategories().get("Cop2")
    all_cop2_types = sorted(cop2_cat.nodeTypes().keys()) if cop2_cat else []

    # Filter for net-like types
    net_like = [t for t in all_cop2_types if "net" in t.lower()]
    print(f"  Net-like types in Cop2: {net_like}")

    # Try creating cop2net
    try:
        net = img.createNode("cop2net", node_name="_debug_cop2net")
        print(f"  Created cop2net: {net.path()}")
        # Check children of the net
        child_types = sorted(hou.nodeTypeCategories().get("Cop2").nodeTypes().keys())
        copernicus_like = [t for t in child_types if "cop" in t.lower() and "cop2" not in t.lower()]
        print(f"  Possible Copernicus nodes: {copernicus_like[:30]}")
        net.destroy()
    except Exception as e:
        print(f"  Failed to create cop2net: {e}")
