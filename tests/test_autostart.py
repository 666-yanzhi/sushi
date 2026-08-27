import unittest
from unittest.mock import Mock

from quick_launcher.app import _save_settings_with_autostart
from quick_launcher.autostart import AutostartError, WindowsAutostart, startup_command
from quick_launcher.models import LauncherConfig, LauncherSettings


class _RegistryKey:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _Registry:
    HKEY_CURRENT_USER = object()
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def OpenKey(self, *args):
        return _RegistryKey()

    def SetValueEx(self, key, name, reserved, kind, value) -> None:
        self.values[name] = value

    def DeleteValue(self, key, name) -> None:
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class AutostartTests(unittest.TestCase):
    def test_writes_and_removes_current_user_run_entry(self) -> None:
        registry = _Registry()
        service = WindowsAutostart(registry)
        service.set_enabled(True)
        self.assertIn(WindowsAutostart.VALUE_NAME, registry.values)
        self.assertIn("main.py", registry.values[WindowsAutostart.VALUE_NAME])
        service.set_enabled(False)
        self.assertNotIn(WindowsAutostart.VALUE_NAME, registry.values)

    def test_source_startup_command_quotes_python_and_entrypoint(self) -> None:
        command = startup_command()
        self.assertIn("main.py", command)

    def test_failed_config_save_restores_autostart_state(self) -> None:
        previous = LauncherConfig(1, (), (), LauncherSettings(launch_at_login=False))
        candidate = LauncherConfig(1, (), (), LauncherSettings(launch_at_login=True))
        store = Mock()
        store.save.side_effect = OSError("disk full")
        autostart = Mock()
        error = _save_settings_with_autostart(store, autostart, previous, candidate)
        self.assertIn("保存设置失败", error or "")
        self.assertEqual(autostart.set_enabled.call_args_list[0].args, (True,))
        self.assertEqual(autostart.set_enabled.call_args_list[1].args, (False,))

    def test_autostart_failure_prevents_config_save(self) -> None:
        previous = LauncherConfig(1, (), (), LauncherSettings())
        candidate = LauncherConfig(1, (), (), LauncherSettings(launch_at_login=True))
        store = Mock()
        autostart = Mock()
        autostart.set_enabled.side_effect = AutostartError("注册表被拒绝")
        error = _save_settings_with_autostart(store, autostart, previous, candidate)
        self.assertIn("注册表被拒绝", error or "")
        store.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
