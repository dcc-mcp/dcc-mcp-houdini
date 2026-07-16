"""Mock-hou unit tests for houdini-camera-light and houdini-render skills."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

_SKILLS_ROOT = Path(__file__).parent.parent / "src" / "dcc_mcp_houdini" / "skills"


def _load_script(skill_name: str, script_name: str) -> ModuleType:
    path = _SKILLS_ROOT / skill_name / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(f"{skill_name}_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_render_worker() -> ModuleType:
    scripts = _SKILLS_ROOT / "houdini-render" / "scripts"
    with patch.object(sys, "path", [str(scripts), *sys.path]):
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


def _run_render_worker(
    tmp_path,
    frame_range,
    expected_outputs,
    snapshot,
    render,
    stderr_text="",
    pattern=None,
    include_launch_snapshot=True,
):
    mod = _load_render_worker()
    pattern = pattern or str(tmp_path / "beauty.$F4.exr")
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"
    stdout.write_text("", encoding="utf-8")
    stderr.write_text(stderr_text, encoding="utf-8")
    status_path = tmp_path / "status.json"
    status = {"state": "queued", "stdout_path": str(stdout), "stderr_path": str(stderr)}
    if include_launch_snapshot:
        status.update(
            {
                "expected_outputs": [str(path) for path in expected_outputs],
                "output_snapshot": snapshot,
            }
        )
    status_path.write_text(json.dumps(status), encoding="utf-8")
    rop = _node("/stage/karma", "karma", "usdrender_rop")
    rop.errors.return_value = []
    mock_hou = MagicMock()
    mock_hou.node.return_value = rop
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


class TestRenderSettings:
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
        mock_hou.node.return_value = rop

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.get_render_settings("/out/mantra1")

        assert result["success"] is True
        assert result["context"]["camera"] == "/obj/cam1"
        assert result["context"]["output_path"] == "/tmp/beauty.exr"
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


class TestRenderExecution:
    def test_background_render_launches_isolated_hython(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        hip = tmp_path / "scene.hip"
        hip.write_bytes(b"hip")
        hython = tmp_path / ("hython.exe" if mod.os.name == "nt" else "hython")
        hython.write_bytes(b"exe")
        mock_hou = MagicMock()
        mock_hou.hipFile.path.return_value = str(hip)
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
        assert popen.call_args.kwargs["env"]["PARENT_ONLY"] == "keep"
        assert popen.call_args.kwargs["env"]["DCC_MCP_BACKGROUND_RENDER"] == "1"
        assert popen.call_args.kwargs["start_new_session"] is (mod.os.name != "nt")
        assert mod._PROCESS_HANDLES[job["job_id"]] is process

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

    def test_terminate_process_tree_uses_taskkill_on_windows(self) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        process = MagicMock(pid=4321)
        process.poll.return_value = None
        process.wait.return_value = 0
        completed = MagicMock(returncode=0)

        with patch.object(mod.os, "name", "nt"), patch.object(mod.subprocess, "run", return_value=completed) as run:
            mod._terminate_process_tree(process)

        run.assert_called_once_with(
            ["taskkill", "/PID", "4321", "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        process.wait.assert_called_once()

    def test_terminate_process_tree_uses_process_group_on_posix(self) -> None:
        mod = _load_script("houdini-render", "_background_render.py")
        process = MagicMock(pid=4321)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("hython", 2), 0]

        with patch.object(mod.os, "name", "posix"), patch.object(mod.os, "killpg", create=True) as killpg:
            mod._terminate_process_tree(process)

        assert killpg.call_args_list[0].args == (4321, mod._SIGTERM)
        assert killpg.call_args_list[1].args == (4321, mod._SIGKILL)

    def test_background_worker_reports_only_updated_requested_outputs(self, tmp_path: Path) -> None:
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
        assert status["state"] == "completed"
        assert status["written_files"] == [str(tmp_path / "beauty.0005.exr")]

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

    def test_render_rop_reports_written_and_elapsed(self, tmp_path: Path) -> None:
        mod = _load_script("houdini-render", "render_rop.py")
        out = tmp_path / "beauty.exr"
        picture = _scalar_parm(str(out))
        rop = _node("/out/mantra1", "mantra1", "ifd")
        rop.parmTuple.return_value = None
        rop.parm.side_effect = lambda n: picture if n == "picture" else None
        rop.render.side_effect = lambda verbose=False: out.write_bytes(b"exr")
        rop.errors.return_value = []
        mock_hou = MagicMock()
        mock_hou.node.return_value = rop
        mock_hou.isUIAvailable.return_value = False

        with patch.dict(sys.modules, {"hou": mock_hou}):
            result = mod.render_rop("/out/mantra1")

        assert result["success"] is True
        assert result["context"]["rendered"] is True
        assert result["context"]["written_files"] == [str(out)]
        assert "elapsed_secs" in result["context"]

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
