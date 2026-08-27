import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from quick_launcher.hotcorner_preview import HotCornerPreview
from quick_launcher.settings import HotCornerDialog


class HotCornerPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_corner_rect_matches_each_screen_corner(self) -> None:
        geometry = QRect(100, 200, 300, 200)
        self.assertEqual(HotCornerPreview.corner_rect(geometry, "top_left", 8), QRect(100, 200, 8, 8))
        self.assertEqual(HotCornerPreview.corner_rect(geometry, "top_right", 8), QRect(392, 200, 8, 8))
        self.assertEqual(HotCornerPreview.corner_rect(geometry, "bottom_left", 8), QRect(100, 392, 8, 8))
        self.assertEqual(HotCornerPreview.corner_rect(geometry, "bottom_right", 8), QRect(392, 392, 8, 8))

    def test_preview_overlays_are_transparent_and_cleanup(self) -> None:
        preview = HotCornerPreview()
        preview.show("bottom_left", 24)
        self.assertEqual(len(preview._overlays), len(QGuiApplication.screens()))
        self.assertTrue(all(
            overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            for overlay in preview._overlays
        ))
        self.assertTrue(all(overlay.width() == 24 and overlay.height() == 24 for overlay in preview._overlays))
        self.assertTrue(all("rgba(255, 255, 255, 145)" in overlay.styleSheet()
                            for overlay in preview._overlays))
        preview.clear()
        self.assertEqual(preview._overlays, [])

    def test_dialog_updates_preview_and_removes_it_on_cancel(self) -> None:
        dialog = HotCornerDialog("top_right", 8, 250, "light")
        dialog.show()
        self.qt_app.processEvents()
        dialog._zone.setValue(32)
        self.assertTrue(dialog._preview._overlays)
        self.assertTrue(all(overlay.width() == 32 for overlay in dialog._preview._overlays))
        dialog.reject()
        self.assertEqual(dialog._preview._overlays, [])


if __name__ == "__main__":
    unittest.main()
