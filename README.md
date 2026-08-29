# Infinite Canvas — A live spatial board for AI and people

<p>
  <a href="https://github.com/mcp-use/mcp-use">Built with <b>mcp-use</b></a>
  &nbsp;
  <a href="https://github.com/mcp-use/mcp-use">
    <img src="https://img.shields.io/github/stars/mcp-use/mcp-use?style=social" alt="mcp-use stars">
  </a>
</p>

An AI-assisted freeform canvas for mind maps, architecture diagrams, research boards, project plans, customer journeys, and agent designs. Models and browser users edit the same positioned cards and connections incrementally—without generating Mermaid source.

## Features

- **Shared live board** — MCP tools and the browser edit the same canvas
- **Freeform cards** — create, select, edit, drag, and move cards with the keyboard
- **Directed connections** — link cards with optional labels
- **Canvas navigation** — pan, zoom, and reset the viewport
- **Live synchronization** — browser polling picks up model changes once per second
- **Portable exports** — download editable JSON or standalone SVG
- **Dependency-free UI** — the browser editor is plain HTML, CSS, and JavaScript

## Tools

| Tool | Description |
|------|-------------|
| `get_canvas` | Return a canvas's revision, positioned cards, and connections |
| `add_node` | Add a card, creating a canvas when `canvas_id` is omitted |
| `update_node` | Patch selected card fields or its position |
| `connect_nodes` | Add an optionally labeled, directed connection |
| `export_canvas` | Export editable JSON or standalone SVG |

## How it works

Start a board by calling `add_node` without a `canvas_id`. The result includes the generated canvas ID. Open the corresponding browser board and pass that ID to later tool calls:

```text
https://YOUR_HOST/?canvas=CANVAS_ID
```

The MCP endpoint is:

```text
https://YOUR_HOST/mcp
```

Infinite Canvas is a standalone collaborative browser experience, not an embedded MCP App widget.

## Local development

Requires Python 3.11 or newer.

```bash
git clone https://github.com/skundu42/infinite-canvas.git
cd infinite-canvas
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

Open the canvas at <http://localhost:8000>. Visit <http://localhost:8000/mcp> in a browser for the connection guide, or use that same URL in an MCP client.

Run the test suite:

```bash
python -m unittest -v
```

`HOST` and `PORT` override the default `0.0.0.0:8000` listener.

## Deploy to Manufact

Install the Manufact GitHub App for this repository, then deploy from the project directory:

```bash
npx mcp-use login
npx mcp-use deploy --name infinite-canvas --start-command "python server.py" --open
```

Once the deployment is running, copy its generated MCP URL from the Manufact dashboard.

## Setup on ChatGPT

1. Open **Settings** > **Apps and Connectors** > **Advanced Settings** and enable **Developer Mode**
2. Go to **Connectors** > **Create**, name it "Infinite Canvas," and paste the hosted `/mcp` URL
3. In a new chat, click **+** > **More** and select the Infinite Canvas connector

## Setup on Claude

1. Open **Settings** > **Connectors** > **Add custom connector**
2. Paste the hosted `/mcp` URL and save
3. The Infinite Canvas tools will be available in new conversations

## Built with

- [mcp-use](https://github.com/mcp-use/mcp-use) — MCP server framework
- Python standard library — canvas state, validation, JSON, and SVG generation
- Plain HTML, CSS, and JavaScript — browser canvas

## Current limits

State is intentionally process-local and resets when the server restarts. Canvas IDs isolate boards within one process, but this template does not provide authentication, durable storage, deletion, or multi-worker synchronization.
