import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication

from quick_launcher.hotcorner import HotCorner


class HotCornerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QApplication.instance() or QApplication([])

    def test_each_corner_respects_zone_boundaries(self) -> None:
        detector = HotCorner(zone_px=8)
        geometry = QRect(100, 200, 300, 200)
        expectations = {
            "top_left": (QPoint(107, 207), QPoint(108, 207)),
            "top_right": (QPoint(399, 207), QPoint(391, 207)),
            "bottom_left": (QPoint(107, 399), QPoint(108, 399)),
            "bottom_right": (QPoint(399, 399), QPoint(391, 399)),
        }
        for position, (inside, outside) in expectations.items():
            detector.configure(position, 8, 250)
            with self.subTest(position=position):
                self.assertTrue(detector._contains(inside, geometry))
                self.assertFalse(detector._contains(outside, geometry))

    def test_runtime_configuration_and_disable_reset_detector(self) -> None:
        detector = HotCorner()
        detector.configure("bottom_left", 24, 600)
        self.assertTrue(detector._contains(QPoint(23, 299), QRect(0, 0, 400, 300)))
        self.assertEqual(detector._zone_px, 24)
        self.assertEqual(detector._dwell_seconds, 0.6)
        detector.set_enabled(False)
        self.assertFalse(detector._timer.isActive())


if __name__ == "__main__":
    unittest.main()
