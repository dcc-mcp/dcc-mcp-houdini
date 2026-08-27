"""Behavior tests for the typed Houdini texture-assignment contract."""

from __future__ import annotations

import importlib.util
import inspect
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest
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


class _RetainsMutationParm(_FakeParm):
    def __init__(self, value: object, parm_type: object) -> None:
        super().__init__(value, parm_type)
        self._original = value
        self._mutated = False

    def set(self, value: object) -> None:
        if self._mutated and value == self._original:
            return
        self._mutated = True
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
    def __init__(self, string_type: object, node_type: str = "principledshader::2.0") -> None:
        self._parent = _FakeParent()
        self._type = node_type
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
        return _FakeNodeType(self._type)

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
        self._colorspace = None
        self._extra_parms: dict[str, _FakeParm] = {}
        self._user_data: dict[str, str] = {}
        self._name = "image{}".format(len(parent.children) + 1)
        self._session_id = 1000 + len(parent.children)

    def parm(self, name: str):
        if name == "file":
            return self._file
        if name == "colorspace":
            return self._colorspace
        return self._extra_parms.get(name)

    def enable_colorspace(self, value: str = "auto") -> None:
        self._colorspace = _FakeParm(value, self._file.parmTemplate().type())

    def type(self) -> _FakeNodeType:
        return _FakeNodeType(self._type)

    def parent(self) -> "_FakeWiringParent":
        return self._parent

    def path(self) -> str:
        return "/mat/{}".format(self._name)

    def name(self) -> str:
        return self._name

    def sessionId(self) -> int:
        return self._session_id

    def userData(self, key: str):
        return self._user_data.get(key)

    def setUserData(self, key: str, value: str) -> None:
        self._user_data[key] = value

    def destroyUserData(self, key: str, _must_exist: bool = True) -> None:
        self._user_data.pop(key, None)

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

    def node(self, name: str):
        return next((child for child in self.children if child.name() == name), None)


class _FakeRetainedDestroyNode(_FakeTextureNode):
    def destroy(self) -> None:
        return None


class _FakeRetainedDestroyParent(_FakeWiringParent):
    def createNode(self, node_type: str) -> _FakeTextureNode:
        node = _FakeRetainedDestroyNode(self, node_type, self._string_type)
        self.children.append(node)
        return node


class _FakeBaseExceptionDestroyNode(_FakeTextureNode):
    def destroy(self) -> None:
        raise KeyboardInterrupt("destroy failed")


class _FakeBaseExceptionDestroyParent(_FakeWiringParent):
    def createNode(self, node_type: str) -> _FakeTextureNode:
        node = _FakeBaseExceptionDestroyNode(self, node_type, self._string_type)
        self.children.append(node)
        return node


class _FakeWiredMaterial:
    def __init__(self, string_type: object, node_type: str = "mtlxstandard_surface") -> None:
        self._parent = _FakeWiringParent(string_type)
        self._type = node_type
        self._session_id = 100
        self._path = "/mat/standard_surface1"
        self._user_data: dict[str, str] = {}

    def parm(self, _name: str):
        return None

    def parent(self) -> _FakeWiringParent:
        return self._parent

    def type(self) -> _FakeNodeType:
        return _FakeNodeType(self._type)

    def path(self) -> str:
        return self._path

    def name(self) -> str:
        return "standard_surface1"

    def sessionId(self) -> int:
        return self._session_id

    def userData(self, key: str):
        return self._user_data.get(key)

    def setUserData(self, key: str, value: str) -> None:
        self._user_data[key] = value

    def destroyUserData(self, key: str, _must_exist: bool = True) -> None:
        self._user_data.pop(key, None)

    def inputNames(self) -> tuple[str, ...]:
        return ("base_color",)

    def input(self, _index: int):
        return None

    def setInput(self, _index: int, _node: _FakeTextureNode, _output: int) -> None:
        raise RuntimeError("private workstation path must not escape")


class _FakeSuccessfulWiredMaterial(_FakeWiredMaterial):
    def __init__(self, string_type: object, node_type: str = "mtlxstandard_surface") -> None:
        super().__init__(string_type, node_type)
        self._input = None

    def setInput(self, index: int, node: _FakeTextureNode, output: int) -> None:
        assert index == 0
        assert output == 0
        self._input = node

    def input(self, index: int):
        assert index == 0
        return self._input


