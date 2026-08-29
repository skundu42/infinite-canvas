"""Checks for nfinite Canvas."""

from __future__ import annotations

import asyncio
import json
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
        self.assertEqual(
            [tool.name for tool in tools],
            ["get_canvas", "add_node", "update_node", "connect_nodes", "export_canvas"],
        )

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

    def test_update_node_only_changes_provided_fields(self) -> None:
        created = app.add_node("Draft", body="Keep me", color="#aabbcc")
        updated = app.update_node(created["canvas_id"], created["node"]["id"], title="Final", x=42)

        self.assertEqual(updated["node"]["title"], "Final")
        self.assertEqual(updated["node"]["body"], "Keep me")
        self.assertEqual(updated["node"]["color"], "#AABBCC")
        self.assertEqual(updated["node"]["x"], 42)
        self.assertEqual(updated["revision"], 2)

    def test_update_node_rejects_empty_patch_and_missing_node(self) -> None:
        created = app.add_node("Draft")
        with self.assertRaisesRegex(ValueError, "At least one"):
            app.update_node(created["canvas_id"], created["node"]["id"])
        with self.assertRaisesRegex(KeyError, "Node .* was not found"):
            app.update_node(created["canvas_id"], "0" * 32, title="Missing")

    def test_connect_nodes_is_directed_and_idempotent(self) -> None:
        source = app.add_node("Source")
        target = app.add_node("Target", canvas_id=source["canvas_id"])
        first = app.connect_nodes(source["canvas_id"], source["node"]["id"], target["node"]["id"], "leads to")
        duplicate = app.connect_nodes(
            source["canvas_id"], source["node"]["id"], target["node"]["id"], "leads to"
        )

        self.assertEqual(first["connection"]["id"], duplicate["connection"]["id"])
        self.assertEqual(duplicate["revision"], 3)
        self.assertEqual(len(app.get_canvas(source["canvas_id"])["connections"]), 1)

    def test_connect_nodes_rejects_self_links_and_missing_nodes(self) -> None:
        source = app.add_node("Source")
        with self.assertRaisesRegex(ValueError, "cannot connect to itself"):
            app.connect_nodes(source["canvas_id"], source["node"]["id"], source["node"]["id"])
        with self.assertRaisesRegex(KeyError, "Node .* was not found"):
            app.connect_nodes(source["canvas_id"], source["node"]["id"], "0" * 32)

    def test_export_canvas_returns_editable_json(self) -> None:
        created = app.add_node("Idea", body="Keep the objects editable")
        exported = app.export_canvas(created["canvas_id"], "json")

        self.assertEqual(exported["mime_type"], "application/json")
        self.assertEqual(json.loads(exported["content"]), app.get_canvas(created["canvas_id"]))

    def test_export_canvas_returns_escaped_standalone_svg(self) -> None:
        source = app.add_node("<script>", body="A & B")
        target = app.add_node("Target", canvas_id=source["canvas_id"])
        app.connect_nodes(source["canvas_id"], source["node"]["id"], target["node"]["id"], "<next>")
        exported = app.export_canvas(source["canvas_id"])

        self.assertEqual(exported["mime_type"], "image/svg+xml")
        self.assertIn("&lt;script&gt;", exported["content"])
        self.assertIn("&lt;next&gt;", exported["content"])
        self.assertNotIn("<script>", exported["content"])
        self.assertIn("marker-end", exported["content"])

    def test_export_canvas_rejects_unknown_format(self) -> None:
        created = app.add_node("Card")
        with self.assertRaisesRegex(ValueError, "Format must be"):
            app.export_canvas(created["canvas_id"], "png")


if __name__ == "__main__":
    unittest.main()
