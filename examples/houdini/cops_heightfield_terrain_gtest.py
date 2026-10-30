"""COPS heightfield terrain ground test for a live Houdini host.

"COPS heightfields" = Houdini Copernicus heightfield layer operators
(``monotoheightfield`` / ``heightfield_erode`` / ``heightfield_terrace`` ...).
This script builds a Copernicus COP network that turns procedural noise into a
real heightfield volume (terrain), applies erosion and terracing, cooks it,
reads back the voxels to prove the terrain is non-flat, then renders two PNG
previews through ``rop_image`` outputs: a grayscale heightmap and a normal
map. The scene is saved as a ``.hip`` file.

Run inside Houdini (``hython`` / ``hou``) or through the adapter's
``houdini_scripting__execute_python`` MCP tool. The module lives under
``examples/houdini`` (not shipped in the wheel), so add that directory to
``sys.path`` and choose an output directory::

    import os
    import sys
    sys.path.insert(0, "/path/to/repo/examples/houdini")
    import cops_heightfield_terrain_gtest as gtest

    OUTPUT_DIR = "/path/to/evidence"
    result = gtest.run_terrain_gtest(OUTPUT_DIR)

The script uses only the Python standard library plus Houdini's own ``hou``;
it stays within Python 3.7 grammar so it can run on legacy embedded hosts. The
evidence dict is also printed as ``TERRAIN_GTEST=<json>`` on stdout when run as
``__main__`` for easy collection.
"""

from __future__ import annotations

import json
import os

# Ordered COPS heightfield terrain recipe. Each step is wired into the
# previous, forming the natural noise -> mono -> heightfield -> erosion ->
# terrace authoring chain used for procedural terrain in Copernicus.
# ``heightfield_erode`` requires Houdini 22.0 or newer.
CHAIN = (
    ("fractalnoise", "noise_src"),
    ("mono", "to_mono"),
    ("monotoheightfield", "to_heightfield"),
    ("heightfield_erode", "hf_erode"),
    ("heightfield_terrace", "hf_terrace"),
)

# Required heightfield stages: each must cook cleanly and read back non-flat
# voxels before the whole terrain chain is reported as PASS.
TERRAIN_STAGES = ("to_heightfield", "hf_erode", "hf_terrace")

# Heightfield visualization branches, each ending in a Copernicus ROP image.
BRANCHES = (
    # (leaf heightfield node, view node type, view node name, rop name, png name)
    ("hf_terrace", "heightfieldtomono", "hf_to_height", "rop_height", "cops_heightfield_terrain_height.png"),
    ("hf_terrace", "heighttonormal", "hf_to_normal", "rop_normal", "cops_heightfield_terrain_normal.png"),
)

SAMPLE_LIMIT = 200000


def _cook_reports(node):
    """Cook one node; return a compact, honest diagnostics dict."""
    report = {"path": node.path(), "type": node.type().name()}
    try:
        node.cook(force=True)
        report["cook_ok"] = True
    except Exception as exc:  # noqa: BLE001 - host cook errors are the evidence
        report["cook_ok"] = False
        report["cook_error"] = str(exc)[:300]
    try:
        report["errors"] = [str(e)[:200] for e in node.errors()][:3]
        report["warnings"] = [str(w)[:200] for w in node.warnings()][:3]
    except Exception as exc:  # noqa: BLE001
        report["diag_error"] = str(exc)[:150]
    return report


def _voxel_sample(node):
    """Return a bounded float sample of the first Volume primitive, or None."""
    try:
        geo = node.geometry()
    except Exception:
        return None
    if geo is None:
        return None
    for prim in geo.prims():
        if "Volume" in prim.type().name():
            try:
                return [float(v) for v in list(prim.allVoxels())[:SAMPLE_LIMIT]]
            except Exception:  # noqa: BLE001
                return None
    return None


def _voxel_stats(sample, total_count):
    """Summarize a voxel sample; ``total_count`` is the full primitive length."""
    if not sample:
        return {"type": "Volume", "count": 0}
    return {
        "type": "Volume",
        "count": total_count,
        "min": min(sample),
        "max": max(sample),
        "distinct": len({round(v, 4) for v in sample}),
    }


