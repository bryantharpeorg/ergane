#!/usr/bin/env python3
"""Render an Ergane spec trio as one readable HTML page.

The point is not prettier markdown. A spec is hard to read because the parts
that matter most are the machine parts — the Work Graph as raw YAML, anchors you
cannot verify by looking, coverage you have to compute — and this resolves all
three against the tree before it renders anything.

Usage:
    python3 render.py <spec-dir> [-o out.html] [--tree <dir>] [--landed]

`--tree` is the tree anchors are resolved against; it defaults to the repository
root. Point it at a checkout of the landing branch when you want the answer an
agent's worktree would get, which is not the same as your working copy.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass, field

from factory.spec import SpecValidation, validate_spec
from factory.workgraph.landed import landed_facts
from factory.workgraph.worktree import WorktreeError

ANCHOR_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|ya?ml|toml|sql|sh)):(\d+)(?:-(\d+))?`")
BARE_RE = re.compile(r"`:(\d+)(?:-(\d+))?`")
FILE_RE = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|md|ya?ml|toml|sql|sh))`")
STORY_RE = re.compile(r"^### User Story (\d+)\s*[-–]\s*(.+?)\s*\(Priority:\s*(P\d)\)", re.M)
FR_RE = re.compile(r"^- \*\*(FR-\d+)\*\*:\s*(.+)$", re.M)
SC_RE = re.compile(r"^- \*\*(SC-\d+)\*\*:\s*(.+)$", re.M)
TASK_RE = re.compile(r"^- \[([ x])\]\s+(T\d+[a-z]?)\s*(.*)$", re.M)
TRAP_RE = re.compile(r"^\*\*(\d+[a-z]?)\.\s+(.+?)\*\*", re.M)


@dataclass
class Anchor:
    doc: str
    doc_line: int
    path: str
    line: int
    end: int | None
    status: str = "ok"          # ok | blank | eof | missing
    text: str = ""


@dataclass
class Spec:
    slug: str
    title: str = ""
    state: str = "unknown"
    provenance: list[str] = field(default_factory=list)
    stories: list[tuple[str, str, str]] = field(default_factory=list)
    frs: list[tuple[str, str]] = field(default_factory=list)
    scs: list[tuple[str, str]] = field(default_factory=list)
    graph: dict = field(default_factory=dict)
    traps: list[tuple[str, str]] = field(default_factory=list)
    tasks: list[tuple[str, str, str]] = field(default_factory=list)
    anchors: list[Anchor] = field(default_factory=list)
    landed: dict[str, str] = field(default_factory=dict)
    sections: dict[str, str] = field(default_factory=dict)
    validation: SpecValidation | None = None
    landing_state: str = "unavailable"
    landing_detail: str = "no --landed-branch was supplied"


def split_frontmatter(text: str) -> tuple[list[str], str, int]:
    """Return (comment lines, body, body start line). Frontmatter closes on the 2nd `---`."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return [], text, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = [l.lstrip("# ").rstrip() for l in lines[1:i] if l.startswith("#")]
            return fm, "\n".join(lines[i + 1:]), i + 1
    return [], text, 0


def parse_graph(body: str) -> dict:
    """The `## Work Graph` yaml block, without a yaml dependency."""
    m = re.search(r"^## Work Graph\s*\n+```ya?ml\n(.*?)\n```", body, re.S | re.M)
    if not m:
        return {}
    graph: dict = {}
    current = None
    for raw in m.group(1).splitlines():
        if not raw.strip():
            continue
        if not raw.startswith((" ", "\t")):
            current = raw.split(":")[0].strip()
            graph[current] = {"depends_on": [], "depends_on_merged": [], "implements": [], "persona": None}
        elif current:
            key, _, val = raw.strip().partition(":")
            val = val.strip()
            if key in ("depends_on", "depends_on_merged", "implements"):
                graph[current][key] = [v.strip() for v in val.strip("[]").split(",") if v.strip()]
            elif key == "persona":
                graph[current]["persona"] = val
    return graph


