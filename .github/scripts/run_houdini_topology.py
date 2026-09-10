"""Licensed real-HOM smoke; creates only transient geometry in fresh Hython."""

import importlib.util
import json
import sys
from pathlib import Path

import hou

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root / "tests"))
from skill_loader import skill_script_import_context  # noqa: E402

import dcc_mcp_houdini  # noqa: E402

assert root in Path(dcc_mcp_houdini.__file__).resolve().parents
script = root / "src/dcc_mcp_houdini/skills/houdini-geometry/scripts/get_primitive_topology.py"
spec = importlib.util.spec_from_file_location("live_primitive_topology", script)
module = importlib.util.module_from_spec(spec)
with skill_script_import_context(spec):
    spec.loader.exec_module(module)
container = hou.node("/obj").createNode("geo", "topology_probe")
box = container.createNode("box")
result = module.get_primitive_topology(box.path(), offset=1, limit=2, vertex_limit=3)
assert result["success"], result
data = result["context"]
assert data["total_count"] == 6 and data["next_offset"] == 3
geo = box.geometry()
for row in data["primitives"]:
    primitive = geo.prim(row["primitive_index"])
    assert row["point_indices"] == [v.point().number() for v in primitive.vertices()][:3]
    assert row["closed"] and row["vertices_truncated"] and row["vertex_count"] == 4
print(
    json.dumps(
        {
            "houdini": hou.applicationVersionString(),
            "result": data,
            "vertices_type": type(geo.prim(0).vertices()).__name__,
        }
    ),
    flush=True,
)
container.destroy()
print("HOUDINI_TOPOLOGY_PROBE_PASSED", flush=True)