class _FakeStickyRollbackMaterial(_FakeSuccessfulWiredMaterial):
    def __init__(self, string_type: object, previous_input: _FakeTextureNode) -> None:
        super().__init__(string_type)
        self._input = previous_input

    def setInput(self, index: int, node: _FakeTextureNode, output: int) -> None:
        if node is self._input:
            return
        super().setInput(index, node, output)


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


class _ExitBaseExceptionUndoGroup(_FakeUndoGroup):
    def __exit__(self, _exc_type, _exc, _tb) -> None:
        super().__exit__(_exc_type, _exc, _tb)
        raise KeyboardInterrupt("undo close failed")


class _ExitBaseExceptionUndos(_FakeUndos):
    def group(self, label: str) -> _FakeUndoGroup:
        return _ExitBaseExceptionUndoGroup(self, label)


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


def test_unversioned_principled_shader_uses_builtin_texture_slot(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type, "principledshader")
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is True
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


def test_hardlinked_texture_file_fails_before_scene_lookup(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    hou = ModuleType("hou")
    hou.node = lambda _path: (_ for _ in ()).throw(AssertionError("scene lookup must not run"))
    monkeypatch.setitem(sys.modules, "hou", hou)
    original = tmp_path / "original.png"
    texture = tmp_path / "alias.png"
    original.write_bytes(b"png")
    os.link(original, texture)

    result = module.assign_texture("/mat/principledshader1", "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "UNSAFE_TEXTURE_FILE"


def test_symlinked_texture_file_fails_before_scene_lookup(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    hou = ModuleType("hou")
    hou.node = lambda _path: (_ for _ in ()).throw(AssertionError("scene lookup must not run"))
    monkeypatch.setitem(sys.modules, "hou", hou)
    original = tmp_path / "original.png"
    texture = tmp_path / "alias.png"
    original.write_bytes(b"png")
    try:
        texture.symlink_to(original)
    except OSError as exc:
        pytest.skip("file symlinks are unavailable: {}".format(exc.winerror if hasattr(exc, "winerror") else exc))

    result = module.assign_texture("/mat/principledshader1", "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "UNSAFE_TEXTURE_FILE"


def test_texture_replacement_after_preflight_fails_without_mutation(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"first")
    original_guard = module._assert_texture_file_current
    replaced = False

    def replace_before_guard(texture_ref) -> None:
        nonlocal replaced
        if not replaced:
            replaced = True
            texture.unlink()
            texture.write_bytes(b"second")
        original_guard(texture_ref)

    monkeypatch.setattr(module, "_assert_texture_file_current", replace_before_guard)

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_FILE_CHANGED"
    assert material.parms["basecolor_useTexture"].value == 0
    assert material.parms["basecolor_texture"].value == ""


@pytest.mark.skipif(os.name != "nt", reason="Windows write-denying lease contract")
def test_equal_length_in_place_overwrite_cannot_replace_hashed_payload(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    original_payload = b"first!"
    replacement_payload = b"second"
    texture.write_bytes(original_payload)
    original_stat = texture.stat()
    texture_parm = material.parms["basecolor_texture"]
    original_set = texture_parm.set
    overwrite_denied = False

    def overwrite_during_mutation(value: object) -> None:
        nonlocal overwrite_denied
        try:
            with texture.open("r+b") as stream:
                stream.write(replacement_payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.utime(texture, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        except PermissionError:
            overwrite_denied = True
        original_set(value)

    texture_parm.set = overwrite_during_mutation

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is True, result
    assert overwrite_denied is True
    assert texture.read_bytes() == original_payload
    assert material.parms["basecolor_useTexture"].value == 1
    assert material.parms["basecolor_texture"].value == str(texture)


def test_texture_payload_is_hashed_once_per_assignment(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    image = _FakeTextureNode(parent, "mtlximage", string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: image if path == image.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"x" * (4 * 1024 * 1024))
    original_read = module.os.read
    bytes_read = 0

    def measured_read(fd: int, size: int) -> bytes:
        nonlocal bytes_read
        chunk = original_read(fd, size)
        bytes_read += len(chunk)
        return chunk

    monkeypatch.setattr(module.os, "read", measured_read)

    result = module.assign_texture(image.path(), "file", str(texture))

    assert result["success"] is True, result
    assert bytes_read == texture.stat().st_size


def test_texture_digest_deadline_is_checked_after_eof_read(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    hou = ModuleType("hou")
    hou.node = lambda _path: (_ for _ in ()).throw(AssertionError("scene lookup must not run"))
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "empty.exr"
    texture.write_bytes(b"")
    now = 0.0
    original_read = module.os.read

    def monotonic() -> float:
        return now

    def delayed_eof_read(fd: int, size: int) -> bytes:
        nonlocal now
        chunk = original_read(fd, size)
        now = module._MAX_TEXTURE_HASH_SECS + 0.001
        return chunk

    monkeypatch.setattr(module.time, "monotonic", monotonic)
    monkeypatch.setattr(module.os, "read", delayed_eof_read)

    result = module.assign_texture("/mat/principledshader1", "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "UNSAFE_TEXTURE_FILE"


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


def test_nonthrowing_node_destroy_requires_exact_readback(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeWiredMaterial(string_type)
    material._parent = _FakeRetainedDestroyParent(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ROLLBACK_FAILED"
    assert len(material.parent().children) == 1


def test_destroy_baseexception_is_reported_as_unverified_rollback(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeWiredMaterial(string_type)
    material._parent = _FakeBaseExceptionDestroyParent(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ROLLBACK_FAILED"


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


def test_nonthrowing_parameter_rollback_requires_exact_readback(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    material.parms["basecolor_texture"] = _RetainsMutationParm("original.png", string_type)
    material.parms["basecolor_useTexture"] = _FailOnValueParm(0, object(), rejected=1)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ROLLBACK_FAILED"
    assert "original.png" not in str(result)


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


def test_principled_rejects_explicit_colorspace_before_mutation(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture), colorspace="ACEScg")

    assert result["success"] is False
    assert result["error"] == "UNSUPPORTED_COLORSPACE"
    assert material.parms["basecolor_useTexture"].value == 0
    assert material.parms["basecolor_texture"].value == ""


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


def test_direct_image_rejects_non_file_string_parameter(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    image = _FakeTextureNode(parent, "mtlximage", string_type)
    image._extra_parms["label"] = _FakeParm("keep me", string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: image if path == image.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(image.path(), "label", str(texture))

    assert result["success"] is False
    assert result["error"] == "UNSUPPORTED_TEXTURE_PARAMETER"
    assert image.parm("label").value == "keep me"


def test_explicit_colorspace_requires_parameter_before_direct_mutation(monkeypatch, tmp_path: Path) -> None:
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

    result = module.assign_texture(image.path(), "file", str(texture), colorspace="ACEScg")

    assert result["success"] is False
    assert result["error"] == "UNSUPPORTED_COLORSPACE"
    assert image.parm("file").value == ""


def test_explicit_colorspace_is_applied_and_read_back_on_direct_image(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    image = _FakeTextureNode(parent, "arnold::image", string_type)
    image.enable_colorspace()
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: image if path == image.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(image.path(), "file", str(texture), colorspace="ACEScg")

    assert result["success"] is True
    assert result["context"]["colorspace_applied"] == "ACEScg"
    assert result["context"]["readback"]["colorspace"] == "ACEScg"
    assert image.parm("colorspace").value == "ACEScg"


def test_auto_colorspace_is_advisory_and_not_reported_as_applied(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    image = _FakeTextureNode(parent, "mtlximage", string_type)
    image.enable_colorspace("host-default")
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: image if path == image.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(image.path(), "file", str(texture))

    assert result["success"] is True
    assert result["context"]["detected_colorspace"] == "sRGB"
    assert "colorspace_applied" not in result["context"]
    assert image.parm("colorspace").value == "host-default"


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


def test_wired_image_rejects_non_string_file_host_shape_before_mutation(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    non_string_type = object()
    material = _FakeSuccessfulWiredMaterial(non_string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "UNSUPPORTED_TEXTURE_PARAMETER"
    assert material.input(0) is None
    assert material.parent().children == []


def test_repeated_materialx_assignment_reuses_owned_image_node(monkeypatch, tmp_path: Path) -> None:
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

    first = module.assign_texture(material.path(), "base_color", str(texture))
    first_image = material.input(0)
    second = module.assign_texture(material.path(), "base_color", str(texture))

    assert first["success"] is True
    assert second["success"] is True
    assert material.input(0) is first_image
    assert material.parent().children == [first_image]


def test_duplicate_owned_texture_nodes_fail_closed_without_mutation(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    first = material.parent().createNode("mtlximage")
    second = material.parent().createNode("mtlximage")
    material.setUserData(module._MATERIAL_ID_USER_DATA_KEY, "material-identity")
    first.setUserData(module._OWNER_USER_DATA_KEY, module._owner_marker(material, 0, first))
    second.setUserData(module._OWNER_USER_DATA_KEY, module._owner_marker(material, 0, second))
    material._input = first
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "AMBIGUOUS_TEXTURE_OWNERSHIP"
    assert material.input(0) is first
    assert first.parm("file").value == ""
    assert second.parm("file").value == ""


def test_material_rename_reuses_one_durable_owned_texture_node(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    first = module.assign_texture(material.path(), "base_color", str(texture))
    owned = material.input(0)
    material._path = "/mat/renamed_surface"
    second = module.assign_texture(material.path(), "base_color", str(texture))

    assert first["success"] is True
    assert second["success"] is True
    assert material.input(0) is owned
    assert material.parent().children == [owned]


def test_replaced_material_session_rejects_stale_owned_node(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    first = module.assign_texture(material.path(), "base_color", str(texture))
    owned = material.input(0)
    material._session_id += 1
    second = module.assign_texture(material.path(), "base_color", str(texture))

    assert first["success"] is True
    assert second["success"] is False
    assert second["error"] == "AMBIGUOUS_TEXTURE_OWNERSHIP"
    assert material.input(0) is owned
    assert material.parent().children == [owned]


def test_reused_material_session_cannot_claim_stale_path_alias(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    active_material = material
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: active_material if path == active_material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    first = module.assign_texture(material.path(), "base_color", str(texture))
    owned = material.input(0)
    replacement = _FakeSuccessfulWiredMaterial(string_type)
    replacement._parent = material.parent()
    replacement._input = owned
    replacement._session_id = material.sessionId()
    replacement._path = "/mat/reused_session_alias"
    active_material = replacement
    second = module.assign_texture(replacement.path(), "base_color", str(texture))

    assert first["success"] is True
    assert second["success"] is False
    assert second["error"] == "AMBIGUOUS_TEXTURE_OWNERSHIP"
    assert replacement.input(0) is owned
    assert replacement.parent().children == [owned]


def test_reloaded_module_rejects_replacement_with_reused_session_and_path(monkeypatch, tmp_path: Path) -> None:
    first_module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    active_material = material
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: active_material if path == active_material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    first = first_module.assign_texture(material.path(), "base_color", str(texture))
    owned = material.input(0)
    replacement = _FakeSuccessfulWiredMaterial(string_type)
    replacement._parent = material.parent()
    replacement._input = owned
    replacement._session_id = material.sessionId()
    replacement._path = material.path()
    active_material = replacement
    reloaded_module = _load_script()
    second = reloaded_module.assign_texture(replacement.path(), "base_color", str(texture))

    assert first["success"] is True
    assert second["success"] is False
    assert second["error"] == "AMBIGUOUS_TEXTURE_OWNERSHIP"
    assert replacement.input(0) is owned
    assert replacement.parent().children == [owned]


def test_arnold_material_assignment_creates_exact_owned_image_type(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type, "arnold::standard_surface")
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is True
    assert material.input(0).type().name() == "arnold::image"
    assert [node.type().name() for node in material.parent().children] == ["arnold::image"]


def test_existing_unowned_upstream_node_is_preserved(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    existing = material.parent().createNode("mtlximage")
    material._input = existing
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is True
    assert material.input(0) is not existing
    assert existing in material.parent().children
    assert len(material.parent().children) == 2


def test_foreign_owned_upstream_node_is_preserved(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    existing = material.parent().createNode("mtlximage")
    existing.setUserData("dcc_mcp.assign_texture.owner", "v1|/mat/other_material|0")
    material._input = existing
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is True
    assert material.input(0) is not existing
    assert existing in material.parent().children


def test_foreign_durable_owned_upstream_node_is_preserved(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    material.setUserData(module._MATERIAL_ID_USER_DATA_KEY, "current-material")
    existing = material.parent().createNode("mtlximage")
    existing.setUserData(
        module._OWNER_USER_DATA_KEY,
        "v3|foreign-material|999|0|{}|/mat/other_material".format(existing.sessionId()),
    )
    material._input = existing
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is True
    assert material.input(0) is not existing
    assert existing in material.parent().children


def test_wired_material_rejects_explicit_colorspace_before_node_creation(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type, "arnold::standard_surface")
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture), colorspace="ACEScg")

    assert result["success"] is False
    assert result["error"] == "UNSUPPORTED_COLORSPACE"
    assert material.parent().children == []


def test_wiring_rollback_requires_exact_input_readback(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    existing = parent.createNode("mtlximage")
    material = _FakeStickyRollbackMaterial(string_type, existing)
    material._parent = parent
    original_set_input = material.setInput

    def fail_then_retain(index: int, node: _FakeTextureNode, output: int) -> None:
        if node is existing:
            return
        original_set_input(index, node, output)
        raise RuntimeError("private wiring failure")

    material.setInput = fail_then_retain
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ROLLBACK_FAILED"
    assert "private wiring" not in str(result)


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


def test_post_mutation_node_summary_failure_rolls_back_wired_graph(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    hou.undos = _FakeUndos()
    monkeypatch.setitem(sys.modules, "hou", hou)
    monkeypatch.setattr(
        module,
        "node_summary",
        lambda _node: (_ for _ in ()).throw(KeyboardInterrupt("post-mutation failure")),
    )
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_WIRING_FAILED"
    assert material.input(0) is None
    assert material.parent().children == []


def test_post_mutation_skill_success_failure_rolls_back_direct_parameter(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    image = _FakeTextureNode(parent, "mtlximage", string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: image if path == image.path() else None
    monkeypatch.setitem(sys.modules, "hou", hou)
    monkeypatch.setattr(
        module,
        "skill_success",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SystemExit("post-mutation failure")),
    )
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(image.path(), "file", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ASSIGNMENT_FAILED"
    assert image.parm("file").value == ""


def test_undo_group_exit_baseexception_rolls_back_direct_parameter(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    parent = _FakeWiringParent(string_type)
    image = _FakeTextureNode(parent, "mtlximage", string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: image if path == image.path() else None
    hou.undos = _ExitBaseExceptionUndos()
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(image.path(), "file", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ASSIGNMENT_FAILED"
    assert image.parm("file").value == ""


def test_undo_group_exit_baseexception_rolls_back_principled_parameters(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakePrincipledShader(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    hou.undos = _ExitBaseExceptionUndos()
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"png")

    result = module.assign_texture(material.path(), "basecolor", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ASSIGNMENT_FAILED"
    assert material.parms["basecolor_useTexture"].value == 0
    assert material.parms["basecolor_texture"].value == ""


def test_undo_group_exit_baseexception_rolls_back_wired_graph(monkeypatch, tmp_path: Path) -> None:
    module = _load_script()
    string_type = object()
    material = _FakeSuccessfulWiredMaterial(string_type)
    hou = ModuleType("hou")
    hou.parmTemplateType = type("ParmTemplateType", (), {"String": string_type})
    hou.node = lambda path: material if path == material.path() else None
    hou.undos = _ExitBaseExceptionUndos()
    monkeypatch.setitem(sys.modules, "hou", hou)
    texture = tmp_path / "albedo.exr"
    texture.write_bytes(b"exr")

    result = module.assign_texture(material.path(), "base_color", str(texture))

    assert result["success"] is False
    assert result["error"] == "TEXTURE_ASSIGNMENT_FAILED"
    assert material.input(0) is None
    assert material.parent().children == []


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
