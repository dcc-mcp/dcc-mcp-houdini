"""Assign a texture through a bounded, typed Houdini node contract."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from _library_common import get_node, hou_import_error, node_summary  # noqa: E402
from dcc_mcp_core.skill import skill_entry, skill_error, skill_success

_PRINCIPLED_SHADER_TYPES = frozenset({"principledshader", "principledshader::2.0"})
_DIRECT_TEXTURE_NODE_TYPES = frozenset({"arnold::image", "mtlximage"})
_WIRED_MATERIAL_NODE_TYPES = {
    "arnold::standard_surface": "arnold::image",
    "mtlxstandard_surface": "mtlximage",
}
_IMAGE_FILE_PARMS = {
    "arnold::image": ("filename", "file"),
    "mtlximage": ("file",),
}
_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_OWNER_USER_DATA_KEY = "dcc_mcp.assign_texture.owner"


class _TextureFileError(RuntimeError):
    """A stable, path-redacted texture file validation failure."""


class _OwnershipError(RuntimeError):
    """An ambiguous or stale ownership contract."""


@dataclass(frozen=True)
class _TextureFileRef:
    path: str
    resolved_path: str
    device: int
    inode: int
    size: int
    mtime_ns: int
    ctime_ns: int
    digest: str


def _is_reparse(stat_result: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(stat_result, "st_file_attributes", 0) & reparse_flag)


def _capture_texture_file(texture_path: str) -> _TextureFileRef:
    path = Path(texture_path).absolute()
    try:
        lexical = os.path.normcase(os.path.normpath(str(path)))
        resolved = path.resolve(strict=True)
        if os.path.normcase(os.path.normpath(str(resolved))) != lexical:
            raise _TextureFileError("unsafe texture path")

        for parent in path.parents:
            if parent.parent == parent:
                break
            parent_stat = os.lstat(str(parent))
            if stat.S_ISLNK(parent_stat.st_mode) or _is_reparse(parent_stat):
                raise _TextureFileError("unsafe texture path")

        path_stat = os.lstat(str(path))
        if (
            not stat.S_ISREG(path_stat.st_mode)
            or stat.S_ISLNK(path_stat.st_mode)
            or _is_reparse(path_stat)
            or path_stat.st_nlink != 1
        ):
            raise _TextureFileError("unsafe texture file")

        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), flags)
        try:
            opened_before = os.fstat(fd)
            digest = hashlib.sha256()
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            opened_after = os.fstat(fd)
        finally:
            os.close(fd)
        path_after = os.lstat(str(path))
    except _TextureFileError:
        raise
    except (FileNotFoundError, NotADirectoryError) as exc:
        raise FileNotFoundError from exc
    except OSError as exc:
        raise _TextureFileError("texture file could not be captured safely") from exc

    identity_before = (path_stat.st_dev, path_stat.st_ino, path_stat.st_size)
    identity_opened = (opened_before.st_dev, opened_before.st_ino, opened_before.st_size)
    identity_after = (opened_after.st_dev, opened_after.st_ino, opened_after.st_size)
    identity_path_after = (path_after.st_dev, path_after.st_ino, path_after.st_size)
    if not identity_before == identity_opened == identity_after == identity_path_after:
        raise _TextureFileError("texture file changed during capture")
    if (
        opened_before.st_mtime_ns != opened_after.st_mtime_ns
        or opened_before.st_ctime_ns != opened_after.st_ctime_ns
        or path_after.st_nlink != 1
        or _is_reparse(path_after)
    ):
        raise _TextureFileError("texture file changed during capture")
    return _TextureFileRef(
        path=str(path),
        resolved_path=str(resolved),
        device=opened_after.st_dev,
        inode=opened_after.st_ino,
        size=opened_after.st_size,
        mtime_ns=opened_after.st_mtime_ns,
        ctime_ns=opened_after.st_ctime_ns,
        digest=digest.hexdigest(),
    )


def _assert_texture_file_current(texture_ref: _TextureFileRef) -> None:
    if _capture_texture_file(texture_ref.path) != texture_ref:
        raise _TextureFileError("texture file identity changed")


def _detect_colorspace(texture_path: str) -> Optional[str]:
    """Best-effort color space detection from file extension."""
    return {
        ".exr": "linear",
        ".hdr": "linear",
        ".jpg": "sRGB",
        ".jpeg": "sRGB",
        ".png": "sRGB",
        ".tif": "linear",
        ".tiff": "linear",
        ".tga": "sRGB",
        ".bmp": "sRGB",
        ".tx": "auto",
        ".rat": "auto",
    }.get(Path(texture_path).suffix.lower())


def _undo_group(hou: Any, label: str) -> Any:
    undos = getattr(hou, "undos", None)
    group = getattr(undos, "group", None)
    return group(label) if callable(group) else nullcontext()


def _rollback_parms(snapshots: list[tuple[Any, Any]]) -> bool:
    try:
        for parm, value in reversed(snapshots):
            parm.set(value)
        return all(parm.eval() == value for parm, value in snapshots)
    except BaseException:  # noqa: BLE001
        return False


def _assign_principled(
    material_node: Any,
    parameter_name: str,
    texture_path: str,
    texture_ref: _TextureFileRef,
    colorspace: Optional[str],
    undo_label: str,
) -> dict:
    use_texture_parm = material_node.parm("{}_useTexture".format(parameter_name))
    texture_parm = material_node.parm("{}_texture".format(parameter_name))
    if use_texture_parm is None or texture_parm is None:
        return skill_error(
            "Unsupported Principled Shader texture parameter",
            "UNSUPPORTED_TEXTURE_PARAMETER",
        )

    try:
        _assert_texture_file_current(texture_ref)
        texture_before = texture_parm.eval()
        _assert_texture_file_current(texture_ref)
        enabled_before = use_texture_parm.eval()
        snapshots = [(texture_parm, texture_before), (use_texture_parm, enabled_before)]
        _assert_texture_file_current(texture_ref)
        texture_parm.set(texture_path)
        _assert_texture_file_current(texture_ref)
        use_texture_parm.set(1)
        _assert_texture_file_current(texture_ref)
        texture_readback = texture_parm.eval()
        _assert_texture_file_current(texture_ref)
        enabled_readback = use_texture_parm.eval()
        if texture_readback != texture_path or not bool(enabled_readback):
            raise RuntimeError("readback mismatch")
        _assert_texture_file_current(texture_ref)
        material_summary = node_summary(material_node)
        return skill_success(
            "Assigned texture to Principled Shader parameter",
            material=material_summary,
            parameter=parameter_name,
            texture_path=texture_path,
            detected_colorspace=_detect_colorspace(texture_path),
            verified=True,
            undo_label=undo_label,
            readback={"texture_enabled": bool(enabled_readback), "texture_path": str(texture_readback)},
        )
    except BaseException as exc:  # noqa: BLE001
        if "snapshots" in locals() and not _rollback_parms(snapshots):
            return skill_error(
                "Texture assignment failed and rollback could not be verified",
                "TEXTURE_ROLLBACK_FAILED",
            )
        if isinstance(exc, _TextureFileError):
            return skill_error("Texture file changed during assignment", "TEXTURE_FILE_CHANGED")
        return skill_error("Texture assignment failed", "TEXTURE_ASSIGNMENT_FAILED")


def _assign_direct_texture(
    hou: Any,
    texture_node: Any,
    parameter_name: str,
    texture_path: str,
    texture_ref: _TextureFileRef,
    colorspace: Optional[str],
    undo_label: str,
) -> dict:
    node_type = texture_node.type().name()
    if parameter_name not in _IMAGE_FILE_PARMS.get(node_type, ()):
        return skill_error(
            "Unsupported texture file parameter",
            "UNSUPPORTED_TEXTURE_PARAMETER",
            node_type=node_type,
        )
    parm = texture_node.parm(parameter_name)
    try:
        parm_type = parm.parmTemplate().type() if parm is not None else None
    except Exception:  # noqa: BLE001
        parm_type = None
    if parm_type != hou.parmTemplateType.String:
        return skill_error(
            "Unsupported texture file parameter",
            "UNSUPPORTED_TEXTURE_PARAMETER",
            node_type=node_type,
        )

    cs_parm = texture_node.parm("colorspace") if colorspace else None
    try:
        cs_parm_type = cs_parm.parmTemplate().type() if cs_parm is not None else None
    except Exception:  # noqa: BLE001
        cs_parm_type = None
    if colorspace is not None and cs_parm_type != hou.parmTemplateType.String:
        return skill_error(
            "Explicit color space is unsupported for this texture target",
            "UNSUPPORTED_COLORSPACE",
            node_type=node_type,
        )
    try:
        _assert_texture_file_current(texture_ref)
        snapshots = [(parm, parm.eval())]
        if cs_parm is not None:
            _assert_texture_file_current(texture_ref)
            snapshots.append((cs_parm, cs_parm.eval()))
        _assert_texture_file_current(texture_ref)
        parm.set(texture_path)
        if cs_parm is not None:
            _assert_texture_file_current(texture_ref)
            cs_parm.set(colorspace)
        _assert_texture_file_current(texture_ref)
        texture_readback = parm.eval()
        if texture_readback != texture_path:
            raise RuntimeError("readback mismatch")
        if cs_parm is not None:
            _assert_texture_file_current(texture_ref)
            colorspace_readback = cs_parm.eval()
            if colorspace_readback != colorspace:
                raise RuntimeError("colorspace readback mismatch")
        _assert_texture_file_current(texture_ref)
        material_summary = node_summary(texture_node)
        readback = {"parameter": parameter_name, "texture_path": str(texture_readback)}
        context = {"detected_colorspace": _detect_colorspace(texture_path)}
        if colorspace is not None:
            readback["colorspace"] = str(colorspace_readback)
            context["colorspace_applied"] = colorspace
        return skill_success(
            "Assigned texture to image node parameter",
            material=material_summary,
            parameter=parameter_name,
            texture_path=texture_path,
            verified=True,
            undo_label=undo_label,
            readback=readback,
            **context,
        )
    except BaseException as exc:  # noqa: BLE001
        if "snapshots" in locals() and not _rollback_parms(snapshots):
            return skill_error(
                "Texture assignment failed and rollback could not be verified",
                "TEXTURE_ROLLBACK_FAILED",
            )
        if isinstance(exc, _TextureFileError):
            return skill_error("Texture file changed during assignment", "TEXTURE_FILE_CHANGED")
        return skill_error("Texture assignment failed", "TEXTURE_ASSIGNMENT_FAILED")


def _destroy_created_node(node: Any) -> bool:
    try:
        parent = node.parent()
        name = node.name()
        node.destroy()
        return parent.node(name) is not node
    except Exception:  # noqa: BLE001
        return False


def _node_session_id(node: Any) -> int:
    session_id = node.sessionId()
    if not isinstance(session_id, int) or isinstance(session_id, bool) or session_id < 0:
        raise RuntimeError("invalid node session identity")
    return session_id


def _owner_marker(material_node: Any, input_index: int, texture_node: Any) -> str:
    return "v2|{}|{}|{}|{}".format(
        _node_session_id(material_node),
        input_index,
        _node_session_id(texture_node),
        material_node.path(),
    )


def _is_owned_texture(node: Any, texture_type: str, material_node: Any, input_index: int) -> bool:
    try:
        return (
            node is not None
            and node.type().name() == texture_type
            and node.userData(_OWNER_USER_DATA_KEY) == _owner_marker(material_node, input_index, node)
        )
    except BaseException:  # noqa: BLE001
        return False


def _parent_children(parent: Any) -> tuple[Any, ...]:
    children = parent.children
    return tuple(children() if callable(children) else children)


def _find_owned_texture(material_node: Any, input_index: int, texture_type: str) -> Optional[Any]:
    material_session = _node_session_id(material_node)
    material_path = material_node.path()
    owned = []
    for node in _parent_children(material_node.parent()):
        marker = node.userData(_OWNER_USER_DATA_KEY)
        if not isinstance(marker, str) or not marker.startswith("v2|"):
            continue
        parts = marker.split("|", 4)
        if len(parts) != 5:
            raise _OwnershipError("invalid texture ownership marker")
        try:
            marker_material_session = int(parts[1])
            marker_input = int(parts[2])
            marker_node_session = int(parts[3])
        except ValueError as exc:
            raise _OwnershipError("invalid texture ownership marker") from exc
        if marker_input != input_index:
            continue
        if marker_material_session != material_session:
            if parts[4] == material_path:
                raise _OwnershipError("stale material session ownership")
            continue
        if marker_node_session != _node_session_id(node) or node.type().name() != texture_type:
            raise _OwnershipError("stale texture node ownership")
        owned.append(node)
    if len(owned) > 1:
        raise _OwnershipError("duplicate texture ownership")
    return owned[0] if owned else None


def _assign_wired_material(
    material_node: Any,
    material_type: str,
    parameter_name: str,
    texture_path: str,
    texture_ref: _TextureFileRef,
    colorspace: Optional[str],
    undo_label: str,
) -> dict:
    texture_type = _WIRED_MATERIAL_NODE_TYPES[material_type]
    try:
        input_names = tuple(material_node.inputNames())
    except Exception:  # noqa: BLE001
        input_names = ()
    input_index = next(
        (index for index, name in enumerate(input_names) if name.lower() == parameter_name.lower()),
        None,
    )
    if input_index is None:
        return skill_error(
            "Unsupported material texture input",
            "UNSUPPORTED_TEXTURE_PARAMETER",
            node_type=material_type,
        )

    try:
        _assert_texture_file_current(texture_ref)
        previous_input = material_node.input(input_index)
        owned_texture = _find_owned_texture(material_node, input_index, texture_type)
    except _TextureFileError:
        return skill_error("Texture file changed during assignment", "TEXTURE_FILE_CHANGED")
    except _OwnershipError:
        return skill_error("Texture ownership is ambiguous", "AMBIGUOUS_TEXTURE_OWNERSHIP")
    except BaseException:  # noqa: BLE001
        return skill_error("Material input cannot be read safely", "TEXTURE_WIRING_FAILED")

    if owned_texture is not None and owned_texture is not previous_input:
        return skill_error("Texture ownership is ambiguous", "AMBIGUOUS_TEXTURE_OWNERSHIP")
    created = owned_texture is None
    texture_node = None
    snapshots: list[tuple[Any, Any]] = []

    try:
        if created:
            _assert_texture_file_current(texture_ref)
            texture_node = material_node.parent().createNode(texture_type)
            owner_marker = _owner_marker(material_node, input_index, texture_node)
            _assert_texture_file_current(texture_ref)
            texture_node.setUserData(_OWNER_USER_DATA_KEY, owner_marker)
            _assert_texture_file_current(texture_ref)
            if texture_node.userData(_OWNER_USER_DATA_KEY) != owner_marker:
                raise RuntimeError("ownership readback mismatch")
        else:
            texture_node = owned_texture

        file_parm = next(
            (texture_node.parm(name) for name in _IMAGE_FILE_PARMS.get(texture_type, ()) if texture_node.parm(name)),
            None,
        )
        if file_parm is None:
            raise RuntimeError("texture node has no supported file parameter")
        _assert_texture_file_current(texture_ref)
        snapshots = [(file_parm, file_parm.eval())]
        _assert_texture_file_current(texture_ref)
        file_parm.set(texture_path)
        if created:
            _assert_texture_file_current(texture_ref)
            material_node.setInput(input_index, texture_node, 0)
        _assert_texture_file_current(texture_ref)
        texture_readback = file_parm.eval()
        _assert_texture_file_current(texture_ref)
        input_readback = material_node.input(input_index)
        if texture_readback != texture_path or input_readback is not texture_node:
            raise RuntimeError("readback mismatch")
        _assert_texture_file_current(texture_ref)
        material_summary = node_summary(material_node)
        _assert_texture_file_current(texture_ref)
        texture_summary = node_summary(texture_node)
        _assert_texture_file_current(texture_ref)
        texture_node_path = texture_node.path()
        return skill_success(
            "Assigned and wired texture to material",
            material=material_summary,
            parameter=parameter_name,
            texture_node=texture_summary,
            texture_path=texture_path,
            detected_colorspace=_detect_colorspace(texture_path),
            reused_owned_node=not created,
            verified=True,
            undo_label=undo_label,
            readback={
                "input_index": input_index,
                "texture_node": texture_node_path,
                "texture_path": str(texture_readback),
            },
        )
    except BaseException as exc:  # noqa: BLE001
        rollback_ok = _rollback_parms(snapshots) if snapshots else True
        try:
            current_input = material_node.input(input_index)
            if current_input is not previous_input:
                material_node.setInput(input_index, previous_input, 0)
            rollback_ok = material_node.input(input_index) is previous_input and rollback_ok
        except BaseException:  # noqa: BLE001
            rollback_ok = False
        if created and texture_node is not None:
            rollback_ok = _destroy_created_node(texture_node) and rollback_ok
        if not rollback_ok:
            return skill_error(
                "Texture wiring failed and rollback could not be verified",
                "TEXTURE_ROLLBACK_FAILED",
            )
        if isinstance(exc, _TextureFileError):
            return skill_error("Texture file changed during assignment", "TEXTURE_FILE_CHANGED")
        return skill_error("Texture could not be wired to the material input", "TEXTURE_WIRING_FAILED")


def assign_texture(
    material_path: str,
    parameter_name: str,
    texture_path: str,
    colorspace: Optional[str] = None,
) -> dict:
    """Assign a texture to one explicitly supported material or image target."""
    try:
        import hou  # noqa: PLC0415
    except ImportError:
        return hou_import_error()

    if not isinstance(material_path, str) or not material_path.startswith("/"):
        return skill_error("Invalid Houdini material path", "INVALID_MATERIAL_PATH")
    if not isinstance(parameter_name, str) or not _PARAMETER_NAME_RE.fullmatch(parameter_name):
        return skill_error("Invalid texture parameter name", "INVALID_PARAMETER_NAME")
    if not isinstance(texture_path, str) or not texture_path:
        return skill_error("Invalid texture file path", "INVALID_TEXTURE_PATH")
    if colorspace is not None and (not isinstance(colorspace, str) or not colorspace):
        return skill_error("Invalid texture color space", "INVALID_COLORSPACE")
    try:
        texture_ref = _capture_texture_file(texture_path)
    except FileNotFoundError:
        return skill_error(
            "Texture file was not found",
            "TEXTURE_FILE_NOT_FOUND",
            prompt="Check the texture path and try again.",
        )
    except _TextureFileError:
        return skill_error(
            "Texture file could not be used safely",
            "UNSAFE_TEXTURE_FILE",
            prompt="Use a stable local regular file with no links or reparse points.",
        )
    texture_path = texture_ref.path

    try:
        target_node = get_node(hou, material_path)
        target_type = target_node.type().name()
    except Exception:  # noqa: BLE001
        return skill_error("Material or texture target was not found", "TEXTURE_TARGET_NOT_FOUND")

    supported_types = _PRINCIPLED_SHADER_TYPES | _DIRECT_TEXTURE_NODE_TYPES | frozenset(_WIRED_MATERIAL_NODE_TYPES)
    if target_type not in supported_types:
        return skill_error(
            "Unsupported texture assignment target",
            "UNSUPPORTED_TEXTURE_TARGET",
            node_type=target_type or "unknown",
        )
    if colorspace is not None and target_type in _PRINCIPLED_SHADER_TYPES:
        return skill_error(
            "Explicit color space is unsupported for this texture target",
            "UNSUPPORTED_COLORSPACE",
            node_type=target_type,
        )
    if colorspace is not None and target_type in _WIRED_MATERIAL_NODE_TYPES:
        return skill_error(
            "Explicit color space is unsupported for this texture target",
            "UNSUPPORTED_COLORSPACE",
            node_type=target_type,
        )

    undo_label = "DCC MCP: assign texture {}".format(parameter_name)
    try:
        with _undo_group(hou, undo_label):
            if target_type in _PRINCIPLED_SHADER_TYPES:
                return _assign_principled(
                    target_node,
                    parameter_name,
                    texture_path,
                    texture_ref,
                    colorspace,
                    undo_label,
                )
            if target_type in _DIRECT_TEXTURE_NODE_TYPES:
                return _assign_direct_texture(
                    hou,
                    target_node,
                    parameter_name,
                    texture_path,
                    texture_ref,
                    colorspace,
                    undo_label,
                )
            return _assign_wired_material(
                target_node,
                target_type,
                parameter_name,
                texture_path,
                texture_ref,
                colorspace,
                undo_label,
            )
    except BaseException:  # noqa: BLE001
        return skill_error("Texture assignment failed", "TEXTURE_ASSIGNMENT_FAILED")


@skill_entry
def main(**kwargs) -> dict:
    return assign_texture(**kwargs)


if __name__ == "__main__":
    from dcc_mcp_core.skill import run_main

    run_main(main)
