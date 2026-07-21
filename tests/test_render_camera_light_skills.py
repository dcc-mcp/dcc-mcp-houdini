"""Mock-hou unit tests for houdini-camera-light and houdini-render skills."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from skill_loader import skill_script_import_context

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"
_DEFAULT_PATTERN = object()


def _wait_for_windows_process_exit(pid: int, timeout_secs: float) -> bool:
    import ctypes
    from ctypes import wintypes

    synchronize = 0x00100000
    wait_object_0 = 0
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return True
    try:
        return kernel32.WaitForSingleObject(handle, int(timeout_secs * 1000)) == wait_object_0
    finally:
        kernel32.CloseHandle(handle)


def _load_script(skill_name: str, script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    with skill_script_import_context(spec):
        spec.loader.exec_module(module)
    return module


def _load_render_worker() -> ModuleType:
    return _load_script("houdini-render", "_render_worker.py")


def _node(path: str, name: str, type_name: str = "geo") -> MagicMock:
    node = MagicMock()
    node.path.return_value = path
    node.name.return_value = name
    node.type.return_value.name.return_value = type_name
    return node


def _scalar_parm(value):
    parm = MagicMock()
    parm.eval.return_value = value
    parm.unexpandedString.return_value = value
    return parm


class _FakeMantraParm:
    def __init__(self, owner, name):
        self._owner = owner
        self._name = name

    def eval(self):
        return self._owner.values[self._name]

    def unexpandedString(self):
        return str(self._owner.values[self._name])

    def set(self, value):
        if self._name in self._owner.set_failures:
            raise RuntimeError("cannot set {}".format(self._name))
        if self._name == "vm_numaux":
            self._owner.resize_aux(int(value))
        else:
            self._owner.values[self._name] = value

    def removeMultiParmInstance(self, index):
        self._owner.remove_aux(index)

    def multiParmStartOffset(self):
        return 1


class _FakeMantraRop:
    _AUX_DEFAULTS = {
        "vm_variable_plane{}": "",
        "vm_vextype_plane{}": "vector",
        "vm_channel_plane{}": "",
        "vm_quantize_plane{}": "half",
        "vm_pfilter_plane{}": "",
        "vm_sfilter_plane{}": "alpha",
    }

    def __init__(self, path="/out/mantra1"):
        self._path = path
        self._parent = None
        self.set_failures = set()
        self.values = {
            "vm_numaux": 0,
            "vm_picture": "",
            "vobject": "*",
            "forceobject": "",
            "matte_objects": "",
            "excludeobject": "",
            "phantom_objects": "",
        }

    def path(self):
        return self._path

    def name(self):
        return self._path.rsplit("/", 1)[-1]

    def setName(self, name, unique_name=False):
        del unique_name
        old_name = self.name()
        self._path = self._path.rsplit("/", 1)[0] + "/" + name
        if self._parent is not None:
            self._parent.children.pop(old_name, None)
            self._parent.children[name] = self

    def copyTo(self, parent):
        clone_name = self.name()
        suffix = 1
        while parent.node(clone_name) is not None:
            clone_name = "{}{}".format(self.name(), suffix)
            suffix += 1
        clone = _FakeMantraRop(parent.path() + "/" + clone_name)
        clone.values = dict(self.values)
        clone.set_failures = set(self.set_failures)
        parent.add(clone)
        return clone

    def destroy(self):
        if self._parent is not None:
            self._parent.children.pop(self.name(), None)
            self._parent = None

    def type(self):
        node_type = MagicMock()
        node_type.name.return_value = "ifd"
        return node_type

    def parm(self, name):
        return _FakeMantraParm(self, name) if name in self.values else None

    def parmTuple(self, _name):
        return None

    def resize_aux(self, count):
        previous = self.values["vm_numaux"]
        for index in range(previous + 1, count + 1):
            for pattern, default in self._AUX_DEFAULTS.items():
                self.values[pattern.format(index)] = default
        for index in range(count + 1, previous + 1):
            for pattern in self._AUX_DEFAULTS:
                self.values.pop(pattern.format(index), None)
        self.values["vm_numaux"] = count

    def remove_aux(self, index):
        planes = [
            {pattern: self.values[pattern.format(plane_index)] for pattern in self._AUX_DEFAULTS}
            for plane_index in range(1, self.values["vm_numaux"] + 1)
        ]
        planes.pop(index)
        self.resize_aux(0)
        self.resize_aux(len(planes))
        for plane_index, plane in enumerate(planes, 1):
            for pattern, value in plane.items():
                self.values[pattern.format(plane_index)] = value

    def aux_planes(self):
        return [
            {
                "variable": self.values["vm_variable_plane{}".format(index)],
                "type": self.values["vm_vextype_plane{}".format(index)],
                "channel": self.values["vm_channel_plane{}".format(index)],
            }
            for index in range(1, self.values["vm_numaux"] + 1)
        ]


class _FakeOutNetwork:
    def __init__(self):
        self.children = {}

    def path(self):
        return "/out"

    def name(self):
        return "out"

    def type(self):
        node_type = MagicMock()
        node_type.name.return_value = "ropnet"
        return node_type

    def add(self, node):
        node._parent = self
        self.children[node.name()] = node

    def node(self, name):
        return self.children.get(name)


def _fake_hou_for_out(out, hip_dir="C:/show/shot"):
    mock_hou = MagicMock()
    mock_hou.node.side_effect = lambda path: out if path == "/out" else out.node(path.rsplit("/", 1)[-1])
    mock_hou.frame.return_value = 1.0
    mock_hou.text.expandStringAtFrame.side_effect = lambda path, frame: path.replace("$HIP", hip_dir).replace(
        "$F4", "{:04d}".format(int(frame))
    )
    mock_hou.text.abspath.side_effect = lambda path: (
        path if path.startswith("/") or ":" in path[:3] else "{}/{}".format(hip_dir, path)
    )
    mock_hou.text.normpath.side_effect = lambda path: path.replace("\\", "/")
    return mock_hou


class _FakeTake:
    def __init__(self, takes, name, parent=None):
        self._takes = takes
        self._name = name
        self._parent = parent
        self._overrides = set()

    def name(self):
        return self._name

    def parent(self):
        return self._parent

    def nodes(self):
        return ()

    def addChildTake(self, name):
        return self._takes.add(name, parent=self)

    def hasParmTuple(self, parm_tuple):
        return parm_tuple in self._overrides

    def addParmTuple(self, parm_tuple):
        if self._takes.currentTake() is not self:
            raise RuntimeError("take is not current")
        self._overrides.add(parm_tuple)

    def removeParmTuple(self, parm_tuple):
        if self._takes.currentTake() is not self:
            raise RuntimeError("take is not current")
        self._overrides.discard(parm_tuple)


class _FakeTakes:
    def __init__(self):
        self._root = _FakeTake(self, "main")
        self._current = self._root
        self._takes = {"main": self._root}

    def currentTake(self):
        return self._current

    def setCurrentTake(self, take):
        self._current = take

    def rootTake(self):
        return self._root

    def findTake(self, name):
        return self._takes.get(name)

    def takes(self):
        return tuple(self._takes.values())

    def add(self, name, parent=None):
        take = _FakeTake(self, name, parent or self._root)
        self._takes[name] = take
        return take


def _run_render_worker(
    tmp_path,
    frame_range,
    expected_outputs,
    snapshot,
    render,
    stderr_text="",
    pattern=_DEFAULT_PATTERN,
    include_launch_snapshot=True,
    ignore_inputs=False,
    job_kind="render",
    rop_errors=(),
    expand_string=None,
):
    mod = _load_render_worker()
    if pattern is _DEFAULT_PATTERN:
        pattern = str(tmp_path / "beauty.$F4.exr")
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text(stderr_text, encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = {
        "state": "queued",
        "job_kind": job_kind,
        "stdout_path": str(stdout),
        "stderr_path": str(stderr),
    }
    if include_launch_snapshot:
        status.update(
            {
                "expected_outputs": [str(path) for path in expected_outputs],
                "output_snapshot": snapshot,
            }
        )
    status_path.write_text(json.dumps(status), encoding="utf-8")
    rop = _node("/stage/karma", "karma", "usdrender_rop")
    rop.errors.return_value = list(rop_errors)
    mock_hou = MagicMock()
    mock_hou.node.return_value = rop
    mock_hou.text.expandString.side_effect = expand_string or (lambda value: value)
    mock_hou.text.expandStringAtFrame.side_effect = lambda value, frame: value.replace(
        "$F4", "{:04d}".format(int(frame))
    )
    argv = [
        "_render_worker.py",
        "scene.hip",
        "/stage/karma",
        json.dumps(frame_range),
        str(status_path),
        json.dumps(pattern),
        json.dumps(ignore_inputs),
    ]
    with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(mod.sys, "argv", argv), patch.object(
        mod, "render_node", side_effect=render
    ):
        mod.main()
    return json.loads(status_path.read_text(encoding="utf-8"))


class TestCameraSkills:
    def test_list_cameras_filters_and_reads_parms(self) -> None:
        mod = _load_script("houdini-camera-light", "list_cameras.py")
        cam = _node("/obj/cam1", "cam1", "cam")
        cam.parmTuple.return_value = None
        cam.parm.side_effect = lambda n: {
            "resx": _scalar_parm(1920),
            "resy": _scalar_parm(1080),
            "focal": _scalar_parm(50.0),
        }.get(n)
        geo = _node("/obj/geo1", "geo1", "geo")
        parent = _node("/obj", "obj")
        parent.children.return_value = [cam, geo]
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.list_cameras("/obj")

        assert result["success"] is True
        assert result["context"]["count"] == 1
        assert result["context"]["cameras"][0]["resolution"] == [1920, 1080]
        assert result["context"]["cameras"][0]["focal"] == 50.0

    def test_create_camera_sets_lens(self) -> None:
        mod = _load_script("houdini-camera-light", "create_camera.py")
        cam = _node("/obj/shotcam", "shotcam", "cam")
        cam.parmTuple.return_value = MagicMock()
        resx, resy, focal = MagicMock(), MagicMock(), MagicMock()
        cam.parm.side_effect = lambda n: {"resx": resx, "resy": resy, "focal": focal}.get(n)
        parent = _node("/obj", "obj")
        parent.createNode.return_value = cam
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_camera("/obj", name="shotcam", resolution=[1280, 720], focal=35)

        assert result["success"] is True
        parent.createNode.assert_called_once_with("cam", node_name="shotcam")
        resx.set.assert_called_once_with(1280)
        focal.set.assert_called_once_with(35.0)


class TestLightSkills:
    def test_create_light_sets_core_parms(self) -> None:
        mod = _load_script("houdini-camera-light", "create_light.py")
        light = _node("/obj/keylight", "keylight", "hlight::2.0")
        light.parmTuple.return_value = MagicMock()
        type_parm, intensity_parm, exposure_parm = MagicMock(), MagicMock(), MagicMock()
        light.parm.side_effect = lambda n: {
            "light_type": type_parm,
            "light_intensity": intensity_parm,
            "light_exposure": exposure_parm,
        }.get(n)
        parent = _node("/obj", "obj")
        parent.createNode.return_value = light
        mock_hou = MagicMock()
        mock_hou.node.return_value = parent

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_light("/obj", light_type="distant", name="keylight", intensity=2.0, exposure=1.5)

        assert result["success"] is True
        type_parm.set.assert_called_once_with(7)
        intensity_parm.set.assert_called_once_with(2.0)
        exposure_parm.set.assert_called_once_with(1.5)

    def test_create_light_rejects_unknown_type(self) -> None:
        mod = _load_script("houdini-camera-light", "create_light.py")
        with patch.dict(sys.modules, {"hou": MagicMock()}):
            result = mod.create_light("/obj", light_type="laser")
        assert result["success"] is False


class TestViewSkills:
    def test_frame_view_headless(self) -> None:
        mod = _load_script("houdini-camera-light", "frame_view.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.frame_view(node_path="/obj/geo1")
        assert result["success"] is True
        assert result["context"]["framed"] is False

    def test_get_view_state_headless(self) -> None:
        mod = _load_script("houdini-camera-light", "get_view_state.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_view_state()
        assert result["success"] is True
        assert result["context"]["ui_available"] is False

    def test_frame_view_camera_only_preserves_camera_view(self) -> None:
        mod = _load_script("houdini-camera-light", "frame_view.py")
        cam = _node("/obj/shotcam", "shotcam", "cam")
        viewport = MagicMock()
        viewport.camera.return_value = cam
        viewer = MagicMock()
        viewer.curViewport.return_value = viewport
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.ui.paneTabOfType.return_value = viewer
        mock_hou.node.return_value = cam

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.frame_view(camera_path="/obj/shotcam")

        assert result["success"] is True
        assert result["context"]["framed"] is True
        assert result["context"]["active_camera"] == "/obj/shotcam"
        viewport.setCamera.assert_called_once_with(cam)
        viewport.frameAll.assert_not_called()

    def test_frame_view_frames_node_before_activating_camera(self) -> None:
        mod = _load_script("houdini-camera-light", "frame_view.py")
        events = []
        geo = _node("/obj/geo1", "geo1")
        cam = _node("/obj/shotcam", "shotcam", "cam")
        geo.setSelected.side_effect = lambda *args, **kwargs: events.append("select")
        viewport = MagicMock()
        viewport.frameSelected.side_effect = lambda: events.append("frame")
        viewport.setCamera.side_effect = lambda camera: events.append("camera")
        viewport.camera.return_value = cam
        viewer = MagicMock()
        viewer.curViewport.return_value = viewport
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.ui.paneTabOfType.return_value = viewer
        mock_hou.node.side_effect = lambda path: {"/obj/geo1": geo, "/obj/shotcam": cam}[path]

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.frame_view(node_path="/obj/geo1", camera_path="/obj/shotcam")

        assert result["success"] is True
        assert result["context"]["active_camera"] == "/obj/shotcam"
        assert events == ["select", "frame", "camera"]


class TestViewportCapture:
    def test_capture_viewport_headless_skips(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "capture_viewport.py")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = False
        out = str(tmp_path / "frame.jpg")
        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.capture_viewport(out)
        assert result["success"] is True
        assert result["context"]["captured"] is False
        assert result["context"]["skipped"] == [out]

    def test_capture_viewport_with_ui_writes_file(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "capture_viewport.py")
        out = tmp_path / "frame.jpg"
        settings = MagicMock()
        viewer = MagicMock()
        viewer.flipbookSettings.return_value.stash.return_value = settings
        viewer.flipbook.side_effect = lambda vp, s: out.write_bytes(b"img")
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.frame.return_value = 1.0
        mock_hou.ui.paneTabOfType.return_value = viewer

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.capture_viewport(str(out), resolution=[99999, 720])

        assert result["success"] is True
        assert result["context"]["captured"] is True
        assert result["context"]["written_files"] == [str(out)]
        # resolution clamped to MAX_DIMENSION
        assert result["context"]["resolution"] == [4096, 720]

    def test_flipbook_launch_returns_job_id(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "flipbook.py")
        out = str(tmp_path / "frame.$F4.jpg")
        settings = MagicMock()
        cam = _node("/obj/shotcam", "shotcam", "cam")
        viewport = MagicMock()
        viewport.camera.return_value = cam
        viewer = MagicMock()
        viewer.curViewport.return_value = viewport
        viewer.flipbookSettings.return_value.stash.return_value = settings
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.ui.paneTabOfType.return_value = viewer
        mock_hou.node.return_value = cam

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.flipbook(
                out,
                frame_range=[1, 10, 3],
                camera_path="/obj/shotcam",
            )

        assert result["success"] is True
        ctx = result["context"]
        assert "job_id" in ctx
        assert ctx["job_id"].startswith("flipbook-")
        assert ctx["state"] == "running"
        assert ctx["frame_range"] == [1.0, 10.0, 3.0]
        assert ctx["camera_path"] == "/obj/shotcam"
        assert ctx["progress"] == {"completed": 0, "total": 4}

    def test_flipbook_rejects_non_positive_increment(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "flipbook.py")
        mock_hou = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.flipbook(
                str(tmp_path / "frame.$F4.jpg"),
                frame_range=[1, 10, 0],
            )

        assert result["success"] is False
        assert "increment" in result["error"].lower()

    def test_flipbook_chunked_runner_step_through(self, tmp_path: Path) -> None:
        """Verify the ChunkedRunner steps through frames and reports progress."""
        mod = _load_script("houdini-render", "flipbook.py")
        out = str(tmp_path / "frame.$F4.jpg")
        settings = MagicMock()
        viewer = MagicMock()
        viewer.curViewport.return_value = MagicMock()
        viewer.flipbookSettings.return_value.stash.return_value = settings
        written_frames = []

        def _write_frame(vp, s):
            # Extract frame from output path in settings
            try:
                frame_path = s.output.call_args[0][0]
            except Exception:  # noqa: BLE001
                frame_path = str(tmp_path / "frame.0001.jpg")
            Path(frame_path).write_bytes(b"img")
            written_frames.append(frame_path)

        viewer.flipbook.side_effect = _write_frame
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.ui.paneTabOfType.return_value = viewer

        with patch.dict(sys.modules, {"hou": mock_hou}):
            launch_result = mod.flipbook(out, frame_range=[1, 4, 1])

            assert launch_result["success"] is True
            job_id = launch_result["context"]["job_id"]

            # Access the cached module that flipbook.py imported
            import _flipbook_chunked as chunked
            job = chunked._flipbook_jobs[job_id]
            runner = job["runner"]

            # Step 1
            assert runner.step() is True
            progress1 = mod.get_flipbook_job(job_id)
            assert progress1["context"]["state"] == "running"
            assert progress1["context"]["progress"]["completed"] == 1

            # Step 2
            assert runner.step() is True
            progress2 = mod.get_flipbook_job(job_id)
            assert progress2["context"]["progress"]["completed"] == 2

            # Step 3
            assert runner.step() is True
            progress3 = mod.get_flipbook_job(job_id)
            assert progress3["context"]["progress"]["completed"] == 3

            # Step 4 — last step
            assert runner.step() is False  # terminal
            final = mod.get_flipbook_job(job_id)
            assert final["context"]["state"] == "completed"
            assert final["context"]["progress"]["completed"] == 4
            assert final["context"]["captured"] is True
            assert len(final["context"]["written_files"]) == 4

    def test_flipbook_chunked_cancellation(self, tmp_path: Path) -> None:
        """Cancel mid-sequence returns partial outputs."""
        mod = _load_script("houdini-render", "flipbook.py")
        out = str(tmp_path / "frame.$F4.jpg")
        settings = MagicMock()
        viewer = MagicMock()
        viewer.curViewport.return_value = MagicMock()
        viewer.flipbookSettings.return_value.stash.return_value = settings

        written_frames = []

        def _write_frame(vp, s):
            try:
                frame_path = s.output.call_args[0][0]
            except Exception:  # noqa: BLE001
                frame_path = str(tmp_path / "frame.0001.jpg")
            Path(frame_path).write_bytes(b"img")
            written_frames.append(frame_path)

        viewer.flipbook.side_effect = _write_frame
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.ui.paneTabOfType.return_value = viewer

        with patch.dict(sys.modules, {"hou": mock_hou}):
            launch_result = mod.flipbook(out, frame_range=[1, 10, 1])

            job_id = launch_result["context"]["job_id"]
            import _flipbook_chunked as chunked
            job = chunked._flipbook_jobs[job_id]
            runner = job["runner"]

            # Execute 3 frames
            for _ in range(3):
                assert runner.step() is True

            progress = mod.get_flipbook_job(job_id)
            assert progress["context"]["progress"]["completed"] == 3

            # Cancel
            cancel_result = mod.cancel_flipbook_job(job_id)
            assert cancel_result["success"] is True
            assert cancel_result["context"]["state"] == "cancelling"

            # Next step detects cancellation
            assert runner.step() is False
            final = mod.get_flipbook_job(job_id)
            assert final["context"]["state"] == "cancelled"
            assert final["context"]["captured"] is True
            assert len(final["context"]["written_files"]) == 3
            assert len(final["context"]["skipped_frames"]) == 7

    def test_flipbook_chunked_terminal_idempotence(self, tmp_path: Path) -> None:
        """step() after terminal is a no-op."""
        mod = _load_script("houdini-render", "flipbook.py")
        out = str(tmp_path / "frame.$F4.jpg")
        settings = MagicMock()
        viewer = MagicMock()
        viewer.curViewport.return_value = MagicMock()
        viewer.flipbookSettings.return_value.stash.return_value = settings

        def _write_frame(vp, s):
            try:
                frame_path = s.output.call_args[0][0]
            except Exception:  # noqa: BLE001
                frame_path = str(tmp_path / "frame.0001.jpg")
            Path(frame_path).write_bytes(b"img")

        viewer.flipbook.side_effect = _write_frame
        mock_hou = MagicMock()
        mock_hou.isUIAvailable.return_value = True
        mock_hou.ui.paneTabOfType.return_value = viewer

        with patch.dict(sys.modules, {"hou": mock_hou}):
            launch_result = mod.flipbook(out, frame_range=[1, 2, 1])

            job_id = launch_result["context"]["job_id"]
            import _flipbook_chunked as chunked
            job = chunked._flipbook_jobs[job_id]
            runner = job["runner"]

            # Run to completion
            assert runner.step() is True
            assert runner.step() is False  # terminal
            assert runner.is_terminal is True

            # Further steps are no-ops
            assert runner.step() is False
            assert runner.step() is False

            final = mod.get_flipbook_job(job_id)
            assert final["context"]["state"] == "completed"

    def test_flipbook_chunked_get_unknown_job(self) -> None:
        mod = _load_script("houdini-render", "flipbook.py")
        result = mod.get_flipbook_job("nonexistent-job-id")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_flipbook_chunked_cancel_unknown_job(self) -> None:
        mod = _load_script("houdini-render", "flipbook.py")
        result = mod.cancel_flipbook_job("nonexistent-job-id")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_flipbook_chunked_empty_sequence(self, tmp_path: Path) -> None:
        """A frame range with zero frames should fail validation."""
        mod = _load_script("houdini-render", "flipbook.py")
        mock_hou = MagicMock()

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.flipbook(
                str(tmp_path / "frame.$F4.jpg"),
                frame_range=[5, 1],  # end < start
            )

        assert result["success"] is False
        assert "end" in result["error"].lower() or "range" in result["error"].lower()


class TestRenderSettings:
    def test_get_render_settings_reports_raw_pattern_and_resolution_frame(self) -> None:
        mod = _load_script("houdini-render", "get_render_settings.py")
        pattern = "$HIP/renders/beauty.$F4.exr"
        current_frame = {"value": 1.0}
        output_parm = _scalar_parm(pattern)
        output_tuple = MagicMock()
        output_tuple.eval.side_effect = lambda: (
            "C:/show/shot/renders/beauty.{:04d}.exr".format(int(current_frame["value"])),
        )
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parm.side_effect = lambda name: output_parm if name == "vm_picture" else None
        rop.parmTuple.side_effect = lambda name: output_tuple if name == "vm_picture" else None
        mock_hou = MagicMock()
        mock_hou.frame.side_effect = lambda: current_frame["value"]
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            frame_1 = mod.get_render_settings("/out/mantra1")["context"]
            current_frame["value"] = 576.0
            frame_576 = mod.get_render_settings("/out/mantra1")["context"]

        assert frame_1["output_path"] == ["C:/show/shot/renders/beauty.0001.exr"]
        assert frame_1["output_path_pattern"] == pattern
        assert frame_1["output_path_resolution"] == {
            "frame": 1.0,
            "paths": ["C:/show/shot/renders/beauty.0001.exr"],
        }
        assert frame_576["output_path"] == ["C:/show/shot/renders/beauty.0576.exr"]
        assert frame_576["output_path_pattern"] == pattern
        assert frame_576["output_path_resolution"] == {
            "frame": 576.0,
            "paths": ["C:/show/shot/renders/beauty.0576.exr"],
        }

    def test_get_render_settings_reads_fields(self) -> None:
        mod = _load_script("houdini-render", "get_render_settings.py")
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: {
            "camera": _scalar_parm("/obj/cam1"),
            "vm_picture": _scalar_parm("/tmp/beauty.exr"),
            "res_overridex": _scalar_parm(1280),
            "res_overridey": _scalar_parm(720),
        }.get(n)
        mock_hou = MagicMock()
        mock_hou.frame.return_value = 1.0
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_render_settings("/out/mantra1")

        assert result["success"] is True
        assert result["context"]["camera"] == "/obj/cam1"
        assert result["context"]["output_path"] == "/tmp/beauty.exr"
        assert result["context"]["output_path_pattern"] == "/tmp/beauty.exr"
        assert result["context"]["output_path_resolution"] == {"frame": 1.0, "paths": ["/tmp/beauty.exr"]}
        assert result["context"]["resolution"] == [1280, 720]

    def test_set_render_settings_reports_unsupported(self) -> None:
        mod = _load_script("houdini-render", "set_render_settings.py")
        camera_parm = MagicMock()
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        # Only the camera parm exists; output_path parms are all missing.
        rop.parm.side_effect = lambda n: camera_parm if n == "camera" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.set_render_settings("/out/mantra1", camera="/obj/cam1", output_path="/tmp/x.exr")

        assert result["success"] is True
        camera_parm.set.assert_called_once_with("/obj/cam1")
        assert result["context"]["applied"]["camera"] == "/obj/cam1"
        assert "output_path" in result["context"]["unsupported"]


class TestRenderPassAuthoring:
    def test_mantra_component_presets_use_complete_light_path_expressions(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")

        assert mod.MANTRA_AOV_PRESETS["diffuse"]["source"] == "lpe:C<RD>.*L"
        assert mod.MANTRA_AOV_PRESETS["specular"]["source"] == "lpe:C<RG>.*[LO]"
        assert mod.MANTRA_AOV_PRESETS["transmission"]["source"] == "lpe:C<TG>.*[LO]"
        assert mod.MANTRA_AOV_PRESETS["volume"]["source"] == "lpe:CV.*L"

    def test_configure_aovs_adds_real_mantra_planes_and_deduplicates(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.configure_aovs("/out/mantra1", ["normal", "depth", "normal"])
            repeated = mod.configure_aovs("/out/mantra1", ["normal", "depth"])

        assert result["success"] is True
        assert [item["name"] for item in result["context"]["configured"]] == ["normal", "depth"]
        assert result["context"]["unsupported"] == []
        assert repeated["context"]["configured"] == []
        assert repeated["context"]["unsupported"] == []
        assert rop.aux_planes() == [
            {"variable": "N", "type": "unitvector", "channel": "normal"},
            {"variable": "Pz", "type": "float", "channel": "depth"},
        ]

    def test_configure_aovs_applies_h21_plane_processing_contract(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.configure_aovs("/out/mantra1", ["normal", "emission"])

        assert result["success"] is True
        assert rop.values["vm_quantize_plane1"] == "float"
        assert rop.values["vm_pfilter_plane1"] == "minmax omedian"
        assert rop.values["vm_sfilter_plane1"] == "alpha"
        assert rop.values["vm_quantize_plane2"] == "half"
        assert rop.values["vm_pfilter_plane2"] == ""
        assert rop.values["vm_sfilter_plane2"] == "fullopacity"

    def test_configure_aovs_removes_named_mantra_plane_and_compacts(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            mod.configure_aovs("/out/mantra1", ["normal", "depth", "worldpos"])
            result = mod.configure_aovs("/out/mantra1", ["depth", "missing", "depth"], action="remove")

        assert result["success"] is True
        assert result["context"]["configured"] == [
            {"name": "depth", "action": "removed", "source": "Pz", "channel": "depth"}
        ]
        assert result["context"]["unsupported"] == ["missing"]
        assert rop.aux_planes() == [
            {"variable": "N", "type": "unitvector", "channel": "normal"},
            {"variable": "P", "type": "vector", "channel": "worldpos"},
        ]

    def test_configure_aovs_remove_clears_all_matching_planes(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        rop.resize_aux(2)
        rop.values.update(
            {
                "vm_variable_plane1": "N",
                "vm_channel_plane1": "normal",
                "vm_variable_plane2": "N",
                "vm_channel_plane2": "normal_copy",
            }
        )
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.configure_aovs("/out/mantra1", ["normal"], action="remove")

        assert result["success"] is True
        assert rop.aux_planes() == []

    def test_configure_aovs_unknown_remove_never_matches_empty_plane_field(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        rop.resize_aux(1)
        rop.values["vm_variable_plane1"] = "custom_export"
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.configure_aovs("/out/mantra1", ["missing"], action="remove")

        assert result["success"] is True
        assert result["context"]["unsupported"] == ["missing"]
        assert rop.values["vm_numaux"] == 1

    def test_configure_aovs_rolls_back_new_plane_when_parameter_write_fails(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        rop.set_failures.add("vm_channel_plane1")
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.configure_aovs("/out/mantra1", ["normal"])

        assert result["success"] is False
        assert rop.values["vm_numaux"] == 0

    def test_configure_aovs_rolls_back_all_planes_when_later_write_fails(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        rop.set_failures.add("vm_channel_plane2")
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.configure_aovs("/out/mantra1", ["normal", "depth"])

        assert result["success"] is False
        assert rop.values["vm_numaux"] == 0

    def test_configure_aovs_rejects_unknown_action_without_mutation(self) -> None:
        mod = _load_script("houdini-render", "configure_aovs.py")
        rop = _FakeMantraRop()
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.configure_aovs("/out/mantra1", ["normal"], action="replace")

        assert result["success"] is False
        assert rop.values["vm_numaux"] == 0

    def test_create_render_layer_clones_mantra_with_masks_and_output(self) -> None:
        mod = _load_script("houdini-render", "create_render_layer.py")
        out = _FakeOutNetwork()
        source = _FakeMantraRop("/out/mantra_base")
        source.values["vm_picture"] = "/renders/base.$F4.exr"
        out.add(source)
        mock_hou = _fake_hou_for_out(out)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_render_layer(
                "solar_fx",
                parent_path="/out",
                source_rop_path="/out/mantra_base",
                output_path="/renders/solar_fx.$F4.exr",
                candidate_objects="/obj/SolarFX*",
                force_objects="/obj/SunCorona",
                matte_objects="/obj/planets/*",
                exclude_objects="/obj/labels/*",
                phantom_objects="/obj/holdouts/*",
                aovs=["normal", "depth"],
            )

        assert result["success"] is True
        layer = out.node("solar_fx")
        assert layer is not None
        assert layer.values["vm_picture"] == "/renders/solar_fx.$F4.exr"
        assert layer.values["vobject"] == "/obj/SolarFX*"
        assert layer.values["forceobject"] == "/obj/SunCorona"
        assert layer.values["matte_objects"] == "/obj/planets/*"
        assert layer.values["excludeobject"] == "/obj/labels/*"
        assert layer.values["phantom_objects"] == "/obj/holdouts/*"
        assert layer.aux_planes() == [
            {"variable": "N", "type": "unitvector", "channel": "normal"},
            {"variable": "Pz", "type": "float", "channel": "depth"},
        ]
        assert source.values["vm_picture"] == "/renders/base.$F4.exr"
        assert result["context"]["node"]["type"] == "ifd"

    def test_create_render_layer_removes_partial_clone_when_required_parm_is_missing(self) -> None:
        mod = _load_script("houdini-render", "create_render_layer.py")
        out = _FakeOutNetwork()
        source = _FakeMantraRop("/out/mantra_base")
        source.values.pop("matte_objects")
        out.add(source)
        mock_hou = _fake_hou_for_out(out)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_render_layer(
                "solar_fx",
                parent_path="/out",
                source_rop_path="/out/mantra_base",
                output_path="/renders/solar_fx.$F4.exr",
                matte_objects="/obj/planets/*",
            )

        assert result["success"] is False
        assert out.node("solar_fx") is None
        assert out.node("mantra_base") is source

    def test_create_render_layer_rejects_missing_output_before_cloning(self) -> None:
        mod = _load_script("houdini-render", "create_render_layer.py")
        out = _FakeOutNetwork()
        source = _FakeMantraRop("/out/mantra_base")
        out.add(source)
        mock_hou = _fake_hou_for_out(out)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_render_layer(
                "solar_fx",
                parent_path="/out",
                source_rop_path="/out/mantra_base",
            )

        assert result["success"] is False
        assert set(out.children) == {"mantra_base"}

    def test_create_render_layer_rejects_source_output_path_before_cloning(self) -> None:
        mod = _load_script("houdini-render", "create_render_layer.py")
        out = _FakeOutNetwork()
        source = _FakeMantraRop("/out/mantra_base")
        source.values["vm_picture"] = "/renders/shared.$F4.exr"
        out.add(source)
        mock_hou = _fake_hou_for_out(out)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_render_layer(
                "solar_fx",
                parent_path="/out",
                source_rop_path="/out/mantra_base",
                output_path="/renders/shared.$F4.exr",
            )

        assert result["success"] is False
        assert set(out.children) == {"mantra_base"}

    def test_create_render_layer_rejects_expanded_variable_alias_before_cloning(self) -> None:
        mod = _load_script("houdini-render", "create_render_layer.py")
        out = _FakeOutNetwork()
        source = _FakeMantraRop("/out/mantra_base")
        source.values["vm_picture"] = "$HIP/render/shared.$F4.exr"
        out.add(source)
        mock_hou = _fake_hou_for_out(out)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_render_layer(
                "solar_fx",
                parent_path="/out",
                source_rop_path="/out/mantra_base",
                output_path="C:/show/shot/render/shared.$F4.exr",
            )

        assert result["success"] is False
        assert set(out.children) == {"mantra_base"}

    def test_create_render_layer_removes_clone_when_requested_aov_is_unsupported(self) -> None:
        mod = _load_script("houdini-render", "create_render_layer.py")
        out = _FakeOutNetwork()
        source = _FakeMantraRop("/out/mantra_base")
        out.add(source)
        mock_hou = _fake_hou_for_out(out)

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.create_render_layer(
                "solar_fx",
                parent_path="/out",
                source_rop_path="/out/mantra_base",
                output_path="/renders/solar_fx.$F4.exr",
                aovs=["normal", "cryptomatte"],
            )

        assert result["success"] is False
        assert set(out.children) == {"mantra_base"}

    def test_manage_takes_create_uses_root_child_take_api(self) -> None:
        mod = _load_script("houdini-render", "manage_takes.py")
        takes = _FakeTakes()
        mock_hou = MagicMock()
        mock_hou.takes = takes

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.manage_takes("create", take_name="solar_fx")

        assert result["success"] is True
        assert takes.findTake("solar_fx").parent() is takes.rootTake()
        assert takes.currentTake() is takes.rootTake()

    def test_manage_takes_adds_and_removes_override_without_changing_current_take(self) -> None:
        mod = _load_script("houdini-render", "manage_takes.py")
        takes = _FakeTakes()
        variant = takes.add("solar_fx")
        parm_tuple = MagicMock()
        node = _node("/out/mantra1", "mantra1", "ifd")
        node.parmTuple.return_value = parm_tuple
        mock_hou = MagicMock()
        mock_hou.takes = takes
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            added = mod.manage_takes(
                "add_override",
                take_name="solar_fx",
                node_path="/out/mantra1",
                parm_name="vm_picture",
            )
            removed = mod.manage_takes(
                "remove_override",
                take_name="solar_fx",
                node_path="/out/mantra1",
                parm_name="vm_picture",
            )

        assert added["success"] is True
        assert removed["success"] is True
        assert variant.hasParmTuple(parm_tuple) is False
        assert takes.currentTake().name() == "main"

    def test_manage_takes_adds_override_value_inside_target_take(self) -> None:
        mod = _load_script("houdini-render", "manage_takes.py")
        takes = _FakeTakes()
        variant = takes.add("solar_fx")
        parm_tuple = MagicMock()

        def assert_target_current(_values):
            assert takes.currentTake() is variant

        parm_tuple.set.side_effect = assert_target_current
        node = _node("/out/mantra1", "mantra1", "ifd")
        node.parmTuple.return_value = parm_tuple
        mock_hou = MagicMock()
        mock_hou.takes = takes
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.manage_takes(
                "add_override",
                take_name="solar_fx",
                node_path="/out/mantra1",
                parm_name="vm_picture",
                value="/renders/solar_fx.$F4.exr",
            )

        assert result["success"] is True
        assert result["context"]["value_applied"] is True
        assert variant.hasParmTuple(parm_tuple) is True
        parm_tuple.set.assert_called_once_with(("/renders/solar_fx.$F4.exr",))
        assert takes.currentTake().name() == "main"

    def test_manage_takes_rolls_back_new_override_when_value_write_fails(self) -> None:
        mod = _load_script("houdini-render", "manage_takes.py")
        takes = _FakeTakes()
        variant = takes.add("solar_fx")
        parm_tuple = MagicMock()
        parm_tuple.set.side_effect = RuntimeError("value rejected")
        node = _node("/out/mantra1", "mantra1", "ifd")
        node.parmTuple.return_value = parm_tuple
        mock_hou = MagicMock()
        mock_hou.takes = takes
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.manage_takes(
                "add_override",
                take_name="solar_fx",
                node_path="/out/mantra1",
                parm_name="vm_picture",
                value="/renders/solar_fx.$F4.exr",
            )

        assert result["success"] is False
        assert variant.hasParmTuple(parm_tuple) is False
        assert takes.currentTake().name() == "main"

    def test_manage_takes_restores_current_take_when_override_update_fails(self) -> None:
        mod = _load_script("houdini-render", "manage_takes.py")
        takes = _FakeTakes()
        variant = takes.add("solar_fx")
        variant.addParmTuple = MagicMock(side_effect=RuntimeError("write failed"))
        node = _node("/out/mantra1", "mantra1", "ifd")
        node.parmTuple.return_value = MagicMock()
        mock_hou = MagicMock()
        mock_hou.takes = takes
        mock_hou.node.return_value = node

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.manage_takes(
                "add_override",
                take_name="solar_fx",
                node_path="/out/mantra1",
                parm_name="vm_picture",
            )

        assert result["success"] is False
        assert takes.currentTake() is takes.rootTake()


class TestRenderExecution:
    def test_solaris_ignore_inputs_uses_rop_render_contract(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        rop = _node("/stage/karma", "karma", "usdrender_rop")
        execute = MagicMock()
        rop.parm.side_effect = lambda name: execute if name == "execute" else None
        rop.parmTuple.return_value = None

        applied_range, execution_mode = mod.render_node(
            rop,
            [1, 24, 2],
            ignore_inputs=True,
        )

        assert applied_range == [1.0, 24.0]
        assert execution_mode == "render"
        execute.pressButton.assert_not_called()
        rop.render.assert_called_once_with(
            verbose=False,
            frame_range=(1.0, 24.0, 2.0),
            ignore_inputs=True,
        )

    def test_solaris_ignore_inputs_never_falls_back_to_execute_button(self) -> None:
        mod = _load_script("houdini-render", "_render_common.py")
        rop = _node("/stage/karma", "karma", "usdrender_rop")
        execute = MagicMock()
        rop.parm.side_effect = lambda name: execute if name == "execute" else None
        rop.parmTuple.return_value = None
        rop.render.side_effect = TypeError("ignore_inputs is unsupported")

        with pytest.raises(TypeError, match="ignore_inputs is unsupported"):
            mod.render_node(rop, [1, 24, 2], ignore_inputs=True)

        execute.pressButton.assert_not_called()
        assert rop.render.call_count == 2
        assert all(call.kwargs["ignore_inputs"] is True for call in rop.render.call_args_list)

    def test_background_render_launches_isolated_hython(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        hip = tmp_path / "scene.hip"
        hip.write_bytes(b"hip")
        hython = tmp_path / ("hython.exe" if mod.os.name == "nt" else "hython")
        hython.write_bytes(b"exe")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = str(hip)
        mock_hou.hipFile.hasUnsavedChanges.return_value = False
        process = MagicMock(pid=4321)

        with patch.dict(mod.os.environ, {"PARENT_ONLY": "keep"}, clear=True), patch.object(
            mod.sys, "executable", str(tmp_path / "houdini.exe")
        ), patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod.subprocess, "Popen", return_value=process
        ) as popen:
            job = mod.launch_background_render(
                mock_hou,
                "/stage/karma",
                [1, 100000, 1],
                str(tmp_path / "beauty.$F4.exr"),
                ignore_inputs=True,
                job_kind="rop_chain",
            )
            assert "DCC_MCP_BACKGROUND_RENDER" not in mod.os.environ

        status = json.loads((tmp_path / "dcc-mcp-houdini-render-jobs" / job["job_id"] / "status.json").read_text())
        assert job["pid"] == 4321
        assert status["state"] == "queued"
        assert "pid" not in status
        assert "expected_outputs" not in status
        assert "output_snapshot" not in status
        mock_hou.text.expandStringAtFrame.assert_not_called()
        assert popen.call_args.kwargs["cwd"].endswith(job["job_id"])
        assert popen.call_args.args[0][0] == str(hython)
        assert json.loads(popen.call_args.args[0][-1]) is True
        assert popen.call_args.kwargs["env"]["PARENT_ONLY"] == "keep"
        assert popen.call_args.kwargs["env"]["DCC_MCP_BACKGROUND_RENDER"] == "1"
        assert popen.call_args.kwargs["start_new_session"] is (mod.os.name != "nt")
        assert mod._PROCESS_HANDLES[job["job_id"]] is process
        assert status["ignore_inputs"] is True
        assert status["job_kind"] == "rop_chain"
        mock_hou.hipFile.saveAsBackup.assert_not_called()

    def test_background_render_gui_rejects_dirty_hip_without_saving(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        hip = tmp_path / "scene.hip"
        hip.write_bytes(b"hip")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = str(hip)
        mock_hou.hipFile.hasUnsavedChanges.return_value = True
        mock_hou.isUIAvailable.return_value = True

        with patch.object(mod.subprocess, "Popen") as popen, pytest.raises(ValueError, match="unsaved changes"):
            mod.launch_background_render(mock_hou, "/out/mantra1", [1, 2, 1], "beauty.$F4.exr")

        mock_hou.hipFile.save.assert_not_called()
        mock_hou.hipFile.saveAsBackup.assert_not_called()
        popen.assert_not_called()

    def test_background_render_gui_rejects_unknown_dirty_state(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        hip = tmp_path / "scene.hip"
        hip.write_bytes(b"hip")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = str(hip)
        mock_hou.hipFile.hasUnsavedChanges.side_effect = RuntimeError("probe failed")
        mock_hou.isUIAvailable.return_value = True

        with patch.object(mod.subprocess, "Popen") as popen, pytest.raises(ValueError, match="dirty state"):
            mod.launch_background_render(mock_hou, "/out/mantra1", [1, 2, 1], "beauty.$F4.exr")

        mock_hou.hipFile.save.assert_not_called()
        mock_hou.hipFile.saveAsBackup.assert_not_called()
        popen.assert_not_called()

    def test_background_render_headless_launches_from_owned_snapshot_without_saving_source(
        self, tmp_path: Path
    ) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        hip = tmp_path / "scene.hip"
        hip.write_bytes(b"source")
        hython = tmp_path / ("hython.exe" if mod.os.name == "nt" else "hython")
        hython.write_bytes(b"exe")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = str(hip)
        mock_hou.hipFile.hasUnsavedChanges.return_value = True
        mock_hou.isUIAvailable.return_value = False
        backup_env = {}
        mock_hou.getenv.return_value = None
        mock_hou.putenv.side_effect = lambda name, value: backup_env.__setitem__(name, value)
        mock_hou.unsetenv.side_effect = lambda name: backup_env.pop(name, None)

        def save_snapshot():
            snapshot = Path(backup_env["HOUDINI_BACKUP_DIR"]) / "scene_bak1.hip"
            snapshot.write_bytes(b"snapshot")
            return str(snapshot)

        mock_hou.hipFile.saveAsBackup.side_effect = save_snapshot
        mock_hou.hipFile.save.side_effect = lambda: hip.write_bytes(b"overwritten")

        with patch.object(mod.sys, "executable", str(tmp_path / "houdini.exe")), patch.object(
            mod.tempfile, "gettempdir", return_value=str(tmp_path)
        ), patch.object(mod.subprocess, "Popen", return_value=MagicMock(pid=4321)) as popen:
            job = mod.launch_background_render(mock_hou, "/out/geometry1", [1, 2, 1], "cache.$F4.bgeo.sc")

        mock_hou.hipFile.hasUnsavedChanges.assert_not_called()
        mock_hou.hipFile.save.assert_not_called()
        mock_hou.hipFile.saveAsBackup.assert_called_once_with()
        mock_hou.hipFile.setName.assert_not_called()
        assert hip.read_bytes() == b"source"
        status = json.loads((tmp_path / "dcc-mcp-houdini-render-jobs" / job["job_id"] / "status.json").read_text())
        snapshot = Path(status["hip_path"])
        assert snapshot.parent == tmp_path / "dcc-mcp-houdini-render-jobs" / job["job_id"]
        assert snapshot.read_bytes() == b"snapshot"
        assert status["source_hip_path"] == str(hip)
        assert status["hip_snapshot_owned"] is True
        assert Path(popen.call_args.args[0][2]) == snapshot
        popen.assert_called_once()

    def test_background_render_headless_rejects_failed_snapshot(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        hip = tmp_path / "scene.hip"
        hip.write_bytes(b"hip")
        hython = tmp_path / ("hython.exe" if mod.os.name == "nt" else "hython")
        hython.write_bytes(b"exe")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = str(hip)
        mock_hou.getenv.return_value = None
        mock_hou.hipFile.saveAsBackup.side_effect = RuntimeError("snapshot failed")
        mock_hou.isUIAvailable.return_value = False

        with patch.object(mod.sys, "executable", str(tmp_path / "houdini.exe")), patch.object(
            mod.tempfile, "gettempdir", return_value=str(tmp_path)
        ), patch.object(mod.subprocess, "Popen") as popen, pytest.raises(ValueError, match="snapshot"):
            mod.launch_background_render(mock_hou, "/out/geometry1", [1, 2, 1], "cache.$F4.bgeo.sc")

        mock_hou.hipFile.save.assert_not_called()
        mock_hou.hipFile.saveAsBackup.assert_called_once_with()
        popen.assert_not_called()

    def test_background_render_headless_rejects_missing_hip(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = str(tmp_path / "untitled.hip")
        mock_hou.isUIAvailable.return_value = False

        with pytest.raises(ValueError, match="requires.*saved"):
            mod.launch_background_render(mock_hou, "/out/mantra1", None, None)

        mock_hou.hipFile.save.assert_not_called()

    def test_cancel_background_render_is_idempotent(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "a" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        status_path = job_dir / "status.json"
        status_path.write_text(json.dumps({"job_id": job_id, "state": "running"}), encoding="utf-8")
        process = MagicMock(pid=4321)
        process.poll.side_effect = [None, 0, 0]
        mod._PROCESS_HANDLES[job_id] = process

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod, "_terminate_process_tree"
        ) as terminate:
            first = mod.cancel_render_job(job_id)
            second = mod.cancel_render_job(job_id)

        assert first["state"] == "cancelled"
        assert first["cancel_requested"] is True
        assert second["state"] == "cancelled"
        assert second["cancel_requested"] is False
        terminate.assert_called_once_with(process)
        assert job_id not in mod._PROCESS_HANDLES

    def test_cancel_background_render_removes_only_job_owned_hip_snapshot(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "8" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        snapshot = job_dir / "scene_bak1.hip"
        snapshot.write_bytes(b"snapshot")
        source = tmp_path / "scene.hip"
        source.write_bytes(b"source")
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "running",
                    "hip_path": str(snapshot),
                    "source_hip_path": str(source),
                    "hip_snapshot_owned": True,
                }
            ),
            encoding="utf-8",
        )
        process = MagicMock(pid=4321)
        process.poll.side_effect = [None, 0]
        mod._PROCESS_HANDLES[job_id] = process

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod, "_terminate_process_tree"
        ):
            result = mod.cancel_render_job(job_id)

        assert result["state"] == "cancelled"
        assert not snapshot.exists()
        assert source.read_bytes() == b"source"

    def test_terminal_status_never_removes_snapshot_path_outside_owned_job_directory(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "7" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        outside = tmp_path / "scene.hip"
        outside.write_bytes(b"source")
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "completed",
                    "hip_path": str(outside),
                    "hip_snapshot_owned": True,
                }
            ),
            encoding="utf-8",
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            mod.read_render_job(job_id)

        assert outside.read_bytes() == b"source"

    def test_concurrent_cancel_terminates_owned_process_once(self, tmp_path: Path) -> None:
        from concurrent.futures import ThreadPoolExecutor

        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "9" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "status.json").write_text(
            json.dumps({"job_id": job_id, "state": "running"}),
            encoding="utf-8",
        )
        return_code = {"value": None}
        process = MagicMock(pid=4321)
        process.poll.side_effect = lambda: return_code["value"]
        mod._PROCESS_HANDLES[job_id] = process

        def terminate(_process):
            return_code["value"] = 0

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod, "_terminate_process_tree", side_effect=terminate
        ) as terminate_mock, ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: mod.cancel_render_job(job_id), range(2)))

        assert [result["state"] for result in results] == ["cancelled", "cancelled"]
        assert sorted(result["cancel_requested"] for result in results) == [False, True]
        terminate_mock.assert_called_once_with(process)
        assert job_id not in mod._PROCESS_HANDLES

    def test_cancel_never_uses_unowned_status_pid(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "b" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "status.json").write_text(
            json.dumps({"job_id": job_id, "state": "running", "pid": 999999}), encoding="utf-8"
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod, "_terminate_process_tree"
        ) as terminate:
            result = mod.cancel_render_job(job_id)

        assert result["state"] == "running"
        assert result["cancel_requested"] is False
        assert result["owned_by_current_process"] is False
        terminate.assert_not_called()

    def test_cancel_unknown_job_does_not_terminate_any_process(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod, "_terminate_process_tree"
        ) as terminate, pytest.raises(FileNotFoundError):
            mod.cancel_render_job("e" * 32)

        terminate.assert_not_called()

    def test_get_render_job_reconciles_exited_owned_worker(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "c" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "status.json").write_text(
            json.dumps({"job_id": job_id, "state": "running", "started_at": 10.0}), encoding="utf-8"
        )
        process = MagicMock(pid=4321)
        process.poll.return_value = 7
        mod._PROCESS_HANDLES[job_id] = process

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod.time, "time", return_value=15.0
        ):
            result = mod.read_render_job(job_id)

        assert result["state"] == "interrupted"
        assert result["return_code"] == 7
        assert result["elapsed_secs"] == 5.0
        assert result["owned_by_current_process"] is False

    def test_get_render_job_derives_progress_and_hides_internal_details(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "f" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        outputs = [job_dir / "beauty.{:04d}.exr".format(frame) for frame in range(1, 31)]
        for output in outputs[:25]:
            output.write_bytes(b"new")
        snapshot = {str(output): {"mtime_ns": 1, "size": 1} for output in outputs[:25]}
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "running",
                    "started_at": 10.0,
                    "expected_outputs": [str(path) for path in outputs],
                    "output_snapshot": snapshot,
                    "written_files": [],
                }
            ),
            encoding="utf-8",
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod.time, "time", return_value=40.0
        ):
            summary = mod.read_render_job(job_id)
            details = mod.read_render_job(job_id, include_details=True)

        assert summary["completed"] == 24
        assert summary["total"] == 30
        assert summary["progress"] == pytest.approx(24.0 / 30.0)
        assert summary["elapsed_secs"] == 30.0
        assert summary["eta_secs"] == 7.5
        assert summary["written_file_count"] == 24
        assert summary["recent_written_files"] == [str(output) for output in outputs[14:24]]
        assert "expected_outputs" not in summary
        assert "output_snapshot" not in summary
        assert details["expected_outputs"] == [str(path) for path in outputs]
        assert details["output_snapshot"] == snapshot
        assert details["written_files"] == [str(output) for output in outputs[:24]]

    def test_get_render_job_does_not_complete_latest_output_while_worker_runs(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "1" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        outputs = [job_dir / "beauty.{:04d}.exr".format(frame) for frame in range(1, 4)]
        for output, mtime_ns in zip(outputs, (3_000_000_000, 2_000_000_000, 1_000_000_000)):
            output.write_bytes(b"render output")
            os.utime(output, ns=(mtime_ns, mtime_ns))
        status_path = job_dir / "status.json"
        status = {
            "job_id": job_id,
            "state": "running",
            "expected_outputs": [str(output) for output in outputs],
            "output_snapshot": {},
        }
        status_path.write_text(json.dumps(status), encoding="utf-8")
        process = MagicMock(pid=4321)
        process.poll.return_value = None
        mod._PROCESS_HANDLES[job_id] = process

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            running = mod.read_render_job(job_id)
            status["state"] = "completed"
            status["written_files"] = [str(output) for output in outputs]
            status_path.write_text(json.dumps(status), encoding="utf-8")
            completed = mod.read_render_job(job_id)

        assert running["completed"] == 2
        assert running["total"] == 3
        assert running["progress"] == pytest.approx(2.0 / 3.0)
        assert running["recent_written_files"] == [str(output) for output in outputs[:2]]
        assert completed["completed"] == 3
        assert completed["progress"] == 1.0

    def test_get_render_job_completes_legacy_terminal_job_without_written_files(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "3" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        outputs = [job_dir / "beauty.{:04d}.exr".format(frame) for frame in range(1, 4)]
        for output in outputs:
            output.write_bytes(b"completed output")
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "completed",
                    "expected_outputs": [str(output) for output in outputs],
                    "output_snapshot": {},
                }
            ),
            encoding="utf-8",
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            result = mod.read_render_job(job_id)

        assert result["completed"] == 3
        assert result["total"] == 3
        assert result["progress"] == 1.0
        assert result["written_file_count"] == 3
        assert result["recent_written_files"] == [str(output) for output in outputs]

    def test_get_render_job_does_not_claim_unverified_failed_outputs(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "2" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        outputs = [job_dir / "beauty.{:04d}.exr".format(frame) for frame in range(1, 5)]
        for output in outputs[:2]:
            output.write_bytes(b"completed output")
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "failed",
                    "expected_outputs": [str(output) for output in outputs],
                    "output_snapshot": {},
                    "written_files": [],
                    "output_verification": {"state": "pending"},
                }
            ),
            encoding="utf-8",
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            result = mod.read_render_job(job_id)

        assert result["completed"] == 0
        assert result["total"] == 4
        assert result["progress"] == 0.0
        assert result["written_file_count"] == 0
        assert result["recent_written_files"] == []

    @pytest.mark.parametrize("state", ["failed", "cancelled", "interrupted"])
    def test_get_render_job_keeps_latest_legacy_terminal_output_pending(self, tmp_path: Path, state: str) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = {"failed": "f", "cancelled": "c", "interrupted": "e"}[state] * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        outputs = [job_dir / "beauty.{:04d}.exr".format(frame) for frame in range(1, 4)]
        for output in outputs:
            output.write_bytes(b"possibly incomplete output")
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": state,
                    "expected_outputs": [str(output) for output in outputs],
                    "output_snapshot": {},
                }
            ),
            encoding="utf-8",
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            result = mod.read_render_job(job_id)

        assert result["completed"] == 2
        assert result["total"] == 3
        assert result["progress"] == pytest.approx(2.0 / 3.0)
        assert result["recent_written_files"] == [str(output) for output in outputs[:2]]

    def test_cancel_complete_race_preserves_completed_state(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "d" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        status_path = job_dir / "status.json"
        status_path.write_text(json.dumps({"job_id": job_id, "state": "running"}), encoding="utf-8")
        process = MagicMock(pid=4321)
        process.poll.return_value = None
        mod._PROCESS_HANDLES[job_id] = process

        def finish(_process):
            status_path.write_text(
                json.dumps({"job_id": job_id, "state": "completed", "written_files": ["beauty.exr"]}),
                encoding="utf-8",
            )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
            mod, "_terminate_process_tree", side_effect=finish
        ):
            result = mod.cancel_render_job(job_id)

        assert result["state"] == "completed"
        assert result["written_files"] == ["beauty.exr"]
        assert result["cancel_requested"] is True
        assert job_id not in mod._PROCESS_HANDLES

    def test_get_render_job_returns_bounded_terminal_summary(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "8" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        output = job_dir / "beauty.0001.exr"
        output.write_bytes(b"new")
        written_files = [str(job_dir / "beauty.{:04d}.exr".format(frame)) for frame in range(12)]
        status = {
            "job_id": job_id,
            "state": "failed",
            "started_at": 10.0,
            "finished_at": 20.0,
            "expected_outputs": [str(output)],
            "output_snapshot": {},
            "written_files": written_files,
            "error": "ROP failed\n" + "x" * 1000,
            "traceback": "large traceback" * 100,
        }
        (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            summary = mod.read_render_job(job_id)
            details = mod.read_render_job(job_id, include_details=True)

        assert summary["written_file_count"] == 12
        assert summary["recent_written_files"] == written_files[-10:]
        assert summary["error_summary"].startswith("ROP failed")
        assert len(summary["error_summary"]) <= 500
        assert summary["warning_count"] == 0
        assert summary["recent_warnings"] == []
        assert summary["eta_secs"] is None
        for internal in ("expected_outputs", "output_snapshot", "written_files", "traceback", "error"):
            assert internal not in summary
        assert details["written_files"] == written_files
        assert details["traceback"] == status["traceback"]
        assert details["error"] == status["error"]

    def test_get_render_job_bounds_warnings_in_default_summary(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "6" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        shared_prefix = "x" * 600
        warnings = [
            shared_prefix + " first",
            shared_prefix + " second",
            *["warning {}\n{}".format(index, "x" * 600) for index in range(10)],
        ]
        (job_dir / "status.json").write_text(
            json.dumps({"job_id": job_id, "state": "failed", "warnings": warnings}),
            encoding="utf-8",
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            summary = mod.read_render_job(job_id)
            details = mod.read_render_job(job_id, include_details=True)

        assert summary["warning_count"] == 12
        assert len(summary["recent_warnings"]) == 10
        assert all("\n" not in warning and len(warning) <= 500 for warning in summary["recent_warnings"])
        assert details["warnings"] == warnings

    def test_get_render_job_surfaces_bounded_stderr_warnings(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "5" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        stderr = job_dir / "stderr.log"
        stderr_warnings = [
            "Property 'vblur' cannot be specified on a per-instance at this time.",
            "Pixel filter 'minmax' - Mode idcover requires PrimId channel",
        ]
        stderr_lines = [warning for warning in stderr_warnings for _ in range(2)]
        stderr_limit = mod.read_render_job.__globals__["_STDERR_TAIL_BYTES"]
        stderr.write_text(
            "outside bounded tail\n{}\n{}\n".format(
                "x" * (stderr_limit + 1),
                "\n".join(stderr_lines),
            ),
            encoding="utf-8",
        )
        (job_dir / "status.json").write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "state": "running",
                    "stderr_path": str(stderr),
                    "warnings": ["worker warning", stderr_warnings[0]],
                }
            ),
            encoding="utf-8",
        )

        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            summary = mod.read_render_job(job_id)
            details = mod.read_render_job(job_id, include_details=True)

        expected_warnings = ["worker warning", *stderr_warnings]
        assert summary["warning_count"] == len(expected_warnings)
        assert summary["recent_warnings"] == expected_warnings
        assert all(len(warning) <= 500 for warning in summary["recent_warnings"])
        assert details["warning_count"] == len(expected_warnings)
        assert details["warnings"] == expected_warnings

    def test_get_render_job_tool_forwards_include_details(self) -> None:
        mod = _load_script("houdini-render", "get_render_job.py")
        status = {"job_id": "7" * 32, "state": "running"}

        with patch.object(mod, "read_render_job", return_value=status) as read:
            result = mod.get_render_job("7" * 32, include_details=True)

        assert result["success"] is True
        read.assert_called_once_with("7" * 32, include_details=True)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree regression")
    def test_cancel_render_job_survives_external_command_failure(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "6" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        (job_dir / "status.json").write_text(
            json.dumps({"job_id": job_id, "state": "running"}),
            encoding="utf-8",
        )
        child_pid_path = tmp_path / "child.pid"
        child_code = "import time; time.sleep(60)"
        parent_code = (
            "import pathlib, subprocess, sys, time; "
            "child = subprocess.Popen([sys.executable, '-c', {!r}]); "
            "pathlib.Path({!r}).write_text(str(child.pid), encoding='utf-8'); "
            "time.sleep(60)"
        ).format(child_code, str(child_pid_path))
        process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", parent_code],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        mod._PROCESS_HANDLES[job_id] = process
        child_pid = None
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not child_pid_path.is_file():
                time.sleep(0.02)
            assert child_pid_path.is_file()
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))

            with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)), patch.object(
                mod.subprocess, "run", side_effect=OSError("cannot create helper process")
            ):
                first = mod.cancel_render_job(job_id)
                second = mod.cancel_render_job(job_id)

            assert first["state"] == "cancelled"
            assert first["cancel_requested"] is True
            assert second["state"] == "cancelled"
            assert second["cancel_requested"] is False
            assert job_id not in mod._PROCESS_HANDLES
            assert process.poll() is not None
            assert _wait_for_windows_process_exit(child_pid, timeout_secs=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if child_pid is not None and not _wait_for_windows_process_exit(child_pid, timeout_secs=0):
                subprocess.run(  # noqa: S603
                    ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

    def test_terminate_process_tree_uses_process_group_on_posix(self) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        process = MagicMock(pid=4321)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("hython", 2), 0]

        with patch.object(mod.os, "name", "posix"), patch.object(mod.os, "killpg", create=True) as killpg:
            mod._terminate_process_tree(process)

        assert killpg.call_args_list[0].args == (4321, mod._SIGTERM)
        assert killpg.call_args_list[1].args == (4321, mod._SIGKILL)

    def test_background_worker_restores_source_hip_name_and_removes_owned_snapshot(self, tmp_path: Path) -> None:
        mod = _load_render_worker()
        source = tmp_path / "source.hip"
        source.write_bytes(b"source")
        snapshot = tmp_path / "snapshot.hip"
        snapshot.write_bytes(b"snapshot")
        output = tmp_path / "beauty.0001.exr"
        stdout = tmp_path / "stdout.log"
        stderr = tmp_path / "stderr.log"
        stdout.write_text("", encoding="utf-8")
        stderr.write_text("", encoding="utf-8")
        status_path = tmp_path / "status.json"
        status_path.write_text(
            json.dumps(
                {
                    "state": "queued",
                    "job_kind": "render",
                    "stdout_path": str(stdout),
                    "stderr_path": str(stderr),
                    "source_hip_path": str(source),
                    "hip_snapshot_owned": True,
                    "expected_outputs": [str(output)],
                    "output_snapshot": {},
                }
            ),
            encoding="utf-8",
        )
        rop = _node("/out/mantra1", "mantra1", "ifd")
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        def render(_rop, _frame_range):
            output.write_bytes(b"new")
            return [1.0, 1.0], "render"

        argv = [
            "_render_worker.py",
            str(snapshot),
            "/out/mantra1",
            json.dumps([1, 1, 1]),
            str(status_path),
            json.dumps(str(tmp_path / "beauty.$F4.exr")),
            "false",
        ]
        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(mod.sys, "argv", argv), patch.object(
            mod, "render_node", side_effect=render
        ):
            mod.main()

        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert status["state"] == "completed"
        mock_hou.hipFile.load.assert_called_once_with(str(snapshot), suppress_save_prompt=True)
        mock_hou.hipFile.setName.assert_called_once_with(str(source))
        assert not snapshot.exists()
        assert source.read_bytes() == b"source"

    def test_background_worker_rejects_partial_requested_outputs(self, tmp_path: Path) -> None:
        stale = tmp_path / "beauty.0001.exr"
        stale.write_bytes(b"stale")
        outside = tmp_path / "beauty.0002.exr"

        def render(_rop, _frame_range):
            outside.write_bytes(b"new but not requested")
            (tmp_path / "beauty.0005.exr").write_bytes(b"new requested frame")
            return [1.0, 9.0], "execute"

        status = _run_render_worker(
            tmp_path,
            [1, 9, 4],
            [tmp_path / "beauty.0001.exr", tmp_path / "beauty.0005.exr", tmp_path / "beauty.0009.exr"],
            {str(stale): {"mtime_ns": stale.stat().st_mtime_ns, "size": stale.stat().st_size}},
            render,
        )
        assert status["state"] == "failed"
        assert status["written_files"] == [str(tmp_path / "beauty.0005.exr")]
        assert status["output_verification"] == {
            "state": "partial",
            "expected_output_count": 3,
            "written_file_count": 1,
        }
        assert status["error"] == "Render produced 1 of 3 expected outputs"

    def test_get_render_job_counts_new_output_without_explicit_frame_range(self, tmp_path: Path) -> None:
        output = tmp_path / "beauty.0001.exr"

        def render(_rop, _frame_range):
            output.write_bytes(b"new output")
            return None, "render"

        status = _run_render_worker(tmp_path, None, [], {}, render)

        assert status["state"] == "completed"
        assert status["expected_outputs"] == []
        assert status["written_files"] == [str(output)]
        assert status["output_verification"] == {
            "state": "verified",
            "expected_output_count": 1,
            "written_file_count": 1,
        }

        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "4" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        status["job_id"] = job_id
        (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            result = mod.read_render_job(job_id)

        assert result["completed"] == 1
        assert result["total"] == 1
        assert result["progress"] == 1.0
        assert result["written_file_count"] == 1
        assert result["recent_written_files"] == [str(output)]

    def test_background_worker_expands_houdini_variables_without_explicit_frame_range(self, tmp_path: Path) -> None:
        output = tmp_path / "renders" / "beauty.0001.exr"

        def render(_rop, _frame_range):
            output.parent.mkdir()
            output.write_bytes(b"new output")
            return None, "render"

        status = _run_render_worker(
            tmp_path,
            None,
            [],
            {},
            render,
            pattern="$HIP/renders/beauty.$F4.exr",
            expand_string=lambda value: value.replace("$HIP", str(tmp_path)),
        )

        assert status["state"] == "completed"
        assert [Path(path) for path in status["written_files"]] == [output]
        assert status["output_verification"] == {
            "state": "verified",
            "expected_output_count": 1,
            "written_file_count": 1,
        }

    def test_background_worker_reports_partial_outputs_when_range_fails(self, tmp_path: Path) -> None:
        expected = [tmp_path / "beauty.{:04d}.exr".format(frame) for frame in range(1, 8)]

        def render(_rop, _frame_range):
            for output in expected[:2]:
                output.write_bytes(b"new")
            return [1.0, 7.0], "execute"

        status = _run_render_worker(
            tmp_path,
            [1, 7, 1],
            expected,
            {},
            render,
            rop_errors=["Command Exit Code: 1"],
        )

        assert status["state"] == "failed"
        assert status["output_verification"] == {
            "state": "partial",
            "expected_output_count": 7,
            "written_file_count": 2,
        }

    def test_background_worker_does_not_verify_outputs_when_render_fails(self, tmp_path: Path) -> None:
        output = tmp_path / "beauty.0001.exr"

        def render(_rop, _frame_range):
            output.write_bytes(b"truncated output")
            return [1.0, 1.0], "execute"

        status = _run_render_worker(
            tmp_path,
            [1, 1, 1],
            [output],
            {},
            render,
            rop_errors=["Command Exit Code: 139"],
        )

        assert status["state"] == "failed"
        assert status["written_files"] == [str(output)]
        assert status["output_verification"] == {
            "state": "failed",
            "expected_output_count": 1,
            "written_file_count": 1,
        }

    def test_background_worker_rejects_empty_output(self, tmp_path: Path) -> None:
        output = tmp_path / "beauty.0001.exr"

        def render(_rop, _frame_range):
            output.write_bytes(b"")
            return [1.0, 1.0], "execute"

        status = _run_render_worker(tmp_path, [1, 1, 1], [output], {}, render)

        assert status["state"] == "failed"
        assert status["written_files"] == []
        assert status["output_verification"] == {
            "state": "not_observed",
            "expected_output_count": 1,
            "written_file_count": 0,
        }

    def test_background_worker_verifies_partial_outputs_when_render_raises(self, tmp_path: Path) -> None:
        expected = [tmp_path / "beauty.{:04d}.exr".format(frame) for frame in range(1, 5)]

        def render(_rop, _frame_range):
            for output in expected[:2]:
                output.write_bytes(b"completed output")
            raise RuntimeError("render failed")

        status = _run_render_worker(tmp_path, [1, 4, 1], expected, {}, render)

        assert status["state"] == "failed"
        assert status["written_files"] == [str(output) for output in expected[:2]]
        assert status["output_verification"] == {
            "state": "partial",
            "expected_output_count": 4,
            "written_file_count": 2,
        }

        mod = _load_script("houdini-render", "_background_render.py")
        job_id = "3" * 32
        job_dir = tmp_path / "dcc-mcp-houdini-render-jobs" / job_id
        job_dir.mkdir(parents=True)
        status["job_id"] = job_id
        (job_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
        with patch.object(mod.tempfile, "gettempdir", return_value=str(tmp_path)):
            result = mod.read_render_job(job_id)

        assert result["completed"] == 2
        assert result["total"] == 4
        assert result["progress"] == 0.5
        assert result["written_file_count"] == 2

    def test_background_worker_recovers_from_cached_launcher_without_snapshot(self, tmp_path: Path) -> None:
        output = tmp_path / "karma_beauty.1080.exr"
        pattern = "{}/karma_beauty.$F4.exr".format(tmp_path.as_posix())

        def render(_rop, _frame_range):
            output.write_bytes(b"new frame")
            return [1080.0, 1080.0], "execute"

        status = _run_render_worker(
            tmp_path,
            [1080, 1080, 1],
            [],
            {},
            render,
            pattern=pattern,
            include_launch_snapshot=False,
        )
        assert status["state"] == "completed"
        assert status["written_files"] == [output.as_posix()]

    def test_background_worker_fails_when_only_stale_output_exists(self, tmp_path: Path) -> None:
        stale = tmp_path / "beauty.0001.exr"
        stale.write_bytes(b"stale")
        status = _run_render_worker(
            tmp_path,
            [1, 1, 1],
            [stale],
            {str(stale): {"mtime_ns": stale.stat().st_mtime_ns, "size": stale.stat().st_size}},
            lambda _rop, _frame_range: ([1.0, 1.0], "execute"),
        )
        assert status["state"] == "failed"
        assert status["written_files"] == []
        assert "no new or updated output" in status["error"].lower()

    @pytest.mark.parametrize("job_kind", ["render", "cache"])
    def test_background_worker_output_job_without_pattern_still_fails(self, tmp_path: Path, job_kind: str) -> None:
        status = _run_render_worker(
            tmp_path,
            [1, 1, 1],
            [],
            {},
            lambda _rop, _frame_range: ([1.0, 1.0], "render"),
            pattern=None,
            job_kind=job_kind,
        )

        assert status["state"] == "failed"
        assert status["output_verification"]["state"] == "unavailable"

    def test_background_worker_rop_chain_without_output_pattern_completes(self, tmp_path: Path) -> None:
        status = _run_render_worker(
            tmp_path,
            [1, 24, 1],
            [],
            {},
            lambda _rop, _frame_range: ([1.0, 24.0], "render"),
            pattern=None,
            job_kind="rop_chain",
        )

        assert status["state"] == "completed"
        assert status["written_files"] == []
        assert status["output_verification"] == {
            "state": "unavailable",
            "expected_output_count": 0,
            "written_file_count": 0,
        }

    def test_background_worker_rop_chain_with_unchanged_output_completes(self, tmp_path: Path) -> None:
        stale = tmp_path / "beauty.0001.exr"
        stale.write_bytes(b"stale")
        status = _run_render_worker(
            tmp_path,
            [1, 1, 1],
            [stale],
            {str(stale): {"mtime_ns": stale.stat().st_mtime_ns, "size": stale.stat().st_size}},
            lambda _rop, _frame_range: ([1.0, 1.0], "render"),
            job_kind="rop_chain",
        )

        assert status["state"] == "completed"
        assert status["output_verification"]["state"] == "not_observed"

    def test_background_worker_fails_on_rop_cook_error_log(self, tmp_path: Path) -> None:
        def render(_rop, _frame_range):
            (tmp_path / "beauty.0001.exr").write_bytes(b"new")
            return [1.0, 1.0], "execute"

        status = _run_render_worker(
            tmp_path,
            [1, 1, 1],
            [tmp_path / "beauty.0001.exr"],
            {},
            render,
            stderr_text="Error: ROP cook error",
        )
        assert status["state"] == "failed"
        assert "rop cook error" in status["error"].lower()

    def test_background_worker_preserves_ignore_inputs(self, tmp_path: Path) -> None:
        captured = {}

        def render(_rop, _frame_range, ignore_inputs=False):
            captured["ignore_inputs"] = ignore_inputs
            (tmp_path / "beauty.0001.exr").write_bytes(b"new")
            return [1.0, 1.0], "render"

        status = _run_render_worker(
            tmp_path,
            [1, 1, 1],
            [tmp_path / "beauty.0001.exr"],
            {},
            render,
            ignore_inputs=True,
        )

        assert status["state"] == "completed"
        assert captured["ignore_inputs"] is True

    def test_render_rop_background_returns_job_without_rendering_in_ui(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        picture = _scalar_parm(str(tmp_path / "beauty.$F4.exr"))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        job = {"job_id": "a" * 32, "state": "running", "pid": 1234}

        with patch.dict(sys.modules, {"hou": mock_hou}):
            with patch.object(mod, "launch_background_render", return_value=job) as launch:
                result = mod.render_rop("/out/mantra1", frame_range=[1, 9, 4], background=True)

        assert result["success"] is True
        assert result["context"]["background"] is True
        assert result["context"]["job_id"] == "a" * 32
        launch.assert_called_once_with(mock_hou, "/out/mantra1", [1, 9, 4], str(tmp_path / "beauty.$F4.exr"))
        rop.render.assert_not_called()

    def test_render_rop_defaults_to_background_in_ui(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        picture = _scalar_parm(str(tmp_path / "beauty.$F4.exr"))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = True
        job = {"job_id": "a" * 32, "state": "queued", "pid": 1234}

        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(
            mod, "launch_background_render", return_value=job
        ) as launch:
            result = mod.render_rop("/out/mantra1", frame_range=[1, 100000, 1])

        assert result["success"] is True
        assert result["context"]["background"] is True
        launch.assert_called_once_with(mock_hou, "/out/mantra1", [1, 100000, 1], str(tmp_path / "beauty.$F4.exr"))
        rop.render.assert_not_called()

    def test_render_rop_defaults_to_background_in_headless(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        picture = _scalar_parm(str(tmp_path / "beauty.$F4.exr"))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = False
        job = {"job_id": "b" * 32, "state": "queued", "pid": 4321}

        with patch.dict(sys.modules, {"hou": mock_hou}), patch.object(
            mod, "launch_background_render", return_value=job
        ) as launch:
            result = mod.render_rop("/out/mantra1", frame_range=[1, 720, 1])

        assert result["success"] is True
        assert result["context"]["background"] is True
        assert result["context"]["job_id"] == "b" * 32
        launch.assert_called_once_with(mock_hou, "/out/mantra1", [1, 720, 1], str(tmp_path / "beauty.$F4.exr"))
        rop.render.assert_not_called()

    def test_expand_outputs_accepts_single_value_parm_tuple(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        out = tmp_path / "beauty.0001.exr"
        out.write_bytes(b"exr")

        assert mod._expand_outputs([str(out)]) == [str(out)]

    def test_render_rop_reports_written_and_elapsed(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        out = tmp_path / "beauty.exr"
        picture = _scalar_parm(str(out))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        rop.render.side_effect = lambda verbose=False: out.write_bytes(b"exr")
        rop.errors.return_value = ["missing texture"]
        rop.warnings.return_value = ["low sample count"]
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = False

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop("/out/mantra1", background=False)

        assert result["success"] is True
        assert result["context"]["rendered"] is True
        assert result["context"]["written_files"] == [str(out)]
        assert "elapsed_secs" in result["context"]
        assert result["context"]["errors"] == ["missing texture"]
        assert result["context"]["warnings"] == ["low sample count"]

    def test_render_rop_reports_render_exception_as_error(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        picture = _scalar_parm(str(tmp_path / "beauty.exr"))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        rop.render.side_effect = RuntimeError("renderer unavailable")
        rop.errors.return_value = ["driver failed"]
        rop.warnings.return_value = ["fallback disabled"]
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = False

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop("/out/mantra1", background=False)

        assert result["success"] is True
        assert result["context"]["rendered"] is False
        assert result["context"]["errors"] == [
            "Render failed: renderer unavailable",
            "driver failed",
        ]
        assert result["context"]["warnings"] == ["fallback disabled"]

    def test_render_rop_uses_solaris_execute_and_outputimage(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        out = tmp_path / "karma.0001.exr"
        output = _scalar_parm(str(out).replace("0001", "$F4"))
        output.eval.return_value = str(out)
        execute = MagicMock()
        execute.pressButton.side_effect = lambda: out.write_bytes(b"exr")
        frame_parms = [MagicMock(), MagicMock(), MagicMock()]
        rop = _node("/stage/karma_rop", "karma_rop", "usdrender_rop")
        rop.parmTuple.side_effect = lambda n: tuple(frame_parms) if n == "f" else None
        rop.parm.side_effect = lambda n: {
            "outputimage": output,
            "lopoutput": _scalar_parm("__render__.usd"),
            "execute": execute,
        }.get(n)
        rop.errors.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = True

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop("/stage/karma_rop", frame_range=[1, 1], background=False)

        assert result["success"] is True
        assert result["context"]["execution_mode"] == "execute"
        assert result["context"]["output_pattern"].endswith("karma.$F4.exr")
        assert result["context"]["written_files"] == [str(out)]
        execute.pressButton.assert_called_once_with()
        rop.render.assert_not_called()
        for parm, value in zip(frame_parms, (1.0, 1.0, 1.0)):
            parm.deleteAllKeyframes.assert_called_once_with()
            parm.set.assert_called_once_with(value)

    def test_render_rop_forwards_explicit_frame_range_to_hom(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        out = tmp_path / "beauty.0001.exr"
        picture = _scalar_parm(str(out))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        rop.render.side_effect = lambda **_kwargs: out.write_bytes(b"exr")
        rop.errors.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop("/out/mantra1", frame_range=[1, 1, 1], background=False)

        assert result["success"] is True
        rop.render.assert_called_once_with(verbose=False, frame_range=(1.0, 1.0, 1.0))
