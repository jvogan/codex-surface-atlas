"""Responsive SVG workflow and scientific schematics; no result inference."""
from __future__ import annotations

import html
import textwrap
from functools import lru_cache

from .diagram_routes import route_between, rounded_path


def esc(value):
    return html.escape(str(value), quote=True)


COLORS = {"green": "#17675d", "blue": "#315f89", "gold": "#8a6027", "gray": "#52645b"}

GROUPS = {
    'target-discovery': [('Source records', ['lit', 'protein', 'expression']), ('Target list', ['keep', 'exclude', 'unknown'])],
    'campaign-routes': [('Design inputs', ['evidence', 'structure'])],
    'screen-control': [('Reference system', ['receptor', 'ligand'])],
    'binder-lineage': [('Sequences from one backbone', ['seq1', 'seq2'])],
    'control-comparison': [('Comparison inputs', ['candidate', 'positive', 'negative'])],
    'target-review': [('Source records', ['expression', 'surface', 'structure'])],
}


def node(key, label, x, y, mx, my, tone="green", kind="box"):
    return dict(key=key, label=label, wide=(x, y), small=(mx, my), tone=tone, kind=kind)


def edge(a, b, label="", *, dashed=False, side=None, wide_target_offset=0):
    return dict(a=a, b=b, label=label, dashed=dashed, side=side, wide_target_offset=wide_target_offset)


