"""Behavior tests for the typed Houdini texture-assignment contract."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType

import yaml
from jsonschema import Draft202012Validator
from skill_loader import skill_script_import_context

_SCRIPT = (
    Path(__file__).parent.parent
    / "src"
    / "dcc_mcp_houdini"
    / "skills"
    / "houdini-material-library"
    / "scripts"
    / "assign_texture.py"
)
_TOOLS = _SCRIPT.parent.parent / "tools.yaml"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("test_assign_texture_script", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


class _FakeParmTemplate:
    def __init__(self, parm_type: object) -> None:
        self._parm_type = parm_type

    def type(self) -> object:
        return self._parm_type


class _FakeParm:
    def __init__(self, value: object, parm_type: object) -> None:
        self.value = value
        self._template = _FakeParmTemplate(parm_type)

    def parmTemplate(self) -> _FakeParmTemplate:
        return self._template

    def set(self, value: object) -> None:
        self.value = value

    def eval(self) -> object:
        return self.value


class _FailOnValueParm(_FakeParm):
    def __init__(self, value: object, parm_type: object, rejected: object) -> None:
        super().__init__(value, parm_type)
        self._rejected = rejected

    def set(self, value: object) -> None:
        if value == self._rejected:
            raise RuntimeError("private workstation failure")
        super().set(value)


class _FakeNodeType:
    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class _FakeParent:
    def __init__(self) -> None:
        self.created_types: list[str] = []

    def createNode(self, node_type: str):
        self.created_types.append(node_type)
        raise RuntimeError("texture VOP creation should not be attempted")

    def path(self) -> str:
        return "/mat"


class _FakePrincipledShader:
    def __init__(self, string_type: object) -> None:
        self._parent = _FakeParent()
        numeric_type = object()
        self.parms = {
            "basecolor": _FakeParm((1.0, 1.0, 1.0), numeric_type),
            "basecolor_useTexture": _FakeParm(0, numeric_type),
            "basecolor_texture": _FakeParm("", string_type),
        }

    def parm(self, name: str):
        return self.parms.get(name)

    def parent(self) -> _FakeParent:
        return self._parent

    def type(self) -> _FakeNodeType:
        return _FakeNodeType("principledshader::2.0")

    def path(self) -> str:
        return "/mat/principledshader1"

    def name(self) -> str:
        return "principledshader1"


class _FakeUnsupportedNode:
    def __init__(self) -> None:
        self._parent = _FakeParent()

    def parm(self, _name: str):
        return None

    def parent(self) -> _FakeParent:
        return self._parent

    def type(self) -> _FakeNodeType:
        return _FakeNodeType("subnet")

    def path(self) -> str:
        return "/mat/not_a_shader"

    def name(self) -> str:
        return "not_a_shader"


class _FakeTextureNode:
    def __init__(self, parent: "_FakeWiringParent", node_type: str, string_type: object) -> None:
        self._parent = parent
        self._type = node_type
        self._file = _FakeParm("", string_type)

    def parm(self, name: str):
        return self._file if name == "file" else None

    def type(self) -> _FakeNodeType:
        return _FakeNodeType(self._type)

    def path(self) -> str:
        return "/mat/image1"

    def name(self) -> str:
        return "image1"

    def destroy(self) -> None:
        self._parent.children.remove(self)


class _FakeWiringParent:
    def __init__(self, string_type: object) -> None:
        self._string_type = string_type
        self.children: list[_FakeTextureNode] = []

    def createNode(self, node_type: str) -> _FakeTextureNode:
        node = _FakeTextureNode(self, node_type, self._string_type)
        self.children.append(node)
        return node

    def path(self) -> str:
        return "/mat"


class _FakeWiredMaterial:
    def __init__(self, string_type: object) -> None:
        self._parent = _FakeWiringParent(string_type)

    def parm(self, _name: str):
        return None

    def parent(self) -> _FakeWiringParent:
        return self._parent

    def type(self) -> _FakeNodeType:
        return _FakeNodeType("mtlxstandard_surface")

    def path(self) -> str:
        return "/mat/standard_surface1"

    def name(self) -> str:
        return "standard_surface1"

    def inputNames(self) -> tuple[str, ...]:
        return ("base_color",)

    def input(self, _index: int):
        return None

    def setInput(self, _index: int, _node: _FakeTextureNode, _output: int) -> None:
        raise RuntimeError("private workstation path must not escape")


class _FakeSuccessfulWiredMaterial(_FakeWiredMaterial):
    def __init__(self, string_type: object) -> None:
        super().__init__(string_type)
        self._input = None

    def setInput(self, index: int, node: _FakeTextureNode, output: int) -> None:
        assert index == 0
        assert output == 0
        self._input = node

    def input(self, index: int):
        assert index == 0
        return self._input


class _FakeUndoGroup:
    def __init__(self, owner: "_FakeUndos", label: str) -> None:
        self._owner = owner
        self._label = label

    def __enter__(self) -> None:
        self._owner.entered.append(self._label)

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self._owner.exited.append(self._label)


class _FakeUndos:
    def __init__(self) -> None:
        self.entered: list[str] = []
        self.exited: list[str] = []

    def group(self, label: str) -> _FakeUndoGroup:
        return _FakeUndoGroup(self, label)


def test_principled_shader_uses_builtin_texture_slot_without_orphan_vop(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    hou.undos = _FakeUndos()
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is True
    assert material.parms["basecolor_useTexture"].value == 1
    assert material.parms["basecolor_texture"].value == str(texture)
    assert material.parent().created_types == []


def test_unsupported_node_type_fails_without_scene_mutation(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    material = _FakeUnsupportedNode()
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": object()})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "UNSUPPORTED_TEXTURE_TARGET"
    assert result["context"]["node_type"] == "subnet"
    assert material.parent().created_types == []


def test_invalid_parameter_name_fails_before_scene_lookup(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    hou = ModuleType("hou")
    hou.node = lambda _path: (_ for _ in ()).throw(AssertionError("scene lookup must not run"))
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture("/mat/principledshader1", "../basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "INVALID_PARAMETER_NAME"


def test_missing_texture_file_returns_stable_redacted_error(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    hou = ModuleType("hou")
    hou.node = lambda _path: (_ for _ in ()).throw(AssertionError("scene lookup must not run"))
    monkeypatch.setitem(sys.modules, "hou", hou)
    missing = tmp_path / "customer-secret" / "missing.png"

    result = module.assign_texture("/mat/principledshader1", "basecolor", str(missing))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_FILE_NOT_FOUND"
    assert "customer-secret" not in str(result)


def test_wiring_failure_fails_closed_and_removes_created_texture(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeWiredMaterial(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_WIRING_FAILED"
    assert "private workstation" not in str(result)
    assert material.parent().children == []


def test_principled_partial_write_rolls_back_without_side_effect(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    material.parms["basecolor_texture"].value = "original.png"
    material.parms["basecolor_useTexture"] = _FailOnValueParm(0, object(), rejected=1)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ASSIGNMENT_FAILED"
    assert "private workstation" not in str(result)
    assert material.parms["basecolor_texture"].value == "original.png"
    assert material.parms["basecolor_useTexture"].value == 0


def test_principled_missing_builtin_texture_parameter_fails_without_mutation(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    del material.parms["basecolor_texture"]
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "UNSUPPORTED_TEXTURE_PARAMETER"
    assert material.parms["basecolor_useTexture"].value == 0
    assert material.parent().created_types == []


def test_supported_texture_node_returns_verified_file_readback(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    image = _FakeTextureNode(parent, "mtlximage", string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: image if path == image.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(image.path(), "file", str(texture))

    assert result["success"] is True
    assert result["context"]["readback"] == {
        "parameter": "file",
        "texture_path": str(texture),
    }
    assert image.parm("file").value == str(texture)
    assert parent.children == []


def test_supported_material_wiring_returns_verified_connection_readback(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    hou.undos = _FakeUndos()
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is True
    image = material.parent().children[0]
    assert result["context"]["readback"] == {
        "input_index": 0,
        "texture_node": image.path(),
        "texture_path": str(texture),
    }
    assert material.input(0) is image
    assert hou.undos.entered == [result["context"]["undo_label"]]
    assert hou.undos.exited == hou.undos.entered


def test_successful_assignment_uses_one_named_undo_group(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    hou.undos = _FakeUndos()
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is True
    assert hou.undos.entered == [result["context"]["undo_label"]]
    assert hou.undos.exited == hou.undos.entered
    assert result["context"]["undo_label"].startswith("DCC MCP: assign texture ")


def test_assign_texture_schema_matches_runtime_validation() -> None:
    module = _load_script()
    tools = yaml.safe_load(_TOOLS.read_text(encoding="utf-8"))["tools"]
    contract = next(tool for tool in tools if tool["name"] == "assign_texture")["input_schema"]

    Draft202012Validator.check_schema(contract)
    signature = inspect.signature(module.assign_texture)
    assert set(contract["properties"]) == set(signature.parameters)
    assert set(contract["required"]) == {
        name for name, parameter in signature.parameters.items() if parameter.default is inspect.Parameter.empty
    }
    assert contract["additionalProperties"] is False
    assert contract["properties"]["material_path"]["pattern"] == r"^/"
    assert contract["properties"]["parameter_name"]["pattern"] == r"^[A-Za-z][A-Za-z0-9_]*$"
    assert contract["properties"]["texture_path"]["minLength"] == 1


def test_runtime_rejects_material_path_that_schema_rejects(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    hou = ModuleType("hou")
    hou.node = lambda _path: (_ for _ in ()).throw(AssertionError("scene lookup must not run"))
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture("mat/principledshader1", "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "INVALID_MATERIAL_PATH"
