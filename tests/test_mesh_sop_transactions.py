"""Strict ownership and public-error contracts for downstream SOP callers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SCRIPT_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills" / "houdini-mesh-ops" / "scripts"
_PRIVATE_TOKENS = (
    "PRIVATE_POST_TRANSFER_PARAMETER_FAILURE",
    "C:\\Users\\private\\shot.hip",
    "relative/private/report.json",
)


def _load_script(script_name: str) -> ModuleType:
    path = _SCRIPT_ROOT / script_name
    spec = importlib.util.spec_from_file_location("transaction_{}".format(path.stem), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _wire_downstream(optype: str):
    parent = MagicMock()
    parent.path.return_value = "/obj/geo1"
    created = MagicMock()
    created.path.return_value = "/obj/geo1/{}1".format(optype)
    created.name.return_value = "{}1".format(optype)
    created.type.return_value.name.return_value = optype
    created.parmTuple.return_value = None
    created.parm.return_value = MagicMock()
    parent.createNode.return_value = created
    source = MagicMock()
    source.path.return_value = "/obj/geo1/source"
    source.parent.return_value = parent
    hou = MagicMock()
    hou.node.return_value = source
    return hou, created


def _assert_safe_failure(result: dict) -> None:
    assert result["success"] is False
    payload = json.dumps(result, sort_keys=True)
    assert "traceback" not in payload.lower()
    for token in _PRIVATE_TOKENS:
        assert token not in payload
    assert result["context"]["error_code"] == "houdini_sop_transaction_failed"
    assert result["context"]["error_type"] == "RuntimeError"


_POST_TRANSFER_CASES = (
    ("add_normals.py", "add_normals", "normal", {"input_path": "/obj/geo1/source"}, "set_parm_if_exists"),
    (
        "blast_geometry.py",
        "blast_geometry",
        "blast",
        {"input_path": "/obj/geo1/source", "group": "0-5"},
        "set_parm_if_exists",
    ),
    (
        "convert_geometry.py",
        "convert_geometry",
        "convert",
        {"input_path": "/obj/geo1/source"},
        "skill_success",
    ),
    (
        "group_geometry.py",
        "group_geometry",
        "groupcreate",
        {"input_path": "/obj/geo1/source", "group_name": "top"},
        "node_summary",
    ),
    (
        "transform_geometry.py",
        "transform_geometry",
        "xform",
        {"input_path": "/obj/geo1/source", "translate": [1.0, 2.0, 3.0]},
        "set_parm_if_exists",
    ),
    (
        "triangulate_geometry.py",
        "triangulate_geometry",
        "divide",
        {"input_path": "/obj/geo1/source"},
        "node_summary",
    ),
)


@pytest.mark.parametrize(
    ("script_name", "function_name", "optype", "kwargs", "failure_target"),
    _POST_TRANSFER_CASES,
)
def test_legacy_downstream_callers_rollback_and_redact_every_post_transfer_failure(
    script_name: str,
    function_name: str,
    optype: str,
    kwargs: dict,
    failure_target: str,
) -> None:
    module = _load_script(script_name)
    hou, created = _wire_downstream(optype)
    failure = RuntimeError(" ".join(_PRIVATE_TOKENS))

    with patch.dict(sys.modules, {"hou": hou}), patch.object(module, failure_target, side_effect=failure):
        result = getattr(module, function_name)(**kwargs)

    _assert_safe_failure(result)
    created.destroy.assert_called_once_with()


@pytest.mark.parametrize("failure_type", (KeyboardInterrupt, SystemExit))
def test_transform_cleanup_preserves_exact_base_exception_identity(failure_type) -> None:
    module = _load_script("transform_geometry.py")
    hou, created = _wire_downstream("xform")
    original = failure_type(" ".join(_PRIVATE_TOKENS))

    with patch.dict(sys.modules, {"hou": hou}):
        with patch.object(module, "set_parm_if_exists", side_effect=original):
            with pytest.raises(failure_type) as captured:
                module.transform_geometry("/obj/geo1/source", translate=[1.0, 2.0, 3.0])

    assert captured.value is original
    created.destroy.assert_called_once_with()


def test_transform_cleanup_base_exception_does_not_replace_or_leak_original_failure() -> None:
    module = _load_script("transform_geometry.py")
    hou, created = _wire_downstream("xform")
    created.destroy.side_effect = SystemExit("PRIVATE_CLEANUP_FAILURE C:\\private\\cleanup.hip")
    failure = RuntimeError(" ".join(_PRIVATE_TOKENS))

    with patch.dict(sys.modules, {"hou": hou}), patch.object(
        module,
        "set_parm_if_exists",
        side_effect=failure,
    ):
        result = module.transform_geometry("/obj/geo1/source", translate=[1.0, 2.0, 3.0])

    _assert_safe_failure(result)
    assert "PRIVATE_CLEANUP_FAILURE" not in json.dumps(result, sort_keys=True)
    created.destroy.assert_called_once_with()


def test_verified_caller_cook_failure_is_exactly_once_and_public_safe() -> None:
    module = _load_script("add_edge_loop.py")
    hou, created = _wire_downstream("polysplit")
    failure = RuntimeError(" ".join(_PRIVATE_TOKENS))

    with patch.dict(sys.modules, {"hou": hou}):
        with patch.object(module, "geometry_readback", return_value={"point_count": 8}):
            with patch.object(module, "set_scalar_parm_verified", return_value="0e0.5"):
                with patch.object(module, "cook_readback", side_effect=failure):
                    result = module.add_edge_loop("/obj/geo1/source", "0e0.5")

    _assert_safe_failure(result)
    created.destroy.assert_called_once_with()


def test_every_downstream_helper_result_is_adopted_by_the_shared_transaction() -> None:
    callers = tuple(
        path
        for path in _SCRIPT_ROOT.glob("*.py")
        if path.name != "_mesh_common.py" and "make_downstream_sop(" in path.read_text(encoding="utf-8")
    )

    assert len(callers) == 16
    assert sum(path.read_text(encoding="utf-8").count("make_downstream_sop(") for path in callers) == 17
    for path in callers:
        source = path.read_text(encoding="utf-8")
        assert source.count("make_downstream_sop(") == source.count("transaction.own(make_downstream_sop(")


@pytest.mark.parametrize(
    ("script_name", "function_name", "optype", "kwargs"),
    tuple(case[:4] for case in _POST_TRANSFER_CASES),
)
def test_legacy_downstream_success_transfers_node_ownership(
    script_name: str,
    function_name: str,
    optype: str,
    kwargs: dict,
) -> None:
    module = _load_script(script_name)
    hou, created = _wire_downstream(optype)

    with patch.dict(sys.modules, {"hou": hou}):
        result = getattr(module, function_name)(**kwargs)

    assert result["success"] is True, result
    created.destroy.assert_not_called()
