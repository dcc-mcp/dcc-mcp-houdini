"""Licensed-Houdini cook regression for the character-animation workflow.

Run under ``hython`` (no pytest / no dcc_mcp_core wheel required):

    hython run_houdini_kinefx_cook_acceptance.py <output_dir>

Exercises the REAL scene tools against a live KineFX skeleton (non-mock):
  * configure_biped_retarget success path + whole-chain cook (QA blocking 1)
  * build_ragdoll success path + dopnet cook (QA blocking 2)
  * build_retarget_motion_mixer graceful degradation on hosts older than H22

Writes a compact JSON evidence file and exits non-zero on any failed check.
Mock-hou unit tests cannot catch standalone-cook failures; this script runs the
actual hou.OperationFailed-prone nodes on a licensed host (verified on
22.0.368 / 21.0.440 / 20.5.550).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
import types
from pathlib import Path

import hou

ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = ROOT / "src" / "dcc_mcp_houdini" / "skills" / "houdini-kinefx" / "scripts"
sys.path.insert(0, str(ROOT / "tests"))
from skill_loader import skill_script_import_context  # noqa: E402

# --- pure-python result-envelope shim -------------------------------------
# Bare hython has no dcc_mcp_core wheel installed. Provide the minimal helper
# contract the skill scripts import, so the real scene logic (and real hou
# cooking) can be exercised without the wheel. Runtime scaffolding only.
if "dcc_mcp_core" not in sys.modules:
    core = types.ModuleType("dcc_mcp_core")
    core.__path__ = []  # mark as package
    sys.modules["dcc_mcp_core"] = core
if "dcc_mcp_core.skill" not in sys.modules:
    _skill = types.ModuleType("dcc_mcp_core.skill")

    def _entry(fn):
        return fn

    def _success(message, **context):
        return {"success": True, "message": message, "error": None, "context": context}

    def _error(message, error, **context):
        return {"success": False, "message": message, "error": error, "context": context}

    def _exception(exc, message="Operation failed"):
        return {"success": False, "message": message, "error": type(exc).__name__, "context": {"detail": str(exc)}}

    def _run_main(main):
        return main()

    _skill.skill_entry = _entry
    _skill.skill_success = _success
    _skill.skill_error = _error
    _skill.skill_exception = _exception
    _skill.run_main = _run_main
    sys.modules["dcc_mcp_core.skill"] = _skill
    sys.modules["dcc_mcp_core"].skill = _skill


def _load(script_name):
    path = _SCRIPTS / script_name
    spec = importlib.util.spec_from_file_location("cookacc_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _make_skeleton(container, name, with_mapping=False):
    skel = container.createNode("kinefx::skeleton", node_name=name)
    geo = hou.Geometry()
    positions = [(0, 0, 0), (0, 0.9, 0), (0, 1.2, 0), (-0.1, 1.2, 0), (0.1, 1.2, 0)]
    pts = geo.createPoints(positions)
    name_attr = geo.addAttrib(hou.attribType.Point, "name", "")
    for i, p in enumerate(pts):
        p.setAttribValue(name_attr, "joint_{}".format(i))
    if with_mapping:
        map_attr = geo.addAttrib(hou.attribType.Point, "retarget_joint", "")
        for i, p in enumerate(pts):
            p.setAttribValue(map_attr, "joint_{}".format(i))
    stash = skel.parm("stash")
    if stash is not None:
        stash.set(geo)
    return skel


def _cook_report(nodes):
    """Force-cook each node, returning (path, ok, errors, warnings)."""
    rows = []
    for node in nodes:
        try:
            node.cook(force=True)
            errs = [str(e) for e in node.errors()]
            warns = [str(w) for w in node.warnings()]
            rows.append({"path": node.path(), "cook_ok": True, "errors": errs, "warnings": warns})
        except Exception as exc:  # noqa: BLE001
            rows.append({"path": node.path(), "cook_ok": False, "errors": [str(exc)], "warnings": []})
    return rows


def check_configure_biped_retarget(retarget):
    obj = hou.node("/obj")
    geo = obj.createNode("geo", node_name="cookacc_retarget_geo")
    try:
        target = _make_skeleton(geo, "target_biped")
        source = _make_skeleton(geo, "source_mocap", with_mapping=True)
        result = retarget.configure_biped_retarget(
            geo.path(),
            target.path(),
            source.path(),
            source_convention="mixamo",
            target_convention="kinefx",
        )
        checks = {
            "success": result["success"] is True,
            "validated": result["context"].get("validated") is True,
            "cook_failures_empty": result["context"].get("cook_failures") == [],
            "mapping_attribute_verified": result["context"].get("mapping_attribute_verified") is True,
            "has_sop_output": bool(result["context"].get("sop_output")),
        }
        # Whole-chain cook verification: the created nodes must all force-cook
        # cleanly on the licensed host (this is what mock-hou tests cannot do).
        created = [hou.node(p) for p in result["context"].get("created_nodes", []) if hou.node(p)]
        rows = _cook_report(created)
        checks["all_created_nodes_cook"] = bool(rows) and all(r["cook_ok"] and not r["errors"] for r in rows)
        # Explicitly verify the 2-input mappoints node is fully wired.
        target_map = next((n for n in created if n and "target_map" in n.name()), None)
        checks["target_map_has_second_input"] = bool(target_map and target_map.input(1) is not None)
        return {
            "checks": checks,
            "cook_rows": rows,
            "result_success": result["success"],
            "result_error": result.get("error"),
        }
    finally:
        pass


def check_build_ragdoll(ragdoll):
    obj = hou.node("/obj")
    geo = obj.createNode("geo", node_name="cookacc_ragdoll_geo")
    try:
        skel = _make_skeleton(geo, "biped")
        result = ragdoll.build_ragdoll(
            geo.path(),
            skel.path(),
            dopnet_path="/obj/cookacc_ragdoll_dopnet",
        )
        checks = {
            "success": result["success"] is True,
            "validated": result["context"].get("validated") is True,
            "cook_failures_empty": result["context"].get("cook_failures") == [],
            "dopnet_wired": bool(result["context"].get("dopnet")),
        }
        dopnet = hou.node(result["context"].get("dopnet", ""))
        dopnet_rows = _cook_report([dopnet] if dopnet else [])
        checks["dopnet_cooks_clean"] = bool(dopnet_rows) and all(r["cook_ok"] and not r["errors"] for r in dopnet_rows)
        return {
            "checks": checks,
            "dopnet_cook_rows": dopnet_rows,
            "result_success": result["success"],
            "result_error": result.get("error"),
        }
    finally:
        pass


def check_motion_mixer_capability(mixer_mod):
    """The H22-only tool must never surface an uncaught node-type/Operation error.

    Hosts differ: 22.x has every Motion Mixer / APEX node type, 21.0.440 also
    has them, 20.5.550 does not. So we accept EITHER a clean success OR a
    structured ``capability_unavailable`` error, but never an uncaught
    ``OperationFailed`` / "Invalid node type name" / generic skill_exception.
    When the tool reports failure it MUST be the structured capability error.
    """
    obj = hou.node("/obj")
    geo = obj.createNode("geo", node_name="cookacc_mixer_geo")
    try:
        target = _make_skeleton(geo, "target_biped")
        s1 = _make_skeleton(geo, "src1", with_mapping=True)
        s2 = _make_skeleton(geo, "src2", with_mapping=True)
        result = mixer_mod.build_retarget_motion_mixer(
            geo.path(),
            target.path(),
            [s1.path(), s2.path()],
        )
        checks = {
            "no_uncaught_operation_failed": result.get("error") != "OperationFailed",
            "no_invalid_node_type": "Invalid node type name" not in str(result),
            "no_generic_exception": result.get("error") not in ("TypeError", "AttributeError", "ValueError"),
        }
        if result["success"] is False:
            # A failure must be the graceful capability degradation, never a
            # raw createNode crash.
            checks["failure_is_structured_capability"] = (
                result.get("error") == "capability_unavailable"
                and result["context"].get("requires_houdini_22") is True
                and bool(result["context"].get("missing_node_type"))
            )
        else:
            checks["clean_success_on_capable_host"] = True
        return {
            "checks": checks,
            "result_success": result["success"],
            "result_error": result.get("error"),
            "missing_node_type": result["context"].get("missing_node_type"),
        }
    finally:
        pass


def main():
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)
    version = hou.applicationVersion()
    is_h22 = version >= (22, 0, 0)
    evidence = {
        "host": {
            "version_string": hou.applicationVersionString(),
            "version": list(version),
            "is_houdini_22_or_newer": is_h22,
        },
        "tests": {},
    }
    try:
        retarget = _load("configure_biped_retarget.py")
        ragdoll = _load("build_ragdoll.py")
        mixer_mod = _load("build_retarget_motion_mixer.py")

        evidence["tests"]["configure_biped_retarget"] = check_configure_biped_retarget(retarget)
        evidence["tests"]["build_ragdoll"] = check_build_ragdoll(ragdoll)
        evidence["tests"]["build_retarget_motion_mixer_capability"] = check_motion_mixer_capability(mixer_mod)

        failed = []
        for name, test in evidence["tests"].items():
            for key, ok in test["checks"].items():
                if not ok:
                    failed.append("{}.{}".format(name, key))
        evidence["verdict"] = "PASS" if not failed else "FAIL"
        evidence["failed_checks"] = failed
    except Exception as exc:  # noqa: BLE001
        evidence["verdict"] = "ERROR"
        evidence["error"] = "{}: {}".format(type(exc).__name__, exc)
        evidence["traceback"] = traceback.format_exc()
    finally:
        # Clean up every cookacc top-level network created by the checks.
        for path in (
            "/obj/cookacc_retarget_geo",
            "/obj/cookacc_ragdoll_geo",
            "/obj/cookacc_ragdoll_dopnet",
            "/obj/cookacc_mixer_geo",
        ):
            n = hou.node(path)
            if n is not None:
                try:
                    n.destroy()
                except Exception:  # noqa: BLE001
                    pass

    out_path = out_dir / "kinefx_cook_acceptance_result.json"
    out_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("KINEFX_COOK_ACCEPTANCE_VERDICT={}".format(evidence["verdict"]))
    print("HOST={}".format(evidence["host"]["version_string"]))
    for name, test in evidence["tests"].items():
        oks = sum(1 for v in test["checks"].values() if v)
        print("  {}: {}/{} checks ok".format(name, oks, len(test["checks"])))
    if evidence.get("failed_checks"):
        print("FAILED_CHECKS={}".format(",".join(evidence["failed_checks"])))
    if evidence.get("error"):
        print("ERROR={}".format(evidence["error"]))
    return 0 if evidence["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