def _digest(sample):
    """Cheap comparable signature so consecutive operator stages can be compared."""
    if not sample:
        return None
    return {
        "count": len(sample),
        "distinct": len({round(v, 4) for v in sample}),
        "rounded_sum": round(sum(sample), 2),
        "min": round(min(sample), 4),
        "max": round(max(sample), 4),
    }


def _bbox(geo):
    try:
        box = geo.boundingBox()
        return {"min": list(box.minvec()), "max": list(box.maxvec())}
    except Exception:
        return None


def _render_branch(rop, output_dir, png_name):
    """Render a rop_image output and verify a PNG produced by THIS run.

    Any pre-existing artifact is removed first, so a file found afterwards must
    have been written by this render call rather than left over from an earlier
    run in a reused output directory.
    """
    png = os.path.join(output_dir, png_name)
    result = {"path": png}
    try:
        if os.path.isfile(png):
            os.remove(png)
    except OSError as exc:  # noqa: BLE001
        result["stale_remove_error"] = str(exc)[:200]
    parm_set = None
    for pname in ("copoutput", "filename", "vm_picture", "picture"):
        parm = rop.parm(pname)
        if parm is not None:
            try:
                parm.set(png)
                parm_set = pname
                break
            except Exception:
                continue
    result["output_param"] = parm_set
    try:
        rop.render()
        result["render_called"] = True
    except Exception as exc:  # noqa: BLE001
        result["render_called"] = False
        result["render_error"] = str(exc)[:200]
    result["png_exists"] = os.path.isfile(png)
    result["png_bytes"] = os.path.getsize(png) if os.path.isfile(png) else 0
    result["fresh"] = bool(result.get("render_called") and result["png_exists"] and result["png_bytes"] > 0)
    return result


