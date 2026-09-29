"""Real filesystem and CLI contract checks; no CAD/proprietary runtime needed."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shellflow import cli


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo with spaces"
        self.root.mkdir()
        self.platform = self.root / ".local/platforms/test-platform"
        self.platform.mkdir(parents=True)
        source = self.platform / "source.step"
        source.write_text("test CAD source only", encoding="utf-8")
        cli.write_json(self.platform / "platform.json", {"schema_version": 1, "id": "test-platform", "files": [cli.file_record(source, self.platform, "source_step")]})

    def invoke(self, *args, root=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--root", str(root or self.root), *args])
        return code, json.loads(out.getvalue())

    def start(self, *extra):
        code, result = self.invoke("start", "--name", "pirate-a", "--platform", "test-platform", "--brief", "\u5c01\u95ed\u524d\u8138\uff0c\u5de6\u53f3\u4e0d\u5f97\u8d85\u51fa\u539f\u8f6e\u5ed3", *extra)
        self.assertEqual(code, 0, result)
        return self.root / "workspaces/pirate-a"

    def checkpoint(self, project, stage):
        evidence = project / "evidence" / f"{stage}.json"
        evidence.write_text('{"passed":true}', encoding="utf-8")
        artifact = f"evidence/{stage}.json"
        if stage == "concept":
            artifact = "evidence/selection.json"
            cli.write_json(project / artifact, {"schema": "design-selection/1", "selected_design": "candidate-a",
                "user_confirmation": "Use candidate A", "references": [cli.file_record(evidence, project, "selected_design")]})
        code, result = self.invoke("checkpoint", "pirate-a", "--stage", stage, "--artifact", artifact)
        self.assertEqual(code, 0, result)
        return result

    def install_fixture_simulation_exporter(self):
        """A tiny external producer tests the wrapper, not actual CAD/MuJoCo behavior."""
        exporter = self.root / "scripts/export_simulation.py"
        exporter.parent.mkdir(parents=True, exist_ok=True)
        exporter.write_text('''from pathlib import Path
import argparse, hashlib, json
parser=argparse.ArgumentParser()
parser.add_argument('--shell',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--profile',type=Path,required=True)
args=parser.parse_args()
mode=args.shell.read_bytes()
if mode==b'producer-fails':
    print(json.dumps({'ok':False,'error':'fixture producer failure'}))
    raise SystemExit(3)
args.output.mkdir(parents=True,exist_ok=False)
(args.output/'meshes').mkdir()
files=[]
for name,content in {'robot.urdf':b'<robot name="fixture"/>','robot.xml':b'<mujoco/>','scene.xml':b'<mujoco/>','meshes/shell.stl':b'fixture mesh'}.items():
    path=args.output/name
    path.write_bytes(content)
    files.append({'role':'fixture','path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
report={'schema_version':1,'passed':True,'files':files,'scope':'control fixture only',
        'source_shell_sha256':hashlib.sha256(mode).hexdigest(),
        'robot_profile_sha256':hashlib.sha256(args.profile.read_bytes()).hexdigest(),
        'urdf_verification':{'passed':True},
        'whole_robot':{'passed':True,'root_link':'base_link','robot_links':2,
                       'movable_joints':1,'native_actuators':0,'shell_parent_link':'base_link',
                       'retained_links':['base_link','leg_1']}}
if mode==b'missing-whole':
    del report['whole_robot']
elif mode==b'empty-whole':
    report['whole_robot']={}
elif mode==b'shell-only':
    report['whole_robot']['robot_links']=1
elif mode==b'no-movable-joints':
    report['whole_robot']['movable_joints']=0
elif mode==b'boolean-counts':
    report['whole_robot']['movable_joints']=True
elif mode==b'failed-whole':
    report['whole_robot']['passed']=False
elif mode==b'wrong-root':
    report['whole_robot']['root_link']='shell'
elif mode==b'no-retained-links':
    report['whole_robot']['retained_links']=[]
elif mode==b'unknown-shell-parent':
    report['whole_robot']['shell_parent_link']='missing'
elif mode==b'failed-urdf':
    report['urdf_verification']['passed']=False
elif mode==b'wrong-source-sha':
    report['source_shell_sha256']='0'*64
elif mode==b'wrong-profile-sha':
    report['robot_profile_sha256']='0'*64
elif mode==b'profile-changes':
    args.profile.write_text('{"changed":true}',encoding='utf-8')
    report['robot_profile_sha256']=hashlib.sha256(args.profile.read_bytes()).hexdigest()
elif mode==b'shell-changes':
    args.shell.write_bytes(b'changed after export')
(args.output/'simulation-report.json').write_text(json.dumps(report),encoding='utf-8')
if mode==b'producer-corrupts':
    (args.output/'robot.urdf').write_text('changed after report',encoding='utf-8')
print(json.dumps({'ok':True,'output':str(args.output)}))
''', encoding="utf-8")
        for platform in ("hexa-v1", "jumper-v1-6", "jumper"):
            cli.write_json(self.root / "robots" / platform / "profile.json", {"fixture": True, "id": platform})

    def test_relocation_and_recorded_is_not_verified(self):
        incoming = Path(self.temporary.name) / "source.glb"
        incoming.write_bytes(b"test model")
        project = self.start("--model", str(incoming), "--front-opening", "close")
        self.assertEqual((project / "input/model.glb").read_bytes(), incoming.read_bytes())
        record = self.checkpoint(project, "requirements")
        self.assertEqual(record["status"], "recorded")
        self.assertEqual(record["verification"], "pending")
        self.assertEqual(record["next_stage"], "concept")
        moved = Path(self.temporary.name) / "relocated repository"
        shutil.move(str(self.root), moved)
        code, status = self.invoke("status", "pirate-a", root=moved)
        self.assertEqual(code, 0, status)
        self.assertEqual(status["stages"]["requirements"]["status"], "recorded")
        self.assertEqual(status["digital_acceptance"], "not_certified_by_shellflow")
        self.assertFalse(status["physical_fit_tested"])

    def test_source_tampering_invalidates_and_blocks_record(self):
        incoming = Path(self.temporary.name) / "source.glb"
        incoming.write_bytes(b"initial")
        project = self.start("--model", str(incoming))
        self.checkpoint(project, "requirements")
        (project / "input/model.glb").write_bytes(b"changed")
        code, status = self.invoke("status", "pirate-a")
        self.assertEqual(code, 1)
        self.assertEqual(status["stages"]["requirements"]["status"], "stale")
        code, result = self.invoke("checkpoint", "pirate-a", "--stage", "concept", "--artifact", "evidence/requirements.json")
        self.assertEqual(code, 2)
        self.assertIn("Source integrity", result["error"])

    def test_artifact_tampering_invalidates_descendants(self):
        project = self.start()
        self.checkpoint(project, "requirements")
        self.checkpoint(project, "concept")
        (project / "evidence/requirements.json").write_text("modified", encoding="utf-8")
        code, status = self.invoke("status", "pirate-a")
        self.assertEqual(code, 1)
        self.assertEqual(status["stages"]["requirements"]["status"], "stale")
        self.assertEqual(status["stages"]["concept"]["status"], "stale")

    def test_parameter_and_engine_changes_invalidate(self):
        project = self.start()
        self.checkpoint(project, "requirements")
        with patch.object(cli, "engine_fingerprint", return_value="0" * 64):
            self.assertEqual(self.invoke("status", "pirate-a")[1]["stages"]["requirements"]["status"], "stale")
        job = cli.read_json(project / "job.json")
        job["design"]["front_opening"] = "close"
        cli.write_json(project / "job.json", job)
        self.assertEqual(self.invoke("status", "pirate-a")[1]["stages"]["requirements"]["status"], "stale")

    def test_platform_tamper_and_replacement_are_detected(self):
        project = self.start()
        self.checkpoint(project, "requirements")
        (self.platform / "source.step").write_text("different", encoding="utf-8")
        code, status = self.invoke("status", "pirate-a")
        self.assertEqual(code, 1)
        self.assertFalse(status["platform"]["integrity_passed"])
        data = cli.read_json(self.platform / "platform.json")
        data["files"] = [cli.file_record(self.platform / "source.step", self.platform, "source_step")]
        cli.write_json(self.platform / "platform.json", data)
        self.assertFalse(self.invoke("status", "pirate-a")[1]["platform"]["integrity_passed"])

    def test_missing_platform_allows_preparation_but_reports_blocker(self):
        shutil.rmtree(self.platform)
        project = self.start()
        result = self.checkpoint(project, "requirements")
        self.assertEqual(result["next_stage"], "concept")
        self.assertTrue(result["blockers"])
        self.assertEqual(self.invoke("next", "pirate-a")[0], 1)

    def test_late_platform_install_binds_on_checkpoint_not_status(self):
        saved_platform = Path(self.temporary.name) / "platform saved before installation"
        shutil.move(str(self.platform), saved_platform)
        project = self.start()
        self.checkpoint(project, "requirements")
        shutil.move(str(saved_platform), self.platform)
        code, status = self.invoke("status", "pirate-a")
        self.assertEqual(code, 1)
        self.assertEqual(status["platform"]["binding"], "unbound")
        self.assertEqual(status["stages"]["requirements"]["status"], "stale")
        self.assertIsNone(cli.read_json(project / "job.json")["platform"]["manifest_sha256"])
        result = self.checkpoint(project, "requirements")
        self.assertTrue(result["platform_bound_now"])
        job = cli.read_json(project / "job.json")
        self.assertEqual(job["platform"]["manifest_sha256"], cli.sha(self.platform / "platform.json"))
        self.assertEqual(self.invoke("status", "pirate-a")[0], 0)
        data = cli.read_json(self.platform / "platform.json")
        data["version"] = "replacement"
        cli.write_json(self.platform / "platform.json", data)
        code, error = self.invoke("checkpoint", "pirate-a", "--stage", "concept", "--artifact", "evidence/requirements.json")
        self.assertEqual(code, 2)
        self.assertIn("platform integrity/version", error["error"])

    def test_overwrite_and_path_traversal_are_rejected(self):
        project = self.start()
        original = (project / "job.json").read_bytes()
        self.assertEqual(self.invoke("start", "--name", "pirate-a", "--platform", "test-platform", "--brief", "overwrite")[0], 2)
        self.assertEqual((project / "job.json").read_bytes(), original)
        for bad in ("../escape", "..\\escape", "C:escape", "/absolute", "CON"):
            self.assertEqual(self.invoke("start", "--name", bad, "--platform", "test-platform", "--brief", "bad")[0], 2)
        self.assertEqual(self.invoke("checkpoint", "pirate-a", "--stage", "requirements", "--artifact", "../outside.json")[0], 2)

    def test_external_evidence_is_copied_and_portable(self):
        project = self.start()
        external = Path(self.temporary.name) / "outside report.json"
        external.write_text('{"passed":true}', encoding="utf-8")
        code, result = self.invoke("checkpoint", "pirate-a", "--stage", "requirements", "--artifact", str(external))
        self.assertEqual(code, 0, result)
        external.unlink()
        self.assertEqual(self.invoke("status", "pirate-a")[0], 0)
        record = cli.read_json(project / "job.json")["stages"]["requirements"]["artifacts"][0]
        self.assertFalse(Path(record["path"]).is_absolute())

    def test_platform_manifest_path_escape_is_rejected(self):
        data = cli.read_json(self.platform / "platform.json")
        data["files"][0]["path"] = "../source.step"
        cli.write_json(self.platform / "platform.json", data)
        self.start()
        code, status = self.invoke("status", "pirate-a")
        self.assertEqual(code, 1)
        self.assertIn("escapes", str(status["platform"]["issues"]))

    def test_known_catalog_pins_manifest_and_unknown_catalog_reports_scope(self):
        state = cli.platform_state(self.root, "test-platform")
        self.assertTrue(state["integrity_passed"])
        self.assertEqual(state["catalog"]["scope"], "local_import_internal_files_only")
        catalog = self.root / "platforms/catalog/test-platform.json"
        cli.write_json(catalog, {"id": "test-platform", "platform_manifest_sha256": cli.sha(self.platform / "platform.json")})
        state = cli.platform_state(self.root, "test-platform")
        self.assertTrue(state["catalog"]["matched"])
        self.assertEqual(state["catalog"]["scope"], "catalog_pinned_and_internal_files")

    def test_self_consistent_replacement_cannot_override_catalog(self):
        catalog = self.root / "platforms/catalog/test-platform.json"
        cli.write_json(catalog, {"id": "test-platform", "platform_manifest_sha256": cli.sha(self.platform / "platform.json")})
        (self.platform / "source.step").write_text("self-consistent replacement", encoding="utf-8")
        data = cli.read_json(self.platform / "platform.json")
        data["files"] = [cli.file_record(self.platform / "source.step", self.platform, "source_step")]
        cli.write_json(self.platform / "platform.json", data)
        project = self.start()
        code, status = self.invoke("status", "pirate-a")
        self.assertEqual(code, 1)
        self.assertFalse(status["platform"]["catalog"]["matched"])
        self.assertIsNone(cli.read_json(project / "job.json")["platform"]["manifest_sha256"])
        self.assertIn("pinned SHA256", str(status["platform"]["issues"]))

    def test_non_object_platform_manifest_is_integrity_failure(self):
        self.start()
        for invalid in ([], None):
            with self.subTest(invalid=invalid):
                cli.write_json(self.platform / "platform.json", invalid)
                code, status = self.invoke("status", "pirate-a")
                self.assertEqual(code, 1)
                self.assertFalse(status["platform"]["integrity_passed"])
                self.assertIn("manifest integrity error", str(status["platform"]["issues"]))

    def test_engineering_requires_bound_valid_platform(self):
        saved = Path(self.temporary.name) / "not-yet-installed"
        shutil.move(str(self.platform), saved)
        project = self.start()
        self.checkpoint(project, "requirements")
        for stage in cli.STAGES[cli.STAGES.index("engineering"):]:
            code, error = self.invoke("checkpoint", "pirate-a", "--stage", stage, "--artifact", "evidence/requirements.json")
            self.assertEqual(code, 2)
            self.assertIn("already bound, valid platform", error["error"])
        shutil.move(str(saved), self.platform)
        code, error = self.invoke("checkpoint", "pirate-a", "--stage", "engineering", "--artifact", "evidence/requirements.json")
        self.assertEqual(code, 2)
        self.assertIsNone(cli.read_json(project / "job.json")["platform"]["manifest_sha256"])
        self.checkpoint(project, "requirements")
        self.checkpoint(project, "concept")
        code, record = self.invoke("checkpoint", "pirate-a", "--stage", "engineering", "--artifact", "evidence/requirements.json")
        self.assertEqual(code, 0)
        self.assertEqual(record["verification"], "pending")

    def test_selection_gate_rejects_missing_confirmation_and_changed_reference(self):
        project = self.start()
        self.checkpoint(project, "requirements")
        before = (project / "job.json").read_bytes()
        for stage in ("concept", "multiview", "appearance", "engineering"):
            code, result = self.invoke("checkpoint", "pirate-a", "--stage", stage,
                                       "--artifact", "evidence/requirements.json")
            self.assertEqual(code, 2, result)
            self.assertEqual((project / "job.json").read_bytes(), before)
        self.checkpoint(project, "concept")
        self.checkpoint(project, "appearance")
        selection = project / "evidence/selection.json"
        data = cli.read_json(selection)
        data["user_confirmation"] = " "
        cli.write_json(selection, data)
        self.assertEqual(self.invoke("checkpoint", "pirate-a", "--stage", "concept",
                                     "--artifact", "evidence/selection.json")[0], 2)
        self.checkpoint(project, "concept")
        (project / "evidence/concept.json").write_text("changed design", encoding="utf-8")
        state = self.invoke("status", "pirate-a")[1]
        self.assertEqual(state["stages"]["concept"]["status"], "stale")
        self.assertEqual(self.invoke("checkpoint", "pirate-a", "--stage", "appearance",
                                     "--artifact", "evidence/requirements.json")[0], 2)

    def test_doctor_does_not_claim_environment_ready(self):
        code, result = self.invoke("doctor")
        self.assertEqual(code, 0)
        self.assertFalse(result["producer_environment_verified"])
        self.assertIn("packages_in_current_python", result)

    def test_manually_claimed_pass_is_not_accepted(self):
        project = self.start()
        job = cli.read_json(project / "job.json")
        job["stages"]["validation"]["verification"] = "passed"
        cli.write_json(project / "job.json", job)
        code, result = self.invoke("status", "pirate-a")
        self.assertEqual(code, 2)
        self.assertIn("pending verification", result["error"])

    def test_new_jobs_require_printing_and_full_robot_simulation(self):
        project = self.start()
        job = cli.read_json(project / "job.json")
        self.assertEqual(job["schema_version"], 2)
        self.assertEqual(job["deliverables"], {"printing": True, "simulation": True})
        self.assertEqual(job["simulation"], cli.simulation_defaults())
        self.assertEqual(job["simulation"]["robot_platform"], "jumper")
        self.assertEqual(cli.STAGES[-3:], ("slicing", "simulation", "delivery"))
        task = (project / "AGENT_TASK.md").read_text(encoding="utf-8")
        self.assertIn("full-robot URDF, MJCF", task)
        self.assertIn("does not certify new-shell collision dynamics", task)
        self.assertIn("`jumper`", task)

    def test_start_allows_explicit_robot_platform_and_rejects_path_syntax(self):
        for bad in ("../hexa-v1", "..\\hexa-v1", "C:robot", "/robot", "CON"):
            with self.subTest(platform=bad):
                code, result = self.invoke("start", "--name", "pirate-a", "--platform", "test-platform",
                                           "--brief", "fixture", "--robot-platform", bad)
                self.assertEqual(code, 2, result)
                self.assertFalse((self.root / "workspaces/pirate-a").exists())
        project = self.start("--robot-platform", "hexa-v1")
        self.assertEqual(cli.read_json(project / "job.json")["simulation"]["robot_platform"], "hexa-v1")

    def test_legacy_job_load_is_readonly_and_checkpoint_persists_upgrade(self):
        project = self.start()
        self.checkpoint(project, "requirements")
        job = cli.read_json(project / "job.json")
        job["schema_version"] = 1
        del job["stages"]["simulation"]
        del job["deliverables"]
        del job["simulation"]
        job["stages"]["requirements"]["engine_sha256"] = "0" * 64
        job["stages"]["requirements"]["input_fingerprint"] = "0" * 64
        cli.write_json(project / "job.json", job)
        original = (project / "job.json").read_bytes()
        code, state = self.invoke("status", "pirate-a")
        self.assertEqual(code, 1)
        self.assertEqual(state["stages"]["simulation"]["status"], "pending")
        self.assertEqual(state["stages"]["requirements"]["status"], "stale")
        self.assertEqual((project / "job.json").read_bytes(), original)
        self.checkpoint(project, "requirements")
        upgraded = cli.read_json(project / "job.json")
        self.assertEqual(upgraded["schema_version"], 2)
        self.assertEqual(upgraded["stages"]["simulation"]["status"], "pending")
        self.assertTrue(upgraded["deliverables"]["simulation"])
        self.assertEqual(upgraded["simulation"]["robot_platform"], "hexa-v1")
        self.assertEqual(upgraded["stages"]["requirements"]["verification"], "pending")

    def test_legacy_partial_simulation_defaults_do_not_select_latest_robot(self):
        project = self.start()
        job = cli.read_json(project / "job.json")
        job["schema_version"] = 1
        job["simulation"] = {"collision_policy": "baseline_preserved"}
        cli.write_json(project / "job.json", job)
        self.assertEqual(cli.load_job(project)["simulation"]["robot_platform"], "hexa-v1")
        job["simulation"]["robot_platform"] = "custom-robot"
        cli.write_json(project / "job.json", job)
        self.assertEqual(cli.load_job(project)["simulation"]["robot_platform"], "custom-robot")

    def test_assemble_records_all_outputs_and_detects_mesh_or_urdf_changes(self):
        project = self.start()
        self.install_fixture_simulation_exporter()
        (project / "work/shell.stl").write_bytes(b"fixture shell")
        code, result = self.invoke("assemble", "pirate-a", "--shell", "work/shell.stl")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(result["verification"], "pending")
        self.assertFalse(result["physical_dynamics_validated"])
        self.assertEqual(result["robot_platform"], "jumper")
        record = cli.read_json(project / "job.json")["stages"]["simulation"]
        self.assertEqual(len(record["artifacts"]), 6)  # report, input shell, three XML files, mesh
        self.assertEqual(self.invoke("status", "pirate-a")[1]["stages"]["simulation"]["status"], "recorded")
        urdf = project / "delivery/simulation/robot.urdf"
        original = urdf.read_bytes()
        self.assertEqual(self.invoke("assemble", "pirate-a", "--shell", "work/shell.stl")[0], 2)
        self.assertEqual(urdf.read_bytes(), original)
        urdf.write_text("modified URDF", encoding="utf-8")
        self.assertEqual(self.invoke("status", "pirate-a")[1]["stages"]["simulation"]["status"], "stale")
        urdf.write_bytes(original)
        (project / "delivery/simulation/meshes/shell.stl").write_bytes(b"tampered mesh")
        self.assertEqual(self.invoke("status", "pirate-a")[1]["stages"]["simulation"]["status"], "stale")

    def test_assemble_failed_or_corrupt_producer_never_records_completion(self):
        project = self.start("--robot-platform", "hexa-v1")
        self.install_fixture_simulation_exporter()
        shell = project / "work/shell.stl"
        original_job = (project / "job.json").read_bytes()
        for mode in (b"producer-fails", b"producer-corrupts"):
            with self.subTest(mode=mode):
                shell.write_bytes(mode)
                code, result = self.invoke("assemble", "pirate-a", "--shell", "work/shell.stl",
                                           "--robot-platform", "jumper-v1-6", "--output", "delivery/" + mode.decode())
                self.assertEqual(code, 2, result)
                self.assertEqual(cli.read_json(project / "job.json")["stages"]["simulation"]["status"], "pending")
                self.assertEqual((project / "job.json").read_bytes(), original_job)

    def test_assemble_preserves_schema2_robot_and_persists_explicit_upgrade_after_success(self):
        project = self.start()
        job = cli.read_json(project / "job.json")
        job["simulation"]["robot_platform"] = "hexa-v1"
        cli.write_json(project / "job.json", job)
        original_job = (project / "job.json").read_bytes()
        self.assertEqual(self.invoke("status", "pirate-a")[0], 0)
        self.assertEqual((project / "job.json").read_bytes(), original_job)
        self.install_fixture_simulation_exporter()
        (project / "work/shell.stl").write_bytes(b"fixture shell")
        code, result = self.invoke("assemble", "pirate-a", "--shell", "work/shell.stl", "--output", "delivery/legacy")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["robot_platform"], "hexa-v1")
        legacy_report = cli.read_json(project / "delivery/legacy/simulation-report.json")
        self.assertEqual(legacy_report["robot_profile_sha256"], cli.sha(self.root / "robots/hexa-v1/profile.json"))
        code, result = self.invoke("assemble", "pirate-a", "--shell", "work/shell.stl",
                                   "--robot-platform", "jumper-v1-6", "--output", "delivery/latest")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["robot_platform"], "jumper-v1-6")
        upgraded = cli.read_json(project / "job.json")
        self.assertEqual(upgraded["simulation"]["robot_platform"], "jumper-v1-6")
        self.assertEqual(self.invoke("status", "pirate-a")[1]["stages"]["simulation"]["status"], "recorded")

    def test_assemble_rejects_incomplete_or_misbound_reports_without_updating_job(self):
        project = self.start("--robot-platform", "hexa-v1")
        self.install_fixture_simulation_exporter()
        shell = project / "work/shell.stl"
        profile = self.root / "robots/jumper-v1-6/profile.json"
        original_profile = profile.read_bytes()
        original_job = (project / "job.json").read_bytes()
        modes = ("missing-whole", "empty-whole", "shell-only", "no-movable-joints", "boolean-counts",
                 "failed-whole", "wrong-root", "no-retained-links", "unknown-shell-parent", "failed-urdf",
                 "wrong-source-sha", "wrong-profile-sha", "profile-changes", "shell-changes")
        for mode in modes:
            with self.subTest(mode=mode):
                profile.write_bytes(original_profile)
                shell.write_bytes(mode.encode())
                code, result = self.invoke("assemble", "pirate-a", "--shell", "work/shell.stl",
                                           "--robot-platform", "jumper-v1-6", "--output", "delivery/" + mode)
                self.assertEqual(code, 2, result)
                self.assertEqual((project / "job.json").read_bytes(), original_job)

    def test_assemble_checkpoint_failure_does_not_persist_robot_override(self):
        project = self.start("--robot-platform", "hexa-v1")
        self.install_fixture_simulation_exporter()
        (project / "work/shell.stl").write_bytes(b"fixture shell")
        original_job = (project / "job.json").read_bytes()
        with patch.object(cli, "file_record", side_effect=OSError("fixture evidence read failed")):
            code, result = self.invoke("assemble", "pirate-a", "--shell", "work/shell.stl",
                                       "--robot-platform", "jumper-v1-6")
        self.assertEqual(code, 2, result)
        self.assertEqual((project / "job.json").read_bytes(), original_job)

    def test_assemble_blocks_missing_platform_before_launching_producer(self):
        shutil.rmtree(self.platform)
        self.start()
        with patch.object(cli.subprocess, "run", side_effect=AssertionError("Producer must not launch")):
            code, result = self.invoke("assemble", "pirate-a", "--shell", "missing.stl")
        self.assertEqual(code, 2)
        self.assertIn("already bound, valid platform", result["error"])


if __name__ == "__main__":
    unittest.main()
