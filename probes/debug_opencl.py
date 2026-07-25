"""Investigate OpenCL COP node parameters in Houdini 21."""
import hou

# Clean up
img = hou.node("/img")
for name in ["_debug_copnet", "_pip2930_probe_copnet"]:
    existing = hou.node(f"/img/{name}")
    if existing:
        existing.destroy()

# Create copnet and opencl node
copnet = img.createNode("copnet", node_name="_debug_copnet")
constant = copnet.createNode("constant", node_name="_debug_constant")
null_node = copnet.createNode("null", node_name="_debug_null")
null_node.setInput(0, constant, 0)

# Create OpenCL node
try:
    ocl = copnet.createNode("opencl", node_name="_debug_opencl")
    print(f"OpenCL node: {ocl.path()}, type={ocl.type().name()}, category={ocl.type().category().name()}")
    print(f"Parms ({len(ocl.parms())}):")
    for p in ocl.parms():
        print(f"  {p.name()} = {p.eval()}  [type={p.parmTemplate().type()}]")
except Exception as e:
    print(f"FAIL opencl create: {e}")

# Cook constant -> null
try:
    layer = null_node.layer()
    print(f"\nCook success: resolution={layer.resolution()}")
except Exception as e:
    print(f"Cook fail: {e}")
