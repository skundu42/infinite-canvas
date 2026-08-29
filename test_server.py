"""Checks for nfinite Canvas."""

from __future__ import annotations

import unittest

import server as app


class CanvasStateTests(unittest.TestCase):
    def setUp(self) -> None:
        with app._store_lock:
            app._canvases.clear()

    def test_canvases_are_isolated_and_returns_are_copies(self) -> None:
        first = app._create_canvas()
        second = app._create_canvas()

        self.assertNotEqual(first["id"], second["id"])
        first["revision"] = 99
        self.assertEqual(app._get_canvas(first["id"])["revision"], 0)

    def test_missing_canvas_is_rejected(self) -> None:
        with self.assertRaisesRegex(KeyError, "was not found"):
            app._get_canvas("missing")


if __name__ == "__main__":
    unittest.main()