def resolve_anchors(docs: dict[str, tuple[str, int]], tree: pathlib.Path) -> list[Anchor]:
    """Every `path:line` citation, resolved against `tree`. Frontmatter is skipped."""
    out: list[Anchor] = []
    cache: dict[str, list[str] | None] = {}
    for doc, (text, skip) in docs.items():
        lines = text.splitlines()
        # A bare `:NN` inherits the last qualified path — but only within the same
        # paragraph. Carrying it further guesses, and guessing here produces a
        # confident wrong answer: on 075 a `:1357` meant for workflow.py resolved
        # against a ladder.py cited two bullets earlier and reported EOF. A bare
        # ref with no antecedent in its own paragraph is reported `ambiguous`,
        # which is the true finding — a reader cannot resolve it either.
        last_path = None
        for i, line in enumerate(lines, 1):
            if i <= skip:
                continue
            if not line.strip():
                last_path = None
            for m in ANCHOR_RE.finditer(line):
                last_path = m.group(1)
                out.append(_probe(doc, i, m.group(1), int(m.group(2)),
                                  int(m.group(3)) if m.group(3) else None, tree, cache))
            # A filename with no line number is an antecedent too. Without this the
            # scan walks past `` `factory/cli/nouns/build.py` `` and resolves the
            # `:511` after it against whatever file was cited further up.
            for m in FILE_RE.finditer(line):
                last_path = m.group(1)
            for m in BARE_RE.finditer(line):
                line_no = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else None
                if last_path:
                    out.append(_probe(doc, i, last_path, line_no, end, tree, cache))
                else:
                    a = Anchor(doc, i, "(no file named in this paragraph)", line_no, end)
                    a.status = "ambiguous"
                    out.append(a)
    return out


def _probe(doc, doc_line, path, line, end, tree, cache) -> Anchor:
    a = Anchor(doc, doc_line, path, line, end)
    if path not in cache:
        p = tree / path
        cache[path] = p.read_text(encoding="utf-8").splitlines() if p.is_file() else None
    body = cache[path]
    if body is None:
        a.status = "missing"
    elif line > len(body):
        a.status = "eof"
    elif not body[line - 1].strip():
        a.status = "blank"
    else:
        a.text = body[line - 1].strip()
    return a


def read_landing(spec_dir: pathlib.Path, tree: pathlib.Path, branch: str | None):
    """Read landing facts without network access, or name why the answer is absent."""
    if not branch:
        return "unavailable", {}, "no --landed-branch was supplied"
    try:
        facts = landed_facts(
            tree,
            spec_dir.name,
            default_branch=branch,
            fetch=False,
        )
    except (WorktreeError, OSError) as error:
        return "error", {}, str(error)
    return ("empty" if not facts else "ready"), {
        story: fact.commit for story, fact in facts.items()
    }, "landing facts returned"


def load(
    spec_dir: pathlib.Path,
    tree: pathlib.Path,
    branch: str | None,
    *,
    specs_root: pathlib.Path,
) -> Spec:
    s = Spec(slug=spec_dir.name)
    docs: dict[str, tuple[str, int]] = {}
    bodies: dict[str, str] = {}
    for name in ("spec.md", "plan.md", "tasks.md"):
        p = spec_dir / name
        if not p.is_file():
            continue
        raw = p.read_text(encoding="utf-8")
        fm, body, skip = split_frontmatter(raw)
        docs[name] = (raw, skip)
        bodies[name] = body
        if name == "spec.md":
            s.provenance = fm
            for l in fm:
                pass
            m = re.search(r"^state:\s*(\w+)", raw, re.M)
            if m:
                s.state = m.group(1)
            t = re.search(r"^# Feature Specification:\s*(.+)$", body, re.M)
            s.title = t.group(1).strip() if t else spec_dir.name

    spec_body = bodies.get("spec.md", "")
    s.stories = [(f"US{n}", title, pri) for n, title, pri in STORY_RE.findall(spec_body)]
    s.frs = FR_RE.findall(spec_body)
    s.scs = SC_RE.findall(spec_body)
    s.graph = parse_graph(spec_body)
    s.traps = TRAP_RE.findall(bodies.get("plan.md", ""))
    s.tasks = [(tid, txt, "done" if mark == "x" else "todo")
               for mark, tid, txt in TASK_RE.findall(bodies.get("tasks.md", ""))]
    s.anchors = resolve_anchors(docs, tree)
    s.sections = bodies
    s.validation = validate_spec(spec_dir, target_repo=str(tree), specs_root=str(specs_root))
    state, landing, detail = read_landing(spec_dir, tree, branch)
    s.landing_state = state
    s.landing_detail = detail
    s.landed = landing
    return s


