"""Checks for nfinite Canvas."""

from __future__ import annotations

import asyncio
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
            app._get_canvas("0" * 32)

    def test_invalid_canvas_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Invalid canvas ID"):
            app.get_canvas("missing")

    def test_get_canvas_is_advertised(self) -> None:
        tools = asyncio.run(app.server.list_tools())
        self.assertEqual([tool.name for tool in tools], ["get_canvas", "add_node"])

    def test_add_node_creates_canvas_and_places_cards(self) -> None:
        first = app.add_node("Research")
        second = app.add_node("Evidence", canvas_id=first["canvas_id"])
        canvas = app.get_canvas(first["canvas_id"])

        self.assertEqual(first["node"]["x"], 80)
        self.assertEqual(second["node"]["x"], 360)
        self.assertEqual(canvas["revision"], 2)
        self.assertEqual([node["title"] for node in canvas["nodes"]], ["Research", "Evidence"])

    def test_add_node_validates_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "Title cannot be empty"):
            app.add_node("   ")
        with self.assertRaisesRegex(ValueError, "hexadecimal"):
            app.add_node("Card", color="red")


if __name__ == "__main__":
    unittest.main()