GRAPHS = {
    "design-methods": dict(title="Two ways to generate a protein binder", caption="Some tools design the sequence and structure together. Others generate a backbone first, then design its sequence. Both routes produce candidates for the same independent evaluation.", height=740, small_height=1150,
        nodes=[node("input", "Target and binding site", 450, 65, 180, 65, tone="blue"), node("joint", "Design sequence and structure together", 175, 265, 92, 265, tone="blue"), node("backbone", "Generate a backbone", 730, 225, 268, 245, tone="blue"), node("sequence", "Design its sequence", 730, 420, 268, 455, tone="blue"), node("candidate", "Save sequence and design pose", 320, 475, 180, 670, tone="blue", kind="file"), node("common", "Predict and score each target–binder complex", 450, 680, 180, 1030), node("controls", "Reference controls", 755, 640, 92, 850, tone="gold")],
        edges=[edge("input", "joint"), edge("input", "backbone"), edge("backbone", "sequence"), edge("joint", "candidate"), edge("sequence", "candidate"), edge("candidate", "common"), edge("controls", "common")]),
    "target-discovery": dict(title="Find proteins on the cell surface", caption="Match records about the same protein. Check its location, then retain it as a cell-surface target, exclude it, or record an unresolved result.", height=540, small_height=850,
        nodes=[node("lit", "Literature", 135, 105, 92, 65, kind="file"), node("protein", "Protein records", 135, 260, 268, 65, kind="database"), node("expression", "RNA expression data", 135, 415, 180, 205, kind="database"), node("identity", "Match gene and protein IDs", 425, 180, 180, 355), node("surface", "Is this protein on the cell surface?", 425, 365, 180, 505, kind="decision"), node("keep", "Retained", 755, 110, 92, 690), node("exclude", "Excluded", 755, 260, 268, 690, tone="gray"), node("unknown", "Unresolved", 755, 415, 180, 815, tone="gold")],
        edges=[edge("lit", "identity"), edge("protein", "identity"), edge("expression", "identity"), edge("identity", "surface"), edge("surface", "keep", "Yes"), edge("surface", "exclude", "No"), edge("surface", "unknown", "Unclear")]),
    "campaign-routes": dict(title="Screen molecules or design protein binders", caption="Choose a protein target and the site where a molecule should attach. Screen existing molecules, or design protein binders for that site.", height=635, small_height=990,
        nodes=[node("evidence", "Target evidence", 160, 70, 92, 65), node("structure", "Target structure", 470, 70, 268, 65, tone="blue"), node("brief", "Choose target, binding site, and action", 320, 230, 180, 245, tone="blue"), node("library", "Molecules to test", 750, 210, 92, 415, tone="gold", kind="database"), node("screen", "Molecule screening", 640, 385, 92, 590, tone="gold"), node("binder", "Protein-binder design", 215, 385, 268, 590, tone="blue"), node("review", "Compare candidates and controls", 425, 570, 180, 775), node("report", "Report and result files", 755, 570, 180, 940, kind="file")],
        edges=[edge("evidence", "brief"), edge("structure", "brief"), edge("brief", "screen"), edge("brief", "binder"), edge("library", "screen"), edge("screen", "review"), edge("binder", "review"), edge("review", "report")]),
    "screen-control": dict(title="Check the docking method with a known ligand", caption="Dock the known ligand and compare its predicted position with the deposited structure. If it misses the criteria, review the preparation or docking method.", height=620, small_height=1010,
        nodes=[node("receptor", "Prepared target", 145, 70, 92, 60, tone="blue"), node("ligand", "Known ligand", 470, 70, 268, 60, tone="gold"), node("dock", "Dock the known ligand", 310, 225, 180, 225, tone="gold"), node("test", "Does the pose meet the criteria?", 310, 395, 180, 400, tone="gold", kind="decision"), node("fix", "Review preparation or method", 735, 225, 268, 595, tone="gray"), node("library", "Dock library molecules", 735, 395, 92, 595, tone="gold"), node("repeat", "Repeat selected runs and inspect poses", 735, 565, 92, 775, tone="gold"), node("save", "Save scores, poses, and failures", 310, 565, 180, 955, kind="file")],
        edges=[edge("receptor", "dock"), edge("ligand", "dock"), edge("dock", "test"), edge("test", "library", "pass"), edge("test", "fix", "fail", dashed=True), edge("fix", "dock", "Re-test", dashed=True, side="right"), edge("library", "repeat"), edge("repeat", "save")]),
    "repeat-runs": dict(title="Compare scores and poses across repeat runs", caption="Use the same prepared inputs and method settings. Review score variation and pose geometry separately.", height=555, small_height=860,
        nodes=[node("inputs", "Same inputs and settings", 140, 270, 180, 65, tone="blue"), node("a", "Repeat A", 430, 90, 92, 240, tone="gold"), node("b", "Repeat B", 430, 270, 268, 240, tone="gold"), node("c", "Repeat C", 430, 450, 180, 395, tone="gold"), node("scores", "Compare scores", 755, 175, 92, 590), node("poses", "Compare poses", 755, 385, 268, 590), node("review", "Review both comparisons", 755, 505, 180, 795)],
        edges=[edge("inputs", "a"), edge("inputs", "b"), edge("inputs", "c"), edge("a", "scores"), edge("b", "scores"), edge("c", "scores"), edge("a", "poses"), edge("b", "poses"), edge("c", "poses"), edge("scores", "review"), edge("poses", "review")]),
    "binder-lineage": dict(title="Track sequences generated from one backbone", caption="A backbone defines the binder’s shape. Design sequences for that backbone, predict each target–binder complex, then compare results with controls.", height=710, small_height=1080,
        nodes=[node("brief", "Target and binding site", 435, 65, 180, 65, tone="blue"), node("backbone", "Generate backbone", 250, 230, 180, 230, tone="blue"), node("seq1", "Design sequence A", 135, 415, 92, 405, tone="blue"), node("seq2", "Design sequence B", 435, 415, 268, 405, tone="blue"), node("controls", "Reference controls", 755, 415, 268, 570, tone="gold"), node("predict", "Predict target–binder complexes", 320, 575, 180, 760, tone="blue"), node("evaluate", "Compare site contacts and scores", 755, 575, 180, 940), node("select", "Select candidates for testing", 755, 730, 180, 1100)],
        edges=[edge("brief", "backbone"), edge("backbone", "seq1"), edge("backbone", "seq2"), edge("seq1", "predict"), edge("seq2", "predict"), edge("predict", "evaluate"), edge("controls", "predict", wide_target_offset=-30), edge("evaluate", "select")]),
    "control-comparison": dict(title="Apply the same checks to candidates and controls", caption="Run candidates and controls through the same preparation, prediction, and scoring steps.", height=465, small_height=620,
        nodes=[node("candidate", "Generated candidate", 150, 105, 92, 65, tone="blue"), node("positive", "Positive control", 150, 300, 268, 65, tone="gold"), node("negative", "Negative control", 450, 300, 180, 215, tone="gray"), node("checks", "Use the same predictor and checks", 460, 105, 180, 390), node("compare", "Compare scores and contacts", 765, 105, 180, 565)],
        edges=[edge("candidate", "checks"), edge("positive", "checks"), edge("negative", "checks"), edge("checks", "compare")]),
    "structure-preparation": dict(title="Prepare a structure without losing its residue numbering", caption="Select target chains and map residue numbers when preparing a design input. Keep a link to the original coordinates.", height=510, small_height=800,
        nodes=[node("original", "Original coordinates", 145, 100, 180, 65, tone="blue", kind="file"), node("inspect", "Inspect chains and partners", 445, 100, 180, 230, tone="blue"), node("target", "Prepared target", 745, 100, 92, 415, tone="blue"), node("map", "Original-to-input residue map", 445, 350, 268, 415, kind="file"), node("site", "Mapped binding site", 745, 350, 180, 625, tone="gold"), node("input", "Design or docking input", 745, 470, 180, 770)],
        edges=[edge("original", "inspect"), edge("inspect", "target"), edge("inspect", "map"), edge("target", "site"), edge("map", "site"), edge("site", "input")]),
    "intervention-links": dict(title="Check why a treatment is linked to a target", caption="Read the supporting record to see how the drug, biologic, or trial was linked to the target.", height=560, small_height=840,
        nodes=[node("source", "Drug, biologic, or trial record", 145, 255, 180, 65, kind="file"), node("check", "How was the target linked?", 445, 255, 180, 240, kind="decision"), node("direct", "Source names the target", 755, 90, 92, 445), node("curated", "Curator assigns the target", 755, 265, 268, 445, tone="blue"), node("unknown", "Target unassigned", 755, 445, 180, 610, tone="gray")],
        edges=[edge("source", "check"), edge("check", "direct"), edge("check", "curated"), edge("check", "unknown")]),
    "molecule-evidence": dict(title="Compare published interactions with docking results", caption="The molecule page links published assay measurements and new docking predictions to the same molecule.", height=530, small_height=770,
        nodes=[node("identity", "Identify the molecule", 440, 65, 180, 65, tone="gold", kind="database"), node("known", "Find published interactions", 165, 260, 92, 245), node("screen", "Run docking", 735, 260, 268, 245, tone="gold"), node("measure", "Record assays and targets", 165, 445, 92, 445), node("pose", "Save scores and poses", 735, 445, 268, 445, tone="gold"), node("report", "Molecule page", 440, 445, 180, 680, kind="file")],
        edges=[edge("identity", "known"), edge("identity", "screen"), edge("known", "measure"), edge("screen", "pose"), edge("measure", "report"), edge("pose", "report")]),
    "provenance": dict(title="Follow a reported result to its source files", caption="Stable identifiers link the report entry, normalized result, run record, and files.", height=480, small_height=790,
        nodes=[node("page", "Report entry", 150, 90, 180, 65, kind="file"), node("record", "Imported result", 445, 90, 180, 230, kind="database"), node("run", "Run record", 750, 90, 180, 410, tone="blue", kind="file"), node("pose", "Pose or complex file", 530, 340, 92, 615, tone="blue", kind="file"), node("metrics", "Metric file", 795, 340, 268, 615, tone="gold", kind="file"), node("source", "Source IDs, versions, and file hashes", 190, 340, 180, 765, tone="gray")],
        edges=[edge("page", "record", "record ID"), edge("record", "run", "run ID"), edge("run", "pose"), edge("run", "metrics"), edge("record", "source")]),
    "study-search": dict(title="Record search coverage before reviewing targets", caption="Save query terms and dates. Deduplicate retrieved records and report searches that remain incomplete.", height=570, small_height=960,
        nodes=[node("scope", "Study scope", 145, 85, 180, 60), node("query", "Search terms and sources", 445, 85, 180, 225), node("retrieve", "Retrieved records", 745, 85, 92, 415, kind="database"), node("partial", "Incomplete sources", 445, 330, 268, 415, tone="gold"), node("dedup", "Remove duplicate records", 745, 330, 92, 610), node("unique", "Unique source records", 745, 515, 92, 795, kind="database"), node("coverage", "Coverage summary", 340, 515, 180, 915, kind="file")],
        edges=[edge("scope", "query"), edge("query", "retrieve"), edge("query", "partial", "gaps", dashed=True), edge("retrieve", "dedup"), edge("dedup", "unique"), edge("unique", "coverage"), edge("partial", "coverage")]),
    "target-review": dict(title="Check expression, location, and structure", caption="Check which cells express the target, whether the protein is on the surface, and which parts of its structure are available.", height=460, small_height=650,
        nodes=[node("expression", "Expression measurements", 150, 85, 92, 65, kind="database"), node("surface", "Protein-location records", 450, 85, 268, 65, kind="file"), node("structure", "Target structures", 750, 85, 180, 230, tone="blue", kind="file"), node("review", "Review the target and missing data", 450, 300, 180, 435), node("action", "Select a site and experiment", 750, 390, 180, 615)],
        edges=[edge("expression", "review"), edge("surface", "review"), edge("structure", "review"), edge("review", "action")]),
}


