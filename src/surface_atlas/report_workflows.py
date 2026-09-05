"""Accessible, campaign-neutral workflow diagrams rendered as local HTML/SVG.

Diagrams explain method order and decision boundaries. They deliberately do not
derive execution status from arrows, counts, or an absent result collection.
"""
from __future__ import annotations

import html
import re

from .report_diagrams import render as render_diagrams


def esc(value):
    return html.escape(str(value), quote=True)


ICONS = {
    "scope": '<path d="M5 4h14v17H5zM8 9h8M8 13h8M8 17h5"/>',
    "sources": '<path d="M3 7h7l2 2h9v12H3zM6 3h14v3"/>',
    "target": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="M12 1v4M12 19v4M1 12h4M19 12h4"/>',
    "filter": '<path d="M3 4h18l-7 8v8l-4-2v-6z"/>',
    "structure": '<path d="M6 3c16 6-4 12 12 18M18 3C2 9 22 15 6 21M7 5h10M8 19h8M9 10h6M9 14h6"/>',
    "molecule": '<path d="m12 3 8 5v9l-8 4-8-4V8zM12 3v6l8 8M12 9 4 17"/>',
    "check": '<path d="M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6zM7 12l3 3 7-7"/>',
    "compare": '<path d="M4 4h6v16H4zM14 4h6v16h-6zM6 9h2M16 9h2M6 13h2M16 13h2"/>',
    "report": '<path d="M4 3h16v18H4zM8 7h8M8 17v-4M12 17V9M16 17v-6"/>',
}


def icon(name):
    return f'<svg class="wf-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS.get(name, ICONS["scope"])}</svg>'


def arrow():
    return '<svg class="wf-arrow" viewBox="0 0 32 20" aria-hidden="true"><path d="M1 10h27m-6-5 6 5-6 5" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>'


def step(number, title, detail, output, symbol="scope", href=None, link_label=None):
    return {"number": number, "title": title, "detail": detail, "output": output, "icon": symbol, "href": href, "link_label": link_label}


def node(item, *, linked=True):
    link = ''
    if linked and item.get('href'):
        link = f'<a class="wf-node-link" href="{esc(item["href"])}">{esc(item.get("link_label") or "Open this evidence")} <span aria-hidden="true">↗</span></a>'
    return (f'<div class="wf-node"><div class="wf-node-top"><span class="wf-number">{esc(item["number"])}</span>{icon(item["icon"])}</div>'
            f'<h3>{esc(item["title"])}</h3><p>{esc(item["detail"])}</p>'
            f'<div class="wf-output"><span>Output</span>{esc(item["output"])}</div>{link}</div>')


def chain(items, *, label, tone="evidence", gate_after=None):
    return f'<ol class="wf-chain wf-{tone} wf-count-{len(items)}" aria-label="{esc(label)}">' + ''.join(
        '<li>' + node(item) + (arrow() if index < len(items) - 1 else '') + ('<span class="wf-edge-label">PASS</span>' if index == gate_after else '') + '</li>' for index, item in enumerate(items)
    ) + '</ol>'


def caption(identifier, title, subtitle):
    return f'<figcaption><p class="eyebrow">Workflow</p><h2 id="{identifier}-title">{esc(title)}</h2><p class="wf-intro">{esc(subtitle)}</p></figcaption>'


def footer():
    return '<p class="wf-caption">Workflow guide. Completed work and results are recorded in the report tables.</p>'


