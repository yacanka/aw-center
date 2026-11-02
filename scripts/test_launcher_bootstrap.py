"""Managed toolchain and CMD trust contract tests."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.launcher import installation_sources as sources
from scripts.launcher import toolchain
from scripts.launcher.model import LauncherError


class ToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.artifacts = {}
        for name, version, executable in (("python", "3.11.18", "python/python.exe"), ("node", "22.23.4", "node/node.exe"), ("npm", "10.9.4", "package/bin/npm-cli.js")):
            archive = self.root / (name + ".zip")
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr(executable, name)
            self.artifacts[name] = sources.Artifact(name, version, archive.name, "https://example.com/" + archive.name, hashlib.sha256(archive.read_bytes()).hexdigest(), "zip", executable)

    def install(self):
        def fetch(artifact, cache, settings):
            destination = cache / artifact.filename
            destination.write_bytes((self.root / artifact.filename).read_bytes())
            return destination
        with patch.object(toolchain, "load_catalog", return_value=self.artifacts), patch.object(toolchain, "fetch_artifact", side_effect=fetch), patch.object(toolchain, "_check_version"):
            return toolchain.ensure_toolchain(self.root / "home", sources.SourceSettings())

    def test_install_preserves_global_path_and_provides_pinned_npm(self):
        previous = os.environ.get("PATH")
        environment = self.install()
        self.assertEqual(os.environ.get("PATH"), previous)
        self.assertEqual(environment["PYTHONDONTWRITEBYTECODE"], "1")
        from scripts.launcher.installation_permissions import require_private
        for relative in ("", "cache", "cache/runtimes", "runtimes"):
            require_private(self.root / "home" / relative)
        self.assertTrue(Path(environment["AWCENTER_MANAGED_PYTHON"]).is_file())
        wrapper = self.root / "home/runtimes/npm-10.9.4/bin/npm.cmd"
        self.assertIn("npm-cli.js", wrapper.read_text())
        self.assertNotIn(str(self.root), wrapper.read_text())
        self.assertIn("DisableDelayedExpansion", wrapper.read_text())
        with patch.object(toolchain, "load_catalog", return_value=self.artifacts):
            self.assertTrue(all(item["status"] == "ready" for item in toolchain.inspect_toolchain(self.root / "home")))

    def test_inspect_missing_is_read_only(self):
        home = self.root / "absent"
        with patch.object(toolchain, "load_catalog", return_value=self.artifacts):
            checks = toolchain.inspect_toolchain(home)
        self.assertEqual(len(checks), 3)
        self.assertTrue(all(item["status"] == "missing" for item in checks))
        self.assertFalse(home.exists())

    def test_tampered_installation_is_reported_and_not_executed(self):
        environment = self.install()
        Path(environment["AWCENTER_MANAGED_PYTHON"]).write_text("tampered")
        with patch.object(toolchain, "load_catalog", return_value=self.artifacts), patch.object(toolchain, "_check_version") as run:
            checks = toolchain.inspect_toolchain(self.root / "home")
        self.assertEqual(checks[0]["status"], "invalid")
        run.assert_not_called()

    def test_forged_runtime_receipt_cannot_authorize_modified_node(self):
        environment = self.install()
        node = Path(environment["AWCENTER_MANAGED_NODE"])
        node.write_bytes(b"injected executable")
        receipt_path = self.root / "home/runtimes/node-22.23.4/.awcenter-tool.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["files"][self.artifacts["node"].executable] = hashlib.sha256(node.read_bytes()).hexdigest()
        receipt_path.write_text(json.dumps(receipt))
        with patch.object(toolchain, "load_catalog", return_value=self.artifacts):
            checks = toolchain.inspect_toolchain(self.root / "home")
        self.assertEqual(next(item for item in checks if item["name"] == "node")["status"], "invalid")

    @unittest.skipIf(os.name == "nt", "symlink creation requires host privilege on Windows")
    def test_inspection_rejects_symlinked_receipt(self):
        self.install()
        receipt = self.root / "home/runtimes/python-3.11.18/.awcenter-tool.json"
        moved = self.root / "receipt.json"
        receipt.replace(moved)
        receipt.symlink_to(moved)
        with patch.object(toolchain, "load_catalog", return_value=self.artifacts):
            checks = toolchain.inspect_toolchain(self.root / "home")
        self.assertEqual(checks[0]["status"], "invalid")

    def test_environment_is_read_only_and_requires_verified_receipts(self):
        expected = self.install()
        home = self.root / "home"
        before = {str(path): path.stat().st_mtime_ns for path in home.rglob("*")}
        with patch.object(toolchain, "load_catalog", return_value=self.artifacts), patch.object(toolchain, "fetch_artifact") as fetch:
            self.assertEqual(toolchain.toolchain_environment(home), expected)
            with self.assertRaises(LauncherError):
                toolchain.toolchain_environment(self.root / "missing")
        self.assertEqual(before, {str(path): path.stat().st_mtime_ns for path in home.rglob("*")})
        fetch.assert_not_called()

    def test_runtime_version_checks_ignore_inherited_interpreter_hooks(self):
        inherited = {"NODE_OPTIONS": "--require injected.js", "PYTHONPATH": "injected", "PYTHONHOME": "injected", "NODE_TLS_REJECT_UNAUTHORIZED": "0"}
        result = subprocess.CompletedProcess([], 0, stdout="22.23.4\n", stderr="")
        with patch.dict(os.environ, inherited), patch.object(toolchain.subprocess, "run", return_value=result) as run:
            toolchain._check_version(Path("node.exe"), "22.23.4")
        environment = run.call_args.kwargs["env"]
        for name in ("NODE_OPTIONS", "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE"):
            self.assertEqual(environment[name], "")
        self.assertEqual(environment["NODE_TLS_REJECT_UNAUTHORIZED"], "1")
        self.assertEqual(environment["PYTHONNOUSERSITE"], "1")

    def test_repeat_install_is_idempotent(self):
        first = self.install()
        receipts = list((self.root / "home/runtimes").glob("*/.awcenter-tool.json"))
        previous = [item.read_bytes() for item in receipts]
        self.assertEqual(self.install(), first)
        self.assertEqual([item.read_bytes() for item in receipts], previous)


class IsolatedVerifierTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        import importlib
        native_filesystem = importlib.import_module("nt" if os.name == "nt" else "posix")
        import sys
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.runtime = self.root / "runtime"
        self.runtime.mkdir()
        self.files = {"python/python.exe": b"exe", "python/python311.dll": b"dll", "python/Lib/encodings/utf_8.py": b"encoding", "python/Lib/late.py": b"stdlib"}
        self.manifest = self.root / "inventory.sha256"
        for relative, data in self.files.items():
            target = self.runtime / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.manifest.write_bytes("".join(hashlib.sha256(data).hexdigest() + "|" + relative + "\n" for relative, data in self.files.items()).encode("utf-8"))
        spec = importlib.util.spec_from_file_location("isolated_verifier_fixture", Path("scripts/launcher/installation_verify_python.py"))
        self.verifier = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"nt": native_filesystem}), patch.object(sys, "builtin_module_names", (*sys.builtin_module_names, "nt")):
            spec.loader.exec_module(self.verifier)

    def verify(self):
        return self.verifier.verify_runtime(str(self.runtime), str(self.manifest))

    def test_full_reviewed_inventory_accepts_exact_runtime_and_reserved_receipt(self):
        (self.runtime / ".awcenter-tool.json").write_text("not trusted or parsed")
        self.verify()

    def test_mutated_dll_encoding_and_late_stdlib_are_rejected(self):
        for relative in ("python/python311.dll", "python/Lib/encodings/utf_8.py", "python/Lib/late.py"):
            with self.subTest(relative=relative):
                target = self.runtime / relative
                target.write_bytes(b"injected")
                with self.assertRaises(self.verifier.IntegrityError):
                    self.verify()
                target.write_bytes(self.files[relative])

    def test_extra_startup_paths_pth_pyc_and_directory_are_rejected(self):
        for relative in ("python/python._pth", "python/python311.zip", "python/pyvenv.cfg", "python/Lib/sitecustomize.py", "python/Lib/extra.pyc", "python/Lib/site-packages/injected.pth"):
            with self.subTest(relative=relative):
                target = self.runtime / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"injected")
                with self.assertRaises(self.verifier.IntegrityError):
                    self.verify()
                target.unlink()
                if relative.startswith("python/Lib/site-packages/"):
                    target.parent.rmdir()
        (self.runtime / "unexpected").mkdir()
        with self.assertRaises(self.verifier.IntegrityError):
            self.verify()

    def test_reviewed_manifest_has_complete_native_startup_closure(self):
        directory = Path("scripts/launcher")
        full = dict(line.split("|", 1)[::-1] for line in (directory / "installation_python.sha256").read_text().splitlines())
        startup = dict(line.split("|", 1)[::-1] for line in (directory / "installation_python_startup.sha256").read_text().splitlines())
        self.assertEqual(len(full), 3983)
        self.assertTrue(all(full[name] == digest for name, digest in startup.items()))
        self.assertEqual({name for name in full if name.count("/") == 1}, {name for name in startup if name.count("/") == 1})
        for module in ("__init__", "aliases", "utf_8"):
            self.assertIn(f"python/Lib/encodings/{module}.py", startup)
            self.assertIn(f"python/Lib/encodings/__pycache__/{module}.cpython-311.pyc", startup)


class BootstrapContractTests(unittest.TestCase):
    def test_cmd_pins_match_catalog_and_doctor_precedes_writes(self):
        script = Path("AWCenter.cmd").read_text()
        python = sources.load_catalog()["python"]
        self.assertIn(python.sha256, script)
        self.assertIn(python.filename, script)
        self.assertIn("DisableDelayedExpansion", script)
        self.assertNotIn("powershell", script.lower())
        self.assertLess(script.index(":readonly"), script.index(":bootstrap"))
        self.assertIn("--offline-dir", script)
        self.assertIn("--repository", script)
        self.assertIn("--ca-file", script)
        self.assertIn("--cacert", script)
        self.assertIn("certutil.exe", script)
        self.assertIn("--proto-redir", script)
        self.assertIn("--disallow-username-in-url", script)
        self.assertIn("installation_python_startup.sha256", script)
        self.assertIn(" -I -S -B -X utf8 ", script)
        self.assertIn("--disable --cacert", script)
        self.assertIn("--disable --silent", script)


@unittest.skipUnless(os.name == "nt", "native CMD checks require Windows")
class NativeReadOnlyBootstrapTests(unittest.TestCase):
    def test_help_and_doctor_without_python_or_inherited_path_do_not_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "Local AppData ! & (test)"
            home.mkdir()
            before = list(home.rglob("*"))
            environment = os.environ.copy()
            environment.update(LOCALAPPDATA=str(home), PATH="", AWC_STAGE=str(home))
            script = Path("AWCenter.cmd").resolve()
            command = str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")
            for arguments, status in (("--help", 0), ("doctor --profile dev", 1)):
                command_line = f'"{command}" /d /s /c ""{script}" {arguments}"'
                result = subprocess.run(command_line, env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, status, result.stdout + result.stderr)
                self.assertEqual(list(home.rglob("*")), before)
            self.assertTrue(home.is_dir(), "inherited staging variable must never be removed")


@unittest.skipUnless(os.name == "nt" and os.environ.get("AWCENTER_RUN_WINDOWS_INSTALL_SMOKE") == "1", "native trust-chain smoke requires opt-in Windows downloads")
class NativeTrustChainSmokeTests(unittest.TestCase):
    def test_hostile_curl_config_and_mutated_runtime_cannot_execute(self):
        with tempfile.TemporaryDirectory(prefix="AWC trust ! & ") as temporary:
            root = Path(temporary)
            offline = root / "offline"
            python = sources.load_catalog()["python"]
            sources.fetch_artifact(python, offline, sources.SourceSettings())
            local = root / "local"
            local.mkdir()
            config = root / "curl config"
            config.mkdir()
            traced = root / "curl-config-was-read.txt"
            for filename in (".curlrc", "_curlrc"):
                (config / filename).write_text('insecure\ntrace-ascii = "' + traced.as_posix() + '"\n')
            environment = os.environ.copy()
            environment.update(LOCALAPPDATA=str(local), PATH=str(Path(os.environ["SystemRoot"]) / "System32"), CURL_HOME=str(config), HTTPS_PROXY="http://127.0.0.1:9", PYTHONDONTWRITEBYTECODE="1")
            command = str(Path(os.environ["SystemRoot"]) / "System32/cmd.exe")
            script = Path("AWCenter.cmd").resolve()
            def run(arguments):
                command_line = f'"{command}" /d /s /c ""{script}" {arguments}"'
                return subprocess.run(command_line, env=environment, capture_output=True, text=True, errors="replace", timeout=180)
            result = run(f'start --profile dev --offline-dir "{offline}"')
            runtime = local / "AWCenter/runtimes/python-3.11.18"
            self.assertTrue((runtime / python.executable).is_file(), result.stdout + result.stderr)
            self.assertFalse(traced.exists(), "curl must ignore hostile per-user configuration")
            marker_path = root / "untrusted-startup-ran.txt"
            injection = ('\nopen(' + repr(str(marker_path)) + ', "w").write("untrusted")\n').encode()
            for relative in ("python/python311.dll", "python/Lib/encodings/utf_8.py", "python/Lib/pathlib.py", "python/Lib/encodings/aliases/__init__.py", "python/Lib/encodings/aliases.pyd", "python/Lib/site-packages/injected.pth", "python/python._pth", "pyvenv.cfg"):
                with self.subTest(relative=relative):
                    target = runtime / relative
                    existed = target.exists()
                    previous = target.read_bytes() if existed else b""
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(previous + injection)
                    try:
                        rejected = run("doctor --profile dev")
                        self.assertNotEqual(rejected.returncode, 0)
                        self.assertIn("[error]", rejected.stdout + rejected.stderr)
                        self.assertFalse(marker_path.exists(), "unreviewed startup code must not run")
                    finally:
                        if existed:
                            target.write_bytes(previous)
                        else:
                            target.unlink()
                            if relative.endswith("aliases/__init__.py"):
                                target.parent.rmdir()


if __name__ == "__main__":
    unittest.main()
