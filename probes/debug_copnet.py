"""Investigate CopNet (Copernicus) node types in Houdini 21."""
import hou

# CopNet category has copnet (network type)
copnet_cat = hou.nodeTypeCategories().get("CopNet")
cop_cat = hou.nodeTypeCategories().get("Cop")

print("=== CopNet (network) types ===")
if copnet_cat:
    for name in sorted(copnet_cat.nodeTypes().keys()):
        print(f"  {name}")

print("\n=== Cop (operator) types ===")
if cop_cat:
    for name in sorted(cop_cat.nodeTypes().keys()):
        print(f"  {name}")

# Try creating copnet in /img
print("\n=== Creating Copernicus network ===")
img = hou.node("/img")

# Clean up previous probe attempts
for child_name in ["_pip2930_probe_copnet", "_debug_copnet"]:
    existing = hou.node(f"/img/{child_name}")
    if existing:
        existing.destroy()
        print(f"  Destroyed {child_name}")

try:
    copnet = img.createNode("copnet", node_name="_debug_copnet")
    print(f"  Created copnet: {copnet.path()}, type={copnet.type().name()}, category={copnet.type().category().name()}")

    # Try creating nodes inside
    tests = [
        ("gradient", "gradient"),
        ("constant", "constant"),
        ("noise", "noise"),
        ("blur", "blur"),
        ("null", "null"),
    ]
    for node_type, label in tests:
        try:
            n = copnet.createNode(node_type, node_name=f"_debug_{label}")
            print(f"  Created {label}: {n.path()}")
        except Exception as e:
            print(f"  FAIL {label}: {e}")

    # Check what methods are available on a CopNet node
    null_node = copnet.node("_debug_null") if copnet.node("_debug_null") else None
    if null_node:
        print(f"\n  null_node type: {null_node.type().name()}, category: {null_node.type().category().name()}")
        print(f"  hasattr layer: {hasattr(null_node, 'layer')}")
        print(f"  hasattr geometry: {hasattr(null_node, 'geometry')}")
        print(f"  hasattr cable: {hasattr(null_node, 'cable')}")
        print(f"  hasattr vdb: {hasattr(null_node, 'vdb')}")

    # Check hou.CopNode class
    print(f"\n  hou.CopNode exists: {hasattr(hou, 'CopNode')}")
    if hasattr(hou, 'CopNode'):
        print(f"  hou.CopNode methods: {[m for m in dir(hou.CopNode) if not m.startswith('_')]}")

    copnet.destroy()
except Exception as e:
    print(f"  FAIL copnet create: {e}")
