# draw.io Architecture Diagrams (examples)

> **Status:** Example / sample only. These files exist to compare draw.io XML
> with the canonical Mermaid source in `docs/architecture-diagrams.md`.
> They are NOT the source of truth. Do not edit architecture here — edit the
> Mermaid file and regenerate if draw.io is adopted.

## What is draw.io?

[draw.io](https://app.diagrams.net) (also marketed as **diagrams.net**) is an
open-source diagramming tool. Files are stored as **plain XML** (`.drawio` or
`.xml`), which means:

- **Editable** in the browser (`app.diagrams.net`), the desktop app, or VS Code
- **Diffable** in git (more so than PNG/PDF, less so than Mermaid)
- **Renderable** by many tools (Confluence, GitHub via renderers, mkdocs plugins)
- **Self-contained** — no online service required for editing

## Files in this folder

| File                       | Diagram                       | Source section in `architecture-diagrams.md` |
| -------------------------- | ----------------------------- | ------------------------------------------- |
| `system-architecture.drawio`   | System architecture         | § 1                                         |
| `agent-sequence.drawio`        | Agent execution sequence    | § 2                                         |
| `context-data-flow.drawio`     | Context management data flow| § 3                                         |
| `evaluation-system.drawio`     | Evaluation system           | § 4                                         |

All four diagrams are stored as **separate `<diagram>` blocks** could be put
into a single `.drawio` file, but we keep one file per diagram to make diffs
and PRs reviewable.

## How to open

### Option A — Browser (no install)

1. Go to <https://app.diagrams.net>
2. **File → Open from Device** → pick the `.drawio` file
3. Edit visually, then **File → Export as → XML** to save back

### Option B — VS Code (recommended for this repo)

Install the extension **"Draw.io Integration"** (`hediet.vscode-drawio`):

- Open any `.drawio` file directly in VS Code
- Edit side-by-side with code; the diagram is rendered live
- Save in place (`.drawio` files are plain XML, version-controllable)

### Option C — Desktop app

Download from <https://github.com/jgraph/drawio-desktop/releases>. Same UX
as the browser version, works offline.

## draw.io vs Mermaid — pros and cons

| Aspect                     | Mermaid (current)                                | draw.io (this folder)                                  |
| -------------------------- | ------------------------------------------------ | ------------------------------------------------------ |
| **Editing UX**             | Code-only, no WYSIWYG                            | Full drag-and-drop, WYSIWYG                            |
| **Git diffs**              | Best — plain text, line-based                    | OK — XML is line-friendly but element ordering can shuffle on re-save |
| **GitHub rendering**       | Native in markdown                               | Needs renderer (e.g. `hediet/vscode-drawio` action, mkdocs plugin, or commit a PNG export) |
| **Diagram complexity**     | Struggles past ~25 nodes; labels get truncated   | Handles 50+ nodes; free-form positioning; no auto-layout limits |
| **Sequence diagrams**      | First-class (`sequenceDiagram`)                  | Manual: actor lifelines + arrows (see `agent-sequence.drawio`) |
| **Flowcharts**             | First-class                                      | First-class, with decision/action/conector shapes       |
| **Shape library**          | Limited (rect/circle/diamond/cloud/stadium)      | Hundreds: AWS, Azure, GCP, K8s, Cisco, UML, BPMN, etc.  |
| **Styling**                | Theme + classDef; coarse                         | Per-cell CSS-like style strings; per-edge colors, dashed/dotted, custom arrowheads |
| **Containers / grouping**   | `subgraph` only                                 | Swimlanes, group containers, nested boxes, plus a real "background" rectangle |
| **Cross-references**       | Via subgraphs                                    | One cell can reference another by `id`; layers/z-order independent of order |
| **Learning curve**         | Low for devs                                     | Low for designers, medium for devs                      |
| **Round-trip with code**   | Direct — code IS the diagram                     | Indirect — must re-export or hand-edit XML              |

## When to choose which

**Stay with Mermaid** if:
- Architecture changes are rare (quarterly or less)
- You want one source of truth in a single markdown file
- Readers are 100% on GitHub

**Move to draw.io** if:
- Architecture changes weekly and you need visual editing
- Diagrams grow past ~20 nodes and Mermaid starts auto-layout-ing badly
- You need swimlanes, group containers, or non-flowchart shapes (AWS icons, etc.)
- Reviewers want to comment on shape positions, not just text

## Things draw.io does that Mermaid cannot

1. **Free-form positioning.** drag any cell anywhere; no auto-layout to fight.
2. **Shape variety.** AWS/GCP/Azure/Kubernetes/Cisco/BPMN/UML out of the box
   (see <https://www.drawio.com/shapes>).
3. **Swimlanes / containers** as first-class layout primitives, not nested
   subgraphs. See the 7-lifeline sequence in `agent-sequence.drawio` — the
   lifelines and headers are independent cells you can reposition.
4. **Per-edge styling.** Color, dash pattern, arrowhead, and label background
   are all independent attributes. The `→ solid / ⇢ dashed` legend in
   `agent-sequence.drawio` uses different `endArrow=classic` vs
   `endArrow=open` + `dashed=1` per edge.
5. **Layered groups.** A rectangle can act as a `parent=` for a sub-tree; move
   the parent, children follow. Useful for "drag the whole eval subsystem
   around."
6. **Embedded images / icons.** A cell can hold an SVG/PNG; useful for logo
   plates on architecture overviews.
7. **Multi-page files.** A single `.drawio` file can hold many `<diagram>`
   pages — tabs at the bottom of the editor.

## How these examples were generated

Hand-written, **not** auto-converted from Mermaid. The intent is to show what
draw.io's XML *feels* like — both for reading and for editing. If draw.io is
adopted, a small conversion script (Mermaid → draw.io via `mmdc` + `drawio`
CLI, or a custom parser) would be more maintainable than hand-writing.

## Regenerating from Mermaid (future)

If/when draw.io becomes canonical, a likely pipeline is:

```bash
# 1. render Mermaid to PNG (sanity check)
npx -p @mermaid-js/mermaid-cli mmdc -i architecture-diagrams.md -o out/png

# 2. parse Mermaid → emit draw.io XML (custom script)
node scripts/mermaid-to-drawio.mjs docs/architecture-diagrams.md \
  > docs/architecture-comparison/drawio/system-architecture.drawio

# 3. visually verify in VS Code
code docs/architecture-comparison/drawio/*.drawio
```

The custom script is non-trivial because Mermaid's `sequenceDiagram` and
`flowchart` grammars differ from draw.io's cell/edge model. Expect ~300 LOC
for a faithful converter.