def text_block(x, y, lines, *, size, color="#19382c", cls="", anchor="middle"):
    start = y - (len(lines) - 1) * size * .62
    return f'<text class="{cls}" x="{x}" y="{start}" text-anchor="{anchor}" dominant-baseline="middle" fill="{color}" font-size="{size}">' + ''.join(f'<tspan x="{x}" dy="{0 if i == 0 else size * 1.24}">{esc(line)}</tspan>' for i, line in enumerate(lines)) + '</text>'


@lru_cache(maxsize=128)
def graph_svg(key, variant, uid):
    spec = GRAPHS[key]
    small = variant == "small"
    width, height, size = (360, spec["small_height"], 18) if small else (900, spec["height"], 20)
    boxes = {}
    for n in spec["nodes"]:
        x, y = n[variant]
        w = 148 if small else 210
        lines = textwrap.wrap(n["label"], width=13 if small else 18, break_long_words=False)
        h = max(78, len(lines) * size * 1.24 + 32)
        if n["kind"] == "decision":
            h += 16
        boxes[n["key"]] = (x, y, w, h, lines, n)
    height = max(height, max(y + h / 2 + 25 for x, y, w, h, lines, n in boxes.values()))
    prefix = f"{uid}-{variant}"
    out = f'<svg class="diagram-svg diagram-{variant}" viewBox="0 0 {width} {height+48}" role="img" aria-labelledby="{prefix}-title {prefix}-desc" xmlns="http://www.w3.org/2000/svg"><title id="{prefix}-title">{esc(spec["title"])}</title><desc id="{prefix}-desc">{esc(spec["caption"])} '
    out += esc("; ".join(f'{boxes[e["a"]][5]["label"]} → {boxes[e["b"]][5]["label"]}' + (f' ({e["label"]})' if e["label"] else '') for e in spec["edges"]))
    out += f'</desc><defs><marker id="{prefix}-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M1 1 8 5 1 9" fill="none" stroke="#52645b" stroke-width="1.3"/></marker></defs>'
    # Restrained stippling distinguishes groups of inputs from individual operations.
    out += '<g transform="translate(0 24)">'
    out += f'<defs><pattern id="{prefix}-dots" width="6" height="6" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".65" fill="#c5d4ca"/></pattern></defs>'
    group_labels = ''
    for label, keys in GROUPS.get(key, []):
        members = [boxes[item] for item in keys]
        left = min(x-w/2 for x,y,w,h,_,_ in members) - 12
        top = min(y-h/2 for x,y,w,h,_,_ in members) - 14
        right = max(x+w/2 for x,y,w,h,_,_ in members) + 12
        bottom = max(y+h/2 for x,y,w,h,_,_ in members) + 14
        # Use groups only when they contain exactly the intended components.
        if any(left < x < right and top < y < bottom for x,y,_,_,_,n in boxes.values() if n['key'] not in keys):
            continue
        out += f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" rx="26" fill="url(#{prefix}-dots)" stroke="#bacbbe" stroke-width=".8"/>'
        label_width = len(label) * 8.7 + 14
        group_labels += f'<rect x="{(left+right-label_width)/2}" y="{top-13}" width="{label_width}" height="26" fill="#fff"/>'
        group_labels += text_block((left+right)/2, top, [label], size=18, color='#405d4b')
    labels = []
    for e in spec["edges"]:
        ax, ay, aw, ah, _, an = boxes[e["a"]]
        bx, by, bw, bh, _, bn = boxes[e["b"]]
        if e["side"]:
            start, end = (ax + aw / 2, ay), (bx + bw / 2, by)
            first, last = (start[0]+18, start[1]), (end[0]+18, end[1])
        elif not small and abs(bx - ax) > aw:
            direction = 1 if bx > ax else -1
            start, end = (ax + direction * aw / 2, ay), (bx - direction * bw / 2, by + e.get('wide_target_offset', 0))
            first, last = (start[0]+direction*18, start[1]), (end[0]-direction*18, end[1])
        else:
            direction = 1 if by > ay else -1
            start, end = (ax, ay + direction * ah / 2), (bx, by - direction * bh / 2)
            first, last = (start[0], start[1]+direction*18), (end[0], end[1]-direction*18)
        obstacles = [(x-w/2-8, y-h/2-8, x+w/2+8, y+h/2+8) for x,y,w,h,_,_ in boxes.values()]
        points = [start, *route_between(first, last, obstacles, width, height), end]
        d = rounded_path(points)
        longest = max(zip(points, points[1:]), key=lambda pair: abs(pair[0][0]-pair[1][0]) + abs(pair[0][1]-pair[1][1]))
        (sx, sy), (ex, ey) = longest
        lx, ly = (sx + ex) / 2, (sy + ey) / 2
        if key == 'target-discovery' and e['label']:
            lx, ly = (end[0], end[1]-32) if small else (end[0]-52, end[1])
        elif small and e['side']:
            lx, ly = width - 60, (ay + by) / 2
        color = COLORS['gray' if e['dashed'] else an['tone']]
        out += f'<path data-from="{esc(e["a"])}" data-to="{esc(e["b"])}" d="{d}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round" marker-end="url(#{prefix}-arrow)"' + (' stroke-dasharray="5 4"' if e['dashed'] else '') + '/>'
        if e['label']:
            labels.append((lx, ly, e['label'], color))
    out += group_labels
    for x, y, w, h, lines, n in boxes.values():
        color = COLORS[n['tone']]
        if n['kind'] == 'decision':
            shape = f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="22" fill="#f1f6ef"/>'
        elif n['kind'] == 'database':
            shape = f'<path d="M{x-w/2} {y-h/2+10} C{x-w/2} {y-h/2-8} {x+w/2} {y-h/2-8} {x+w/2} {y-h/2+10} V{y+h/2-10} C{x+w/2} {y+h/2+8} {x-w/2} {y+h/2+8} {x-w/2} {y+h/2-10} Z"/><path d="M{x-w/2} {y-h/2+10} C{x-w/2} {y-h/2+28} {x+w/2} {y-h/2+28} {x+w/2} {y-h/2+10}" fill="none"/>'
        elif n['kind'] == 'file':
            shape = f'<path d="M{x-w/2} {y-h/2} H{x+w/2-16} L{x+w/2} {y-h/2+16} V{y+h/2} H{x-w/2} Z"/><path d="M{x+w/2-16} {y-h/2} V{y-h/2+16} H{x+w/2}" fill="none"/>'
        else:
            shape = f'<rect x="{x-w/2}" y="{y-h/2}" width="{w}" height="{h}" rx="22"/>'
        weight = 2.2 if n['kind'] == 'decision' else 1.7
        out += f'<g class="diagram-component" data-node="{esc(n["key"])}" fill="#fff" stroke="{color}" stroke-width="{weight}">{shape}</g>'
        out += text_block(x, y + (6 if n['kind'] == 'database' else 0), lines, size=size, color=color)
    for x, y, label, color in labels:
        out += f'<rect x="{x-len(label)*4.8-5}" y="{y-12}" width="{len(label)*9.6+10}" height="24" fill="#fff"/>'
        out += text_block(x, y, [label], size=18, color=color)
    return out + '</g></svg>'


def graph(key, prefix):
    spec = GRAPHS[key]
    uid = prefix + '-' + key
    return (f'<section class="explanatory-diagram" aria-labelledby="{uid}-heading"><h3 id="{uid}-heading">{esc(spec["title"])}</h3>'
            '<div class="diagram-canvas">' + graph_svg(key, 'wide', uid) + graph_svg(key, 'small', uid) + '</div>'
            f'<p class="diagram-caption">{esc(spec["caption"])}</p></section>')


def science_svg(kind, variant, uid):
    small = variant == 'small'
    width, height = (360, 710) if small else (900, 370)
    prefix = f'{uid}-{variant}'
    title = 'Compare a reference ligand pose' if kind == 'pose' else 'Expression and cell-surface access'
    description = ('Align the receptor coordinates, then compare the reference ligand in gold with the docked pose in blue.' if kind == 'pose' else 'A protein spans the cell membrane, with a binding site outside the cell. RNA is shown inside the cell; measuring RNA does not locate the protein binding site.')
    out = f'<svg class="diagram-svg diagram-{variant}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{prefix}-title {prefix}-desc" xmlns="http://www.w3.org/2000/svg"><title id="{prefix}-title">{title}. Conceptual schematic.</title><desc id="{prefix}-desc">{description}</desc>'
    if kind == 'pose':
        panels = [(20, 55, 'Deposited complex'), (20 if small else 485, 400 if small else 55, 'Compare docked pose')]
        for index, (x, y, label) in enumerate(panels):
            out += text_block(x + 155, y - 25, [label], size=21, color='#19382c')
            out += f'<g transform="translate({x+15} {y+10})"><path d="M20 140 C-10 90 20 10 90 20 C125 25 135 70 165 65 C205 40 255 65 270 115 C295 165 245 215 190 205 C130 230 45 210 20 140Z" fill="#f0f6f2" stroke="#17675d" stroke-width="2"/><path d="M120 70 145 105 170 93 198 122" fill="none" stroke="#a26c24" stroke-width="5" stroke-linecap="round"/>'
            if index:
                out += '<path d="M121 79 145 115 169 103 195 131" fill="none" stroke="#315f89" stroke-width="3" stroke-dasharray="5 4"/><ellipse cx="159" cy="101" rx="57" ry="47" fill="none" stroke="#52645b" stroke-width="1.2" stroke-dasharray="4 4"/>'
            out += '</g>'
            out += text_block(x + 155, y + 258, ['Target receptor'] if index == 0 else ['Align receptor; compare ligand'], size=18)
        out += '<path d="M180 335v28m-6-7 6 7 6-7" stroke="#52645b" fill="none"/>' if small else '<path d="M375 180h78m-8-7 8 7-8 7" stroke="#52645b" fill="none"/>'
    else:
        height = 480 if small else 440
        # The same scientific drawing is centered at native label size in each layout.
        out = out.replace(f'0 0 {width} {710 if small else 370}', f'0 0 {width} {height}')
        ox = 0 if small else 265
        out += f'<g transform="translate({ox} 0)">'
        for x in range(16, 350, 20):
            out += f'<circle cx="{x}" cy="235" r="5" fill="#d4dfd7"/><path d="M{x-2} 241v13m4-13v13" stroke="#a6bbae"/><circle cx="{x}" cy="275" r="5" fill="#d4dfd7"/><path d="M{x-2} 269v-13m4 13v-13" stroke="#a6bbae"/>'
        out += '<path d="M154 292 V223 C119 205 118 175 139 148 C108 105 126 65 163 68 C200 40 230 88 205 122 C236 155 221 193 194 217 V292Z" fill="#e8f2ed" stroke="#17675d" stroke-width="2"/><ellipse cx="197" cy="103" rx="31" ry="24" fill="none" stroke="#8a6027" stroke-width="2" stroke-dasharray="4 3"/><path d="M211 83 268 44 H335" stroke="#8a6027" fill="none"/><path d="M160 165H35" stroke="#17675d" fill="none"/><path d="M77 365q12-20 24 0t24 0t24 0t24 0" stroke="#315f89" stroke-width="2" fill="none"/>'
        out += text_block(282, 24, ['Binding site'], size=18, color='#8a6027')
        out += text_block(65, 55, ['Outside', 'the cell'], size=18, color='#52645b')
        out += text_block(65, 144, ['Surface', 'protein'], size=18, color='#17675d')
        out += text_block(280, 210, ['Cell membrane'], size=18)
        out += text_block(190, 329, ['Inside the cell'], size=18, color='#52645b')
        out += text_block(178, 405, ['RNA in sampled cells'], size=18, color='#315f89')
        out += '</g>'
    return out + '</svg>'


def science(kind, prefix):
    uid = prefix + '-' + kind
    title, caption = ('Compare the reference and docked ligand poses', 'Conceptual schematic. Align the receptor coordinates, then compare the reference ligand (gold) with the docked pose (blue).') if kind == 'pose' else ('Expression and surface location answer different questions', 'Conceptual schematic. RNA measurements show expression in the sampled cells. Protein-location records and structures help identify sites that molecules can reach.')
    return f'<section class="explanatory-diagram" aria-labelledby="{uid}-heading"><h3 id="{uid}-heading">{title}</h3><div class="diagram-canvas">' + science_svg(kind, 'wide', uid) + science_svg(kind, 'small', uid) + f'</div><p class="diagram-caption">{caption}</p></section>'


PAGE_DIAGRAMS = {
    'overview': ['target-discovery', 'campaign-routes'],
    'explore': ['target-review', 'science:surface'],
    'targets': ['target-discovery', 'target-review'],
    'dossier': ['target-review', 'science:surface'],
    'treatments': ['intervention-links', 'provenance'],
    'molecular-library': ['molecule-evidence', 'screen-control'],
    'screening': ['screen-control', 'science:pose', 'repeat-runs'],
    'structures': ['structure-preparation', 'science:surface'],
    'binders': ['design-methods', 'binder-lineage', 'control-comparison'],
    'design-sources': ['campaign-routes', 'provenance'],
    'study': ['study-search', 'target-discovery'],
}


def render(key):
    return ''.join(science(item.split(':')[1], key) if item.startswith('science:') else graph(item, key) for item in PAGE_DIAGRAMS.get(key, []))
