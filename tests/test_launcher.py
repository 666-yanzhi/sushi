import unittest
from unittest.mock import patch

from quick_launcher.launcher import LaunchError, TargetLauncher
from quick_launcher.models import AppEntry


class _ElevationRequired(OSError):
    winerror = 740


class TargetLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = AppEntry("admin", "管理员工具", "system", "admin-tool.exe", ("--safe",), "C:\\work")

    @patch.object(TargetLauncher, "_open_elevated")
    @patch("quick_launcher.launcher.subprocess.Popen", side_effect=_ElevationRequired("elevation"))
    def test_retries_with_uac_only_after_elevation_required(self, popen, elevated) -> None:
        TargetLauncher().open(self.entry)
        elevated.assert_called_once_with("admin-tool.exe", ("--safe",), "C:\\work")

    @patch("quick_launcher.launcher.sys.platform", "win32")
    @patch("quick_launcher.launcher._shell_execute_runas", return_value=(5, 1223))
    def test_reports_when_user_cancels_uac(self, shell_execute) -> None:
        with self.assertRaisesRegex(LaunchError, "取消管理员授权"):
            TargetLauncher._open_elevated("admin-tool.exe", (), None)

    @patch("quick_launcher.launcher.sys.platform", "win32")
    @patch("quick_launcher.launcher._shell_execute_runas", return_value=(33, 0))
    def test_accepts_successful_uac_launch(self, shell_execute) -> None:
        TargetLauncher._open_elevated("admin-tool.exe", (), None)
        shell_execute.assert_called_once_with("admin-tool.exe", (), None)


if __name__ == "__main__":
    unittest.main()
