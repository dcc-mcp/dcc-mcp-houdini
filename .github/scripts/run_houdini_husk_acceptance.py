"""Reproduce issue 238 with real hair procedural errors and a partial EXR.

Run in a fresh licensed hython with this checkout installed. Temporary USD,
EXR and durable job records are retained for inspection. No UI scene is used.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

import hou
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdRender

import dcc_mcp_houdini

ROOT = Path(__file__).resolve().parents[2]
assert ROOT in Path(dcc_mcp_houdini.__file__).resolve().parents, "Install this checkout first"
sys.path.insert(0, str(ROOT / "tests"))
from skill_loader import skill_script_import_context  # noqa: E402


def _load(name):
    path = ROOT / "src/dcc_mcp_houdini/skills/houdini-husk/scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return getattr(module, name)


def _scene(directory):
    source = directory / "source.usda"
    stage = Usd.Stage.CreateNew(str(source))
    skin = UsdGeom.Mesh.Define(stage, "/World/skin")
    points = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]
    skin.CreatePointsAttr(points)
    skin.CreateFaceVertexCountsAttr([4])
    skin.CreateFaceVertexIndicesAttr([0, 1, 2, 3])
    UsdGeom.PrimvarsAPI(skin).CreatePrimvar("rest", Sdf.ValueTypeNames.Point3fArray, "vertex").Set(points)
    guides = UsdGeom.BasisCurves.Define(stage, "/World/guides")
    guides.CreateTypeAttr("linear")
    guides.CreateCurveVertexCountsAttr([2])
    guides.CreatePointsAttr([(0, 0, 0), (0, 0, 1)])
    guides.CreateWidthsAttr([0.01, 0.01])
    # Deliberately omit skinprim/pscale to make the procedural fail during Husk.
    UsdGeom.PrimvarsAPI(guides).CreatePrimvar("rest", Sdf.ValueTypeNames.Point3fArray, "vertex").Set(
        [(0, 0, 0), (0, 0, 1)]
    )
    camera = UsdGeom.Camera.Define(stage, "/World/camera")
    camera.AddTranslateOp().Set(Gf.Vec3d(0, 0, 5))
    UsdLux.DomeLight.Define(stage, "/World/light").CreateIntensityAttr(1)
    settings = UsdRender.Settings.Define(stage, "/Render/settings")
    settings.CreateResolutionAttr(Gf.Vec2i(32, 32))
    settings.CreateCameraRel().SetTargets(["/World/camera"])
    product = UsdRender.Product.Define(stage, "/Render/product")
    product.CreateProductNameAttr(str(directory / "partial.exr"))
    product.CreateProductTypeAttr("raster")
    var = UsdRender.Var.Define(stage, "/Render/color")
    var.CreateDataTypeAttr("color4f")
    var.CreateSourceNameAttr("C.*[LO]")
    var.CreateSourceTypeAttr("lpe")
    var.GetPrim().AddAppliedSchema("HuskRenderVarAPI")
    # husk (Karma) requires the generic driver:parameters:aov:* tokens; the
    # driver:parameters:aov:husk:* namespace is deprecated and makes husk exit 1
    # with "Missing driver:parameters:aov:name token" before any EXR is written.
    var.GetPrim().AddAppliedSchema("KarmaRenderVarAPI")
    var.GetPrim().CreateAttribute("driver:parameters:aov:format", Sdf.ValueTypeNames.String).Set("color4h")
    var.GetPrim().CreateAttribute("driver:parameters:aov:name", Sdf.ValueTypeNames.String).Set("C")
    product.CreateOrderedVarsRel().SetTargets(["/Render/color"])
    settings.CreateProductsRel().SetTargets(["/Render/product"])
    stage.SetMetadata("renderSettingsPrimPath", "/Render/settings")
    stage.GetRootLayer().Save()
    sub = hou.node("/stage").createNode("sublayer")
    try:
        sub.parm("filepath1").set(str(source))
        hair = hou.node("/stage").createNode("houdinihairprocedural")
        try:
            hair.setInput(0, sub)
            hair.setParms(
                {"procprim": "/World/hair", "guideprims": "/World/guides", "skinprims": "/World/skin", "hairCount": 10}
            )
            usd = directory / "render.usda"
            hair.stage().Export(str(usd))
        finally:
            hair.destroy()
    finally:
        sub.destroy()
    return usd


def main():
    directory = Path(tempfile.mkdtemp(prefix="husk-procedural-acceptance-"))
    usd = _scene(directory)
    launch = _load("render_with_husk")(str(usd), str(directory / "partial.exr"), resolution=[32, 32])
    assert launch["success"], launch
    job_id = launch["context"]["job_id"]
    poll = _load("get_husk_job")
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = poll(job_id)["context"]
        if status["state"] in ("completed", "failed", "cancelled", "canceled"):
            break
        time.sleep(1)
    else:
        _load("cancel_husk_job")(job_id)
        raise RuntimeError("render acceptance timed out")
    assert status["returncode"] == 0, "Fixture did not reach a zero-exit render"
    assert status["state"] == "failed", "Partial render was incorrectly accepted"
    assert status["render_outcome"] == "completed_with_render_errors"
    assert status["output_verification"]["state"] == "verified"
    assert str(directory / "partial.exr") in status["written_files"]
    assert (directory / "partial.exr").stat().st_size > 0
    codes = {item["code"] for item in status["render_errors"]}
    assert "HOUDINI_OPERATION_FAILED" in codes, "Expected procedural failure was not captured"
    print(json.dumps({"houdini": hou.applicationVersionString(), "job_id": job_id, "error_codes": sorted(codes)}))
    print("HOUDINI_HUSK_ACCEPTANCE_PASSED", flush=True)


if __name__ == "__main__":
    main()
