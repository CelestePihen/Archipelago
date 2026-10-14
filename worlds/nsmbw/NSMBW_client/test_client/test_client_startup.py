import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile

from ... import Utils as nsmbw_utils


class TestDolphinProcessDetection(unittest.TestCase):
    def setUp(self) -> None:
        self.psutil = Mock(
            STATUS_ZOMBIE="zombie", STATUS_DEAD="dead",
            NoSuchProcess=ProcessLookupError, AccessDenied=PermissionError,
        )
        self.enterContext(patch.dict("sys.modules", {"dolphin_memory_engine": Mock(), "psutil": self.psutil}))
        self.enterContext(patch.dict("os.environ", {"DME_DOLPHIN_PROCESS_NAME": ""}))
        self.enterContext(patch("Utils.get_settings", return_value={
            "nsmbw_settings": SimpleNamespace(dolphin_process_name="", dolphin_instance_override=False),
        }))
        from .. import dolphin_interface_client

        self.client = dolphin_interface_client
        self.enterContext(patch.object(self.client, "psutil", self.psutil))
        self.enterContext(patch.object(self.client, "get_settings", return_value={
            "nsmbw_settings": SimpleNamespace(dolphin_instance_override=False),
        }))

    def test_linux_ignores_file_manager_tools_and_dead_processes(self) -> None:
        processes = []
        for name, status in [
            ("dolphin", "running"), ("dolphin-tool", "running"),
            ("dolphin-emu", "zombie"), ("dolphin-emu", "dead"),
        ]:
            process = Mock()
            process.name.return_value = name
            process.status.return_value = status
            processes.append(process)
        self.psutil.process_iter.return_value = processes
        with patch("Utils.is_linux", True):
            self.assertEqual(self.client.get_num_dolphin_instances(), 0)
            self.assertTrue(self.client.assert_no_running_dolphin())

    def test_emulator_names_on_each_platform(self) -> None:
        for linux, windows, name in [
            (True, False, "dolphin-emu"), (True, False, "dolphin-emu-qt2"), (True, False, "dolphin-emu-nogui"),
            (False, True, "Dolphin.exe"), (False, False, "Dolphin"), (False, False, "Dolphin-custom"),
        ]:
            with self.subTest(linux=linux, windows=windows, name=name), \
                    patch("Utils.is_linux", linux), patch("Utils.is_windows", windows):
                process = Mock()
                process.name.return_value = name
                process.status.return_value = "running"
                self.psutil.process_iter.return_value = [process]
                self.assertEqual(self.client.get_num_dolphin_instances(), 1)
                self.assertFalse(self.client.assert_no_running_dolphin())

    def test_windows_requires_exact_emulator_name(self) -> None:
        with patch("Utils.is_linux", False), patch("Utils.is_windows", True):
            for name, expected in [("Dolphin.EXE", 1), ("dolphin", 0), ("Dolphin-custom.exe", 0),
                                   ("dolphin-tool.exe", 0)]:
                with self.subTest(name=name):
                    process = Mock()
                    process.name.return_value = name
                    process.status.return_value = "running"
                    self.psutil.process_iter.return_value = [process]
                    self.assertEqual(self.client.get_num_dolphin_instances(), expected)

    def test_custom_process_name_and_inaccessible_processes(self) -> None:
        custom = Mock()
        custom.name.return_value = "Custom-Emulator"
        custom.status.return_value = "running"
        other = Mock()
        other.name.return_value = "dolphin-emu"
        gone = Mock()
        gone.name.side_effect = ProcessLookupError
        denied = Mock()
        denied.name.side_effect = PermissionError
        self.psutil.process_iter.return_value = [gone, denied, other, custom]
        for linux, windows in [(True, False), (False, True), (False, False)]:
            with self.subTest(linux=linux, windows=windows), \
                    patch("Utils.is_linux", linux), patch("Utils.is_windows", windows), \
                    patch.dict("os.environ", {"DME_DOLPHIN_PROCESS_NAME": "custom-emulator"}):
                self.assertEqual(self.client.get_num_dolphin_instances(), 1)


class TestClientManifest(unittest.TestCase):
    def test_manifest_from_apworld_and_sources(self) -> None:
        manifest = {"game": "NSMBW", "world_version": "0.4.0"}
        with TemporaryDirectory() as folder:
            source = Path(folder) / "nsmbw"
            source.mkdir()
            (source / "archipelago.json").write_text(json.dumps(manifest), encoding="utf-8")
            archive = Path(folder) / "nsmbw.apworld"
            with ZipFile(archive, "w") as pack:
                pack.writestr("nsmbw/archipelago.json", json.dumps(manifest))
            for frozen, path in [(False, source / "Utils.py"), (True, archive / "nsmbw/Utils.py")]:
                with self.subTest(frozen=frozen), patch("Utils.is_frozen", return_value=frozen), \
                        patch.object(nsmbw_utils, "__file__", str(path)):
                    self.assertEqual(nsmbw_utils.read_manifest(), manifest)