# --- the page ---------------------------------------------------------------

def dag_svg(graph: dict, landed: dict) -> str:
    """The Work Graph as a layered DAG. Merge edges are solid, verify edges dashed."""
    if not graph:
        return "<p class='empty'>No Work Graph block.</p>"
    depth: dict[str, int] = {}

    def d(n, seen=()):
        if n in seen or n not in graph:
            return 0
        if n in depth:
            return depth[n]
        deps = graph[n]["depends_on"] + graph[n]["depends_on_merged"]
        depth[n] = 1 + max([d(x, seen + (n,)) for x in deps] or [0])
        return depth[n]

    for n in graph:
        d(n)
    layers: dict[int, list[str]] = {}
    for n, lv in sorted(depth.items()):
        layers.setdefault(lv, []).append(n)

    bw, bh, gx, gy = 128, 54, 56, 34
    width = max(len(v) for v in layers.values()) * (bw + gx) + gx
    height = len(layers) * (bh + gy) + gy
    pos = {}
    for lv, nodes in layers.items():
        row_w = len(nodes) * (bw + gx) - gx
        x0 = (width - row_w) / 2
        for i, n in enumerate(nodes):
            pos[n] = (x0 + i * (bw + gx), gy / 2 + (lv - 1) * (bh + gy))

    parts = [f'<svg viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" role="img" '
             f'aria-label="Work graph, {len(graph)} stories">']
    parts.append('<defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" '
                 'markerHeight="7" orient="auto-start-reverse">'
                 '<path d="M0 0 L8 4 L0 8 z" fill="currentColor"/></marker></defs>')
    for n, meta in graph.items():
        if n not in pos:
            continue
        x2, y2 = pos[n]
        for dep, dashed in [(x, False) for x in meta["depends_on_merged"]] + \
                           [(x, True) for x in meta["depends_on"]]:
            if dep not in pos:
                continue
            x1, y1 = pos[dep]
            parts.append(
                f'<path class="edge{" verify" if dashed else ""}" '
                f'd="M{x1 + bw / 2:.0f} {y1 + bh:.0f} C{x1 + bw / 2:.0f} {y1 + bh + gy / 2:.0f} '
                f'{x2 + bw / 2:.0f} {y2 - gy / 2:.0f} {x2 + bw / 2:.0f} {y2:.0f}" '
                f'marker-end="url(#ah)"/>')
    for n, (x, y) in pos.items():
        meta = graph[n]
        cls = "node landed" if n in landed else "node"
        parts.append(f'<g class="{cls}"><rect x="{x:.0f}" y="{y:.0f}" width="{bw}" height="{bh}" rx="3"/>'
                     f'<text x="{x + bw / 2:.0f}" y="{y + 21:.0f}" class="nid">{html.escape(n)}</text>')
        sub = meta.get("persona") or ("landed" if n in landed else f'{len(meta["implements"])} FR')
        parts.append(f'<text x="{x + bw / 2:.0f}" y="{y + 39:.0f}" class="nsub">{html.escape(sub)}</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def md(text: str) -> str:
    """Just enough markdown for spec prose: headings, lists, code, emphasis, tables.

    Prose paragraphs are JOINED, one source line per paragraph is the wall the
    page exists to replace: consecutive non-blank, non-structural lines fold
    into a single <p> with a soft break, and only a blank line or a structural
    line (heading, list, table, fence) starts a new one. Ordered lists become
    <ol>, and h1 renders (the '# Feature Specification:' title line) instead of
    falling through to a literal '# ...' paragraph.
    """
    out = []
    in_code = in_ul = in_ol = in_table = False
    para: list[str] = []          # buffered prose lines of the current paragraph
    in_item = False               # an open <li> may absorb its continuation lines

    def close_para():
        if para:
            out.append("<p>" + "\n".join(para) + "</p>")
            para.clear()

    def close_lists():
        nonlocal in_ul, in_ol, in_item
        if in_ul:
            out.append("</ul>"); in_ul = False
        if in_ol:
            out.append("</ol>"); in_ol = False
        in_item = False

    def slug(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

    for line in text.splitlines():
        if line.startswith("```"):
            close_para(); close_lists()
            if in_table:
                out.append("</table></div>"); in_table = False
            in_code = not in_code
            out.append("<pre><code>" if in_code else "</code></pre>")
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        esc = html.escape(line)
        esc = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc)
        esc = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", esc)
        # tables
        if line.startswith("|") and "|" in line[1:]:
            close_para(); close_lists()
            cells = [c.strip() for c in esc.strip().strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            if not in_table:
                out.append("<div class='scroll'><table>"); in_table = True
            tag = "th" if "<table>" in out[-1] else "td"
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table></div>"); in_table = False
        # headings: # through ####, with emphasis marks stripped from the id text.
        # A '# Feature Specification:' line is the title restated inside the body
        # (the page header already carries it as h1) — skip it rather than print twice.
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            close_para(); close_lists()
            if m.group(1) == "#" and m.group(2).strip().startswith("Feature Specification:"):
                continue
            lv = len(m.group(1))
            out.append(f"<h{lv} id='{slug(re.sub(r'[*`]', '', m.group(2)))}'>"
                       f"{m.group(2)}</h{lv}>")
            continue
        # unordered list
        if re.match(r"^\s*[-*]\s+", line):
            close_para()
            if in_ol:
                out.append("</ol>"); in_ol = False
            if not in_ul:
                out.append("<ul>"); in_ul = True
            out.append("<li>" + re.sub(r"^\s*[-*]\s+", "", esc) + "</li>")
            in_item = True
            continue
        # ordered list — the acceptance scenarios are numbered lines
        m = re.match(r"^\s*(\d+)\.\s+(.*)", line)
        if m:
            close_para()
            if in_ul:
                out.append("</ul>"); in_ul = False
            if not in_ol:
                out.append("<ol>"); in_ol = True
            item = re.sub(r"^\s*\d+\.\s+", "", esc)
            out.append("<li>" + item + "</li>")
            in_item = True
            continue
        # continuation of the current list item — indented prose under a numbered
        # scenario. Absorb into the open <li> with a joining space rather than
        # dropping it to a separate <p>.
        if in_item and re.match(r"^\s+\S", line):
            if out and out[-1].endswith("</li>"):
                out[-1] = out[-1][:-5] + " " + esc.strip() + "</li>"
            continue
        # blank line ends the paragraph
        if not line.strip():
            close_para(); close_lists()
            continue
        close_lists()
        para.append(esc)
    close_para(); close_lists()
    if in_table:
        out.append("</table></div>")
    return "\n".join(out)


CSS = """
:root{
  --ground:#EDF0F2; --surface:#FFFFFF; --sunken:#E3E8EB;
  --ink:#14202A; --muted:#566873; --faint:#7D8F9A;
  --rule:#C7D1D7; --hairline:#D8E0E4;
  --accent:#0E6F79; --accent-w:#DCEDEF;
  --olive:#5A6B2F; --olive-w:#EBEFD9;
  --gold:#8F7D32; --gold-w:#F4F0D9;
  --fb:#396F9E; --fb-w:#E1EBF5;
  --alarm:#9E3319; --alarm-w:#F6E3DD;
  --shadow:0 1px 2px rgba(20,32,42,.05), 0 8px 24px -12px rgba(20,32,42,.14);
  --serif:ui-serif,"Iowan Old Style",Georgia,"Times New Roman",serif;
  --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0D1418; --surface:#131E24; --sunken:#0A1013;
    --ink:#D8E3E8; --muted:#8A9EA9; --faint:#6B7F8A;
    --rule:#27373F; --hairline:#1E2C33;
    --accent:#46B7C1; --accent-w:#102D31;
    --olive:#A9BC62; --olive-w:#20260F;
    --gold:#DBC878; --gold-w:#262112;
    --fb:#74A9D6; --fb-w:#10222F;
    --alarm:#E2795A; --alarm-w:#2E1710;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
  }
}
:root[data-theme="dark"]{
  --ground:#0D1418; --surface:#131E24; --sunken:#0A1013;
  --ink:#D8E3E8; --muted:#8A9EA9; --faint:#6B7F8A;
  --rule:#27373F; --hairline:#1E2C33;
  --accent:#46B7C1; --accent-w:#102D31;
  --olive:#A9BC62; --olive-w:#20260F;
  --gold:#DBC878; --gold-w:#262112;
  --fb:#74A9D6; --fb-w:#10222F;
  --alarm:#E2795A; --alarm-w:#2E1710;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -12px rgba(0,0,0,.6);
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
     font-size:15.5px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{display:grid;grid-template-columns:250px minmax(0,1fr);gap:48px;
      max-width:1180px;margin:0 auto;padding:48px 32px 96px}
@media(max-width:900px){.wrap{grid-template-columns:1fr;gap:28px}.rail{position:static!important}}
.rail{position:sticky;top:32px;align-self:start;font-family:var(--sans);font-size:13px}
.eyebrow{font-family:var(--mono);font-size:.66rem;font-weight:600;letter-spacing:.09em;
         text-transform:uppercase;color:var(--accent);margin:0 0 10px}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(26px,3.6vw,40px);
   line-height:1.08;margin:0 0 12px;text-wrap:balance}
h2{font-family:var(--mono);font-size:12px;font-weight:600;letter-spacing:.12em;
   text-transform:uppercase;margin:44px 0 14px;padding-bottom:8px;
   border-bottom:1px solid var(--hairline);color:var(--muted)}
h3{font-family:var(--serif);font-size:17px;margin:26px 0 8px;font-weight:600}
h4{font-family:var(--mono);font-size:12px;font-weight:600;letter-spacing:.05em;
   text-transform:uppercase;margin:18px 0 6px;color:var(--muted)}
p{margin:0 0 14px;max-width:68ch}
ul{margin:0 0 14px;padding-left:20px;max-width:68ch}
li{margin:0 0 6px}
code{font-family:var(--mono);font-size:.86em;background:var(--sunken);
     padding:.1em .34em;border-radius:2px}
pre{background:var(--surface);border:1px solid var(--rule);border-radius:2px;padding:14px 16px;
    overflow-x:auto;margin:0 0 16px;box-shadow:var(--shadow)}
pre code{background:none;padding:0;font-size:12.5px;line-height:1.6}
a{color:var(--accent)}
.scroll{overflow-x:auto;margin:0 0 16px;scrollbar-width:thin;scrollbar-color:var(--rule) transparent}
table{border-collapse:collapse;width:100%;font-family:var(--sans);font-size:13.5px;
      font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:7px 12px;border-bottom:1px solid var(--hairline);vertical-align:top}
th{font-family:var(--mono);font-size:10px;font-weight:600;letter-spacing:.08em;
   text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--rule)}
.chip{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:.62rem;
      font-weight:600;letter-spacing:.08em;text-transform:uppercase;padding:.24em .55em;
      border:1px solid currentColor;line-height:1.5}
.chip.ok{color:var(--olive);background:var(--olive-w)}
.chip.warn{color:var(--gold);background:var(--gold-w)}
.chip.bad{color:var(--alarm);background:var(--alarm-w)}
.chip.neutral{color:var(--muted);background:var(--sunken)}
.health{display:flex;flex-direction:column;gap:9px;margin:16px 0 22px;padding:14px 16px;
        background:var(--surface);border:1px solid var(--rule);border-radius:2px;box-shadow:var(--shadow)}
.health div{display:flex;justify-content:space-between;align-items:center;gap:10px}
.health span:first-child{color:var(--muted);font-size:.78rem}
.rail nav{display:flex;flex-direction:column;gap:3px;margin-top:8px}
.rail nav a{text-decoration:none;color:var(--muted);padding:3px 0;border-left:2px solid transparent;padding-left:9px}
.rail nav a:hover{color:var(--ink);border-left-color:var(--accent)}
.rail nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
svg{max-width:100%;height:auto;color:var(--muted)}
.node rect{fill:var(--surface);stroke:var(--rule);stroke-width:1;rx:2}
.node.landed rect{fill:var(--olive-w);stroke:var(--olive);stroke-width:2}
.nid{font-family:var(--mono);font-size:13px;font-weight:600;fill:var(--ink);text-anchor:middle}
.nsub{font-family:var(--mono);font-size:10px;fill:var(--faint);text-anchor:middle;letter-spacing:.04em}
.edge{fill:none;stroke:var(--muted);stroke-width:1.5;opacity:.8}
.edge.verify{stroke-dasharray:5 4;opacity:.55}
.legend{font-family:var(--sans);font-size:.82rem;color:var(--muted);margin:6px 0 0;line-height:1.55}
.anchor-row td:first-child{font-family:var(--mono);font-size:12px;white-space:nowrap}
.anchor-row code{font-size:11.5px}
details{margin:0 0 14px;border:1px solid var(--rule);border-radius:2px;background:var(--surface);
        box-shadow:var(--shadow)}
summary{cursor:pointer;padding:10px 14px;font-family:var(--mono);font-size:.66rem;font-weight:600;
        letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}
summary:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
details[open] summary{border-bottom:1px solid var(--hairline)}
.prov{padding:12px 16px;font-family:var(--mono);font-size:12px;line-height:1.7;
      white-space:pre-wrap;color:var(--muted);max-height:420px;overflow-y:auto}
.empty{color:var(--faint);font-style:italic}
.trap{background:var(--surface);border:1px solid var(--rule);border-left:3px solid var(--gold);
      border-radius:2px;box-shadow:var(--shadow);padding:10px 14px;margin:0 0 12px}
.trap b{font-family:var(--mono);font-size:12.5px;color:var(--gold)}
@media print{.rail{display:none}.wrap{grid-template-columns:1fr}}
"""


def validation_html(report: SpecValidation) -> str:
    """Render the library report in run order, preserving severity and reasons."""
    finding_rows = []
    for finding in report.findings:
        cls = {"refusal": "bad", "advisory": "warn"}.get(finding.severity, "neutral")
        finding_rows.append(
            f'<tr><td>{html.escape(finding.severity, quote=False)}</td>'
            f'<td>{html.escape(finding.layer, quote=False)}</td>'
            f'<td>{html.escape(finding.message, quote=False)}</td></tr>'
        )
    skipped_rows = []
    for skipped in report.skipped:
        skipped_rows.append(
            f'<tr><td>{html.escape(skipped["layer"], quote=False)}</td>'
            f'<td>{html.escape(skipped["reason"], quote=False)}</td></tr>'
        )
    checked = ", ".join(report.checked) or "—"
    summary = (f"refusals={len(report.refusals)}, advisories={len(report.advisories)}, "
               f"skipped={len(report.skipped)}")
    return f"""<table><tr><th>verdict</th><th>layer</th><th>message</th></tr>
<tr><td>{html.escape(report.verdict, quote=False)}</td><td colspan="2">{html.escape(summary)}</td></tr>
{"".join(finding_rows)}
</table>
<h3>Skipped layers</h3>
<table><tr><th>layer</th><th>reason</th></tr>
{"".join(skipped_rows)}
</table>
<p><b>Checked:</b> {html.escape(checked)}</p>"""


def build(s: Spec, tree_label: str, validation: SpecValidation | None = None) -> str:
    broken = [a for a in s.anchors if a.status != "ok"]
    story_ids = {sid for sid, _, _ in s.stories}
    covered_fr = set(re.findall(r"FR-\d+", "\n".join(t[1] for t in s.tasks)))
    declared_fr = {f for f, _ in s.frs}
    covered_sc = set(re.findall(r"US\d+-S\d+", "\n".join(t[1] for t in s.tasks)))

    def chip(cls, label):
        return f'<span class="chip {cls}">{html.escape(label)}</span>'

    anchor_chip = chip("ok", f"{len(s.anchors)} anchors ok") if not broken \
        else chip("bad", f"{len(broken)} of {len(s.anchors)} broken")
    fr_gap = declared_fr - covered_fr
    fr_chip = chip("ok", f"{len(declared_fr)}/{len(declared_fr)} FR") if not fr_gap \
        else chip("bad", f"{len(fr_gap)} FR uncovered")
    state_cls = {"landed": "ok", "ready": "warn", "draft": "neutral"}.get(s.state, "neutral")
    landing_count = len(s.landed)
    landing_label = (
        f"{landing_count}/{len(s.stories)} landed"
        if s.landing_state in {"empty", "ready"}
        else s.landing_state
    )
    landing_cls = "neutral" if s.landing_state == "empty" else (
        "ok" if s.landing_state == "ready" and landing_count == len(s.stories)
        else "bad"
    )

    rows = []
    for a in sorted(broken, key=lambda x: (x.doc, x.doc_line)):
        rows.append(f'<tr class="anchor-row"><td>{html.escape(a.doc)}:{a.doc_line}</td>'
                    f'<td><code>{html.escape(a.path)}:{a.line}</code></td>'
                    f'<td>{chip("bad", a.status)}</td></tr>')
    anchor_tbl = ("<div class='scroll'><table><tr><th>cited in</th><th>anchor</th><th>status</th></tr>"
                  + "".join(rows) + "</table></div>") if rows else \
        "<p class='empty'>Every citation resolves against the tree.</p>"

    srows = []
    for sid, title, pri in s.stories:
        g = s.graph.get(sid, {})
        deps = ", ".join(g.get("depends_on_merged", [])) or "—"
        vdeps = ", ".join(g.get("depends_on", [])) or "—"
        if sid in s.landed:
            land = chip("ok", "landed " + s.landed[sid][:7])
        elif s.landing_state in {"unavailable", "error"}:
            land = chip("bad", "landing " + s.landing_state)
        else:
            land = chip("neutral", "not landed")
        srows.append(f"<tr><td><code>{sid}</code></td><td>{html.escape(title)}</td><td>{pri}</td>"
                     f"<td><code>{html.escape(g.get('persona') or 'implementer')}</code></td>"
                     f"<td>{html.escape(vdeps)}</td><td>{html.escape(deps)}</td><td>{land}</td></tr>")
    story_tbl = ("<div class='scroll'><table><tr><th>story</th><th>title</th><th>pri</th><th>persona</th>"
                 "<th>needs verified</th><th>needs merged</th><th>state</th></tr>"
                 + "".join(srows) + "</table></div>") if srows else "<p class='empty'>No stories.</p>"

    traps = "".join(f'<div class="trap"><b>{html.escape(n)}.</b> {html.escape(t)}</div>'
                    for n, t in s.traps) or "<p class='empty'>No traps declared.</p>"

    prov = html.escape("\n".join(s.provenance)) or "No provenance recorded."

    nav = "".join(f'<a href="#{i}">{n}</a>' for i, n in
                  [("graph", "Work graph"), ("stories", "Stories"), ("anchors", "Anchor health"),
                   ("traps", "Traps"), ("spec", "Specification"), ("plan", "Plan"), ("tasks", "Tasks")])

    done = sum(1 for _, _, st in s.tasks if st == "done")
    if s.landing_state == "empty":
        landing_body = "<p class='empty'>No landing facts returned.</p>"
    elif s.landing_state in {"unavailable", "error"}:
        landing_body = f"<div class='trap'><b>{html.escape(s.landing_state)}</b> {html.escape(s.landing_detail)}</div>"
    else:
        landing_body = "<p class='empty'>No landing facts returned.</p>"
    validation_section = validation_html(validation or SpecValidation())
    validation_chip = chip(
        "ok" if (validation or SpecValidation()).verdict == "pass" else "bad",
        (validation or SpecValidation()).verdict,
    )
    return f"""<meta charset="utf-8">
<title>{html.escape(s.slug)}</title>
<style>{CSS}</style>
<div class="wrap">
<aside class="rail">
  <p class="eyebrow">Ergane spec</p>
  <div class="health">
    <div><span>state</span>{chip(state_cls, s.state)}</div>
    <div><span>anchors</span>{anchor_chip}</div>
    <div><span>requirements</span>{fr_chip}</div>
    <div><span>validation</span>{validation_chip}</div>
    <div><span>stories</span>{chip(landing_cls, landing_label)}</div>
    <div><span>tasks</span>{chip("neutral", f"{done}/{len(s.tasks)} done")}</div>
  </div>
  <nav>{nav}</nav>
  <p class="legend" style="margin-top:18px">Resolved against<br><code>{html.escape(tree_label)}</code></p>
</aside>
<main>
  <p class="eyebrow">{html.escape(s.slug)}</p>
  <h1>{html.escape(s.title)}</h1>
  <details><summary>Provenance — why this spec is in the state it is</summary>
    <div class="prov">{prov}</div></details>

  <h2 id="graph">Work graph</h2>
  {dag_svg(s.graph, s.landed)}
  <p class="legend">Solid edge: waits for the dependency to <b>merge</b>. Dashed: waits only for it to
  <b>verify</b>. A green outline is a story already landed on the branch.</p>

  <h2 id="stories">Stories</h2>
  {story_tbl}

  <h2 id="landing">Landing: {html.escape(s.landing_state)}</h2>
  {landing_body}

  <h2 id="anchors">Anchor health</h2>
  {anchor_tbl}

  <h2 id="validation">Validation: {(validation or SpecValidation()).verdict}</h2>
  {validation_section}

  <h2 id="traps">Traps</h2>
  {traps}

  <h2 id="spec">Specification</h2>
  {md(s.sections.get('spec.md', ''))}

  <h2 id="plan">Plan</h2>
  {md(s.sections.get('plan.md', ''))}

  <h2 id="tasks">Tasks</h2>
  {md(s.sections.get('tasks.md', ''))}
</main>
</div>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_dir")
    ap.add_argument("-o", "--output")
    ap.add_argument("--tree", default=".")
    ap.add_argument("--landed-branch", default=None,
                    help="resolve landed stories against this branch (e.g. ergane-buildout)")
    args = ap.parse_args()

    spec_dir = pathlib.Path(args.spec_dir)
    if not (spec_dir / "spec.md").is_file():
        print(f"no spec.md in {spec_dir}", file=sys.stderr)
        return 2
    tree = pathlib.Path(args.tree).resolve()
    s = load(spec_dir, tree, args.landed_branch, specs_root=spec_dir.parent)
    page = build(s, str(tree), validation=s.validation)
    out = pathlib.Path(args.output) if args.output else spec_dir / f"{spec_dir.name}.html"
    out.write_text(page, encoding="utf-8")
    broken = sum(1 for a in s.anchors if a.status != "ok")
    print(f"{out}  ({len(s.stories)} stories, {len(s.anchors)} anchors, {broken} broken)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