def overview_steps():
    identifier = 'workflow-overview'
    out = f'<figure id="{identifier}" class="workflow wf-overview" aria-labelledby="{identifier}-title">'
    out += caption(identifier, 'Research and design workflows', 'Collect target evidence, choose a target and site, then screen molecules or design protein binders. Review the results with the source records and controls.')
    out += '<nav class="wf-roadmap" aria-label="Workflow phases"><a href="#workflow-evidence"><span>01–03</span>Find surface targets</a><a href="#workflow-context"><span>04–05</span>Select the target and site</a><a href="#workflow-compute"><span>06</span>Screen or design</a><a href="#workflow-review"><span>07</span>Review the results</a></nav>'
    out += '<div id="workflow-evidence" class="wf-phase-label"><span>01—03</span><strong>Collect records and check protein location</strong></div>'
    out += chain([
        step('01', 'Disease and cell state', 'Record the disease, cell population, treatment context, and search dates.', 'Study plan', 'scope', 'study.html', 'Study & scope'),
        step('02', 'Collect source records', 'Search literature and databases. Save identifiers and retrieval dates.', 'Publications and annotations', 'sources', 'study.html', 'Sources & coverage'),
        step('03', 'Build the target list', 'Match gene and protein identifiers and check whether the protein is on the cell surface.', 'Retained, excluded, and unresolved targets', 'filter', 'targets.html', 'Target census'),
    ], label='Evidence workflow')
    out += '<div class="wf-down"><span>Review each target’s interventions, structures, and candidate molecules</span></div>'
    out += '<div id="workflow-context" class="wf-branch-frame wf-planning"><div class="wf-phase-label"><span>04</span><strong>Review interventions, structures, and molecules</strong><small>Parallel views</small></div><ul class="wf-parallel" aria-label="Parallel decision inputs">'
    for item in [
        step('04A', 'Map interventions', 'Link drugs, biologics, and trials to their target evidence.', 'Interventions with source links', 'compare', 'treatments.html', 'Interventions'),
        step('04B', 'Inspect structures', 'Check target chains, binding partners, and accessible sites.', 'Structures and residue maps', 'structure', 'structures.html', 'Structure library'),
        step('04C', 'Prepare molecules', 'Resolve chemical identities and record preparation status.', 'Molecule library', 'molecule', 'molecular-library.html', 'Molecule library'),
    ]:
        out += '<li>' + node(item) + '</li>'
    out += '</ul></div>'
    out += '<div class="wf-down"><span>Use these records to choose a target and site</span></div>'
    out += '<div class="wf-lock"><span class="wf-number">05</span>' + icon('target') + '<div><h3>Choose the target, site, and intended effect</h3><p>Record the intended action, target construct, binding site, molecule format, controls, and compute budget.</p></div><a href="design-sources.html">Design decisions →</a></div>'
    out += '<div id="workflow-compute" class="wf-fork-label"><span>Choose molecule screening or protein-binder design</span></div><div class="wf-lanes wf-compute">'
    lanes = [
        ('06A', 'Molecule screening', 'Prepared molecules + a defined binding site', [('Test the reference control', 'Check the known ligand pose against the chosen criteria.'), ('Dock the molecules', 'Save poses, scores, parameters, and failed runs.'), ('Repeat and inspect', 'Compare repeated runs and inspect the binding poses.')], 'screening.html', 'Screening results'),
        ('06B', 'Protein-binder design', 'Target structure + site and design constraints', [('Generate backbones and sequences', 'Track each sequence to its parent backbone.'), ('Predict and score complexes', 'Evaluate candidates and reference controls with the same method.'), ('Select candidates for testing', 'Record selection criteria and the measurements still needed.')], 'binders.html', 'Binder results'),
    ]
    for number, title, input_text, items, href, link_label in lanes:
        out += f'<section class="wf-lane"><span class="wf-number">{number}</span><h3>{title}</h3><p class="wf-lane-input">INPUT · {input_text}</p><ol class="wf-mini">'
        for name, detail in items:
            out += f'<li><strong>{name}</strong><span>{detail}</span></li>'
        out += f'</ol><a class="wf-node-link" href="{href}">{link_label} ↗</a></section>'
    out += '</div><div class="wf-review-loop"><span aria-hidden="true">↶</span><p><strong>Failed control:</strong> save the result and review the preparation or method before expanding the run.</p></div>'
    out += '<div class="wf-down"><span>Review results from either workflow</span></div><div id="workflow-review" class="wf-outcome"><span class="wf-number">07</span><div><h3>Review candidates and supporting records</h3><p>Compare candidate results with controls. Link selected candidates to source records, structures, and run files.</p></div>' + icon('report') + '</div>'
    out += '<div class="wf-future"><strong>Next: experimental testing</strong><span>Measure binding, selectivity, and activity for selected candidates.</span></div>'
    return out + footer() + '</figure>'


def overview():
    original = overview_steps()
    start = original.index('</figcaption>') + len('</figcaption>')
    navigation = '<nav class="diagram-nav" aria-label="Overview sections"><a href="#overview-target-discovery-heading">Find targets</a><a href="#overview-campaign-routes-heading">Screen or design</a><a href="#readout">Campaign results ↓</a></nav>'
    return (original[:start] + navigation + render_diagrams('overview')
            + '<details class="workflow-notes"><summary>Read the workflow steps and open related pages</summary>'
            + original[start:-len('</figure>')] + '</details></figure>')