def run_terrain_gtest(output_dir):
    """Build, cook and verify a COPS heightfield terrain; return evidence dict."""
    import hou

    evidence = {
        "host": {
            "houdini": hou.applicationVersionString(),
            "python": __import__("sys").version.split()[0],
        },
        "chain": [step[0] for step in CHAIN],
        "required_stages": list(TERRAIN_STAGES),
        "output_dir": os.path.abspath(output_dir),
    }
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as exc:
        evidence["output_dir_error"] = str(exc)[:200]

    # List the Copernicus heightfield node types actually present on the host.
    try:
        cop_types = sorted(hou.nodeTypeCategories().get("Cop").nodeTypes().keys())
        evidence["cop_heightfield_types"] = [t for t in cop_types if "heightfield" in t.lower()]
        evidence["cop_node_type_count"] = len(cop_types)
    except Exception as exc:  # noqa: BLE001
        evidence["cop_probe_error"] = str(exc)[:200]

    obj = hou.node("/obj")
    geo = obj.node("cops_hf_terrain")
    if geo is None:
        geo = obj.createNode("geo", "cops_hf_terrain")
    for child in list(geo.children()):
        child.destroy()
    evidence["geo"] = geo.path()

    copnet = geo.createNode("copnet", "copnet_terrain")
    evidence["copnet"] = copnet.path()

    # Author the COPS heightfield terrain chain, honoring the host's real
    # node-type catalogue. A missing type is recorded rather than faked.
    named = {}
    previous = None
    created = []
    for node_type, name in CHAIN:
        try:
            node = copnet.createNode(node_type, name)
        except Exception as exc:  # noqa: BLE001
            evidence.setdefault("missing_nodes", []).append({"type": node_type, "error": str(exc)[:200]})
            continue
        if previous is not None:
            try:
                node.setInput(0, previous)
            except Exception as exc:  # noqa: BLE001
                evidence.setdefault("wire_errors", []).append({"type": node_type, "error": str(exc)[:200]})
        previous = node
        named[name] = node
        created.append(node)

    # Author visualization branches off the named heightfield leaf.
    renders = {}
    for leaf_name, view_type, view_name, rop_name, png_name in BRANCHES:
        leaf = named.get(leaf_name)
        if leaf is None:
            evidence.setdefault("missing_branches", []).append(leaf_name)
            continue
        try:
            view = copnet.createNode(view_type, view_name)
            view.setInput(0, leaf)
            rop = copnet.createNode("rop_image", rop_name)
            rop.setInput(0, view)
        except Exception as exc:  # noqa: BLE001
            evidence.setdefault("branch_errors", []).append({"leaf": leaf_name, "error": str(exc)[:200]})
            continue
        created.extend((view, rop))
        renders[png_name] = rop
    evidence["created_nodes"] = [n.path() for n in created]

    # Cook every authored node and keep the per-node diagnostics.
    cooks = [_cook_reports(node) for node in created]
    evidence["cooks"] = cooks
    cook_by_path = {c["path"]: c for c in cooks}

    # Read back heightfield voxels from the volume-producing stages. The sample
    # is also used to compare consecutive operators for measurable changes.
    voxel_sources = {}
    samples = {}
    for stage in TERRAIN_STAGES:
        node = named.get(stage)
        if node is None:
            continue
        sample = _voxel_sample(node)
        if sample is None:
            continue
        total = len(sample)
        try:
            for prim in node.geometry().prims():
                if "Volume" in prim.type().name():
                    total = len(prim.allVoxels())
                    break
        except Exception:  # noqa: BLE001
            total = len(sample)
        voxel_sources[stage] = [_voxel_stats(sample, total)]
        samples[stage] = sample
    evidence["heightfield_voxels"] = voxel_sources

    # Bounding box of an explicit heightfield node, not merely the first node
    # that happens to expose geometry (a 2D noise layer has a near-zero Z span).
    bbox_node = named.get("hf_terrace") or named.get("to_heightfield")
    if bbox_node is not None:
        try:
            g = bbox_node.geometry()
        except Exception:
            g = None
        if g is not None:
            evidence["terrain_bbox"] = _bbox(g)
            evidence["terrain_bbox_node"] = bbox_node.path()

    # Compare consecutive stage digests so the doc can claim only changes that
    # are actually measured (erosion vs terracing may be a no-op at defaults).
    signatures = {stage: _digest(sample) for stage, sample in samples.items()}
    evidence["stage_signatures"] = signatures
    stage_deltas = {}
    for earlier, later in (("to_heightfield", "hf_erode"), ("hf_erode", "hf_terrace")):
        a, b = signatures.get(earlier), signatures.get(later)
        stage_deltas["{}__to__{}".format(earlier, later)] = {
            "changed": bool(a and b and a != b),
            "before": a,
            "after": b,
        }
    evidence["stage_deltas"] = stage_deltas

    # Decide PASS only when every required stage cooked cleanly (no errors) and
    # read back real, non-flat heightfield voxels.
    stage_status = {}
    for stage in TERRAIN_STAGES:
        node = named.get(stage)
        report = cook_by_path.get(node.path(), {}) if node is not None else {}
        sig = signatures.get(stage)
        cooked_clean = bool(report.get("cook_ok")) and not report.get("errors")
        non_flat = bool(sig and sig["count"] > 0 and sig["distinct"] > 1)
        stage_status[stage] = {"cooked_clean": cooked_clean, "non_flat": non_flat}
    evidence["terrain_stages"] = stage_status
    evidence["terrain_cook_pass"] = all(value["cooked_clean"] and value["non_flat"] for value in stage_status.values())

    # Render the heightmap and normal-map previews and verify BOTH configured
    # branches produced a fresh, non-empty PNG during this run.
    evidence["renders"] = {}
    for png_name, rop in renders.items():
        evidence["renders"][png_name] = _render_branch(rop, evidence["output_dir"], png_name)
    expected = {branch[4] for branch in BRANCHES}
    evidence["render_pass"] = set(evidence["renders"]) == expected and all(
        r.get("fresh") for r in evidence["renders"].values()
    )

    # Persist the scene as a reproducible .hip artifact.
    hip = os.path.join(evidence["output_dir"], "cops_heightfield_terrain.hip")
    try:
        hou.hipFile.save(hip)
        evidence["hip"] = {"path": hip, "bytes": os.path.getsize(hip), "saved": True}
    except Exception as exc:  # noqa: BLE001
        evidence["hip"] = {"path": hip, "saved": False, "error": str(exc)[:200]}

    return evidence


def main():
    out_dir = os.environ.get(
        "COPS_TERRAIN_OUT",
        os.path.join(os.path.expanduser("~"), "cops_hf_terrain"),
    )
    print("TERRAIN_GTEST=" + json.dumps(run_terrain_gtest(out_dir)))


if __name__ == "__main__":
    main()