PAGE_MAPS = {
    'explore': ('Compare targets', 'Select a target on the chart to open its scores, source records, and missing measurements.', [
        step('01', 'Start with the census', 'Every retained target stays available, including targets outside structure waves.', 'Retained target list', 'sources', 'targets.html', 'Open target census'),
        step('02', 'Compare evidence scores', 'Inspect the measurements behind each score and how missing data were handled.', 'Scores and missing measurements', 'compare'),
        step('03', 'Open the target page', 'Check the source cohort, topology, score components, and missing measurements.', 'Target measurements and sources', 'target'),
    ], 'Filtering is not exclusion. Low warning signals are not evidence of safety.'),
    'targets': ('Build and prioritize the target list', 'Resolve each identity, assess cell-surface localization, then assign the depth of structure review.', [
        step('01', 'Resolve identity', 'Reconcile names and identifiers while preserving ambiguous records.', 'Names matched to stable identifiers', 'sources'),
        step('02', 'Check cell-surface location', 'Inspect localization, topology, cohort context, and conflicting evidence.', 'Retain, exclude, or leave unresolved', 'filter'),
        step('03', 'Assign review depth', 'Use the completed target list to assign structure-review tiers.', 'Structure-review tiers', 'target', 'explore.html', 'Compare retained targets'),
    ], 'Retained does not mean tumor-specific, druggable, safe, or therapeutically validated.'),
    'dossier': ('Review a target', 'Check the target identity and supporting measurements before choosing an intervention or design.', [
        step('01', 'Establish identity', 'Check the exact target, source context, and surface annotations.', 'Target identity and source records', 'target'),
        step('02', 'Review the measurements', 'Compare cell populations, score components, warning signals, and missing data.', 'Reported measurements and gaps', 'compare'),
        step('03', 'Review possible interventions', 'Follow related interventions, structures, and computed observations.', 'Related interventions and structures', 'structure', 'design-sources.html', 'Methods & decisions'),
    ], 'A cohort observation or modality-fit score does not establish patient-specific activity.'),
    'treatments': ('Review intervention evidence', 'Check the source of each target assignment and the disease context of the intervention.', [
        step('01', 'Identify the intervention', 'Normalize drug, biologic, or trial records and preserve source identifiers.', 'A source-linked intervention', 'sources'),
        step('02', 'Check the target link', 'Distinguish explicit target evidence, curated assignments, and unassigned records.', 'Target assignment and its source', 'compare'),
        step('03', 'Interpret the action', 'Read format, mechanism, disease scope, status, and supporting evidence together.', 'Mechanism, format, and trial status', 'target', 'design-sources.html', 'Review opportunities'),
    ], 'A completed trial is not an approval. A curated target mapping is not a measured interaction.'),
    'molecular-library': ('Prepare molecules for screening', 'Check molecule identity and known interactions before selecting a binding site and screening method.', [
        step('01', 'Resolve the molecule', 'Track identity, sequence or chemical structure, provenance, and preparation flags.', 'A reproducible library input', 'molecule'),
        step('02', 'Classify the relationship', 'Label known interactions and targets proposed for screening.', 'Known interactions and proposed targets', 'compare'),
        step('03', 'Choose the screening method', 'Use a compatible site and method; carry controls and limitations into the readout.', 'Screening plan and controls', 'check', 'screening.html', 'Open screening readout'),
    ], 'Resolving a molecule does not establish that it binds a proposed target.'),
    'screening': ('Screen molecules and compare results', 'Test the reference control, dock the library, then repeat and inspect selected poses.', [
        step('01', 'Prepare a matched system', 'Record receptor, ligand chemistry, pocket, scoring function, and parameters.', 'Reproducible inputs', 'molecule', 'molecular-library.html', 'Inspect input library'),
        step('02', 'Test the reference control', 'Compare the reference pose with the chosen geometry criteria.', 'A recorded pass or failure', 'check'),
        step('03', 'Screen the library', 'After the reference passes, dock the prepared molecules and save all outcomes.', 'Poses, scores, and failure records', 'filter'),
        step('04', 'Confirm and inspect', 'Repeat selected runs with the same settings and compare the poses.', 'Repeated scores and inspected poses', 'compare'),
    ], 'A single seed cannot establish repeatability. Score repeatability does not establish pose convergence or binding.'),
    'structures': ('Select a structure and binding site', 'Inspect the available coordinates and map the site to the exact target construct.', [
        step('01', 'Register the source', 'Preserve experimental, predicted, and derived records as different evidence classes.', 'A labeled structure record', 'sources'),
        step('02', 'Inspect the construct', 'Check chains, sequence coverage, partners, glycans, and residue numbering.', 'Chains, partners, and residue numbering', 'structure'),
        step('03', 'Assess the site', 'Examine accessible geometry and known interfaces; record gaps and uncertainty.', 'Selected site and missing coordinates', 'target', 'design-sources.html', 'Review site decisions'),
    ], 'A deposited complex, predicted complex, and target-only design construct support different claims.'),
    'binders': ('Design and evaluate protein binders', 'Generate candidate backbones and sequences, predict their target complexes, then compare them with reference controls.', [
        step('01', 'Select the target and site', 'Specify the construct, residue numbering, design constraints, and reference controls.', 'Target, site, and design constraints', 'target', 'design-sources.html', 'Inspect design decisions'),
        step('02', 'Generate candidates', 'Generate backbones and design sequences. Record each sequence’s parent backbone.', 'Candidate sequences and structures', 'structure'),
        step('03', 'Evaluate independently', 'Predict target–binder complexes and score them alongside the controls.', 'Predicted complexes and scores', 'compare'),
        step('04', 'Select candidates', 'Apply the review criteria and specify the assays needed for each selected candidate.', 'Candidates for experimental testing', 'report'),
    ], 'A generated sequence or high interface score does not establish binding, selectivity, or efficacy.'),
    'design-sources': ('Plan, run, and record a design', 'Specify the target and intended action. Choose the method, run the tools, and import their outputs.', [
        step('01', 'Choose the target, site, and intended effect', 'Record desired action, disease rationale, target, site, and principal risks.', 'Target, site, and intended action', 'target'),
        step('02', 'Choose the tools', 'Check that the tools support the requested design and controls within the compute budget.', 'Tools, controls, and compute budget', 'check'),
        step('03', 'Run the tools and import results', 'Import result files with their candidate identifiers, run records, and failures.', 'Result records and files', 'structure'),
        step('04', 'Review and report', 'Compare results with the selection criteria and link the supporting files.', 'Report with source and result links', 'report', 'index.html', 'Report overview'),
    ], 'File-integrity and packaging checks do not substitute for scientific validation.'),
    'study': ('Disease, study population, and sources', 'Record the disease and cell state, searches, and retrieval dates used to build the target list.', [
        step('01', 'Disease and study population', 'Record the disease, organism, cell population, sources, and search dates.', 'Study plan', 'scope'),
        step('02', 'Record the searches', 'Preserve executed queries, retrieval dates, counts, and partial-source limitations.', 'Search terms, dates, and record counts', 'sources'),
        step('03', 'Review search coverage', 'Account for retained, excluded, and unresolved entities within that scope.', 'Target counts and search gaps', 'filter', 'targets.html', 'Open the target census'),
    ], 'Complete within the recorded search scope does not mean every biologically relevant target is known.'),
}


def page_diagram(key):
    if key not in PAGE_MAPS:
        return ''
    title, subtitle, items, note = PAGE_MAPS[key]
    identifier = 'workflow-' + key
    tone = 'compute' if key in {'screening', 'binders'} else 'planning' if key in {'structures', 'design-sources', 'molecular-library', 'treatments'} else 'evidence'
    out = f'<figure id="{identifier}" class="workflow wf-page" aria-labelledby="{identifier}-title">' + caption(identifier, title, subtitle)
    out += f'<nav class="diagram-nav" aria-label="Page sections"><a href="#{identifier}-records">View results and records ↓</a></nav>'
    out += render_diagrams(key)
    out += '<details class="workflow-notes"><summary>Read the workflow steps and interpretation notes</summary>'
    out += chain(items, label=title, tone=tone, gate_after=1 if key == 'screening' else None)
    if key == 'screening':
        out += '<div class="wf-gate-outcomes"><div class="wf-pass"><strong>STEP 02 · REFERENCE PASSES →</strong><span>Screen the library, repeat selected runs, and inspect poses.</span></div><div class="wf-hold"><strong>STEP 02 · REFERENCE FAILS ↶</strong><span>Save the failed output. Review the preparation, pocket, and method, then retest the reference before expanding the run.</span></div></div>'
    elif key == 'binders':
        out += '<div class="wf-control-track">' + icon('check') + '<p><strong>Parallel reference-control track</strong><br>Evaluate positive and negative controls alongside the candidates. Calibration informs interpretation; controls are not newly designed candidates.</p></div>'
    elif key == 'structures':
        out += '<div class="wf-evidence-types"><span><strong>Experimental</strong> · deposited observations</span><span><strong>Predicted</strong> · model outputs</span><span><strong>Derived</strong> · transformed inputs</span></div>'
    out += f'<p class="wf-takeaway">{esc(note)}</p>'
    return out + footer() + f'</details><div id="{identifier}-records" tabindex="-1"></div></figure>'


def insert_page_diagram(body, current, title):
    """Put records first, with a direct route to the page's full diagrams."""
    if current == 'overview':
        return body
    key = 'dossier' if title.endswith(' dossier') else current
    diagram = page_diagram(key)
    start = body.find('<div class="page-heading">')
    if start < 0 or not diagram:
        return body
    depth = 0
    for match in re.finditer(r'</?div\b[^>]*>', body[start:]):
        depth += -1 if match.group().startswith('</') else 1
        if depth == 0:
            end = start + match.end()
            anchor = f'<div id="workflow-{key}-records" tabindex="-1"></div>'
            diagram = diagram.replace(anchor, '').replace('View results and records ↓', 'Back to results and records ↑')
            navigation = f'<nav class="diagram-nav" aria-label="Page contents"><a href="#workflow-{key}">Workflow and diagrams ↓</a></nav>'
            return body[:end] + navigation + anchor + body[end:] + diagram
    return body
