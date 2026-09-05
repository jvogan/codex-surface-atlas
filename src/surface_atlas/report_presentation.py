"""Readable, source-derived views for the offline Surface Atlas report.

These views consume the builder's normalized snapshot; they never inspect live
provider directories or infer execution from absent imported records.
"""
from __future__ import annotations

import html
import hashlib
import json
import math

from .screening_context import screening_role, screening_role_group, screening_run_contexts


def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fmt(value):
    return f"{value:,.2f}".rstrip("0").rstrip(".") if number(value) else "Not measured"


def obj(value):
    return value if isinstance(value, dict) else {}


def object_records(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def expression_summary(record):
    """Keep population labels tied to their recorded expression context."""
    context = obj(record.get('expression_context'))
    if context:
        population = context.get('population_key', 'disease_cells')
        label = context.get('population_label', 'Disease cells')
    else:
        context = obj(record.get('cancer_surfaceome_context'))
        population, label = 'tumor', 'Tumor cells'
        if not context:
            owner = obj(record.get('cell_owner'))
            observed = obj(owner.get('observed_percent_expressing'))
            if observed:
                context = {'single_cell_percent_expressing': {'values': observed},
                           'cancer_code': owner.get('cancer_code'),
                           'claim_ceiling': owner.get('claim_ceiling'),
                           'measurement_kind': 'transcript detection'}
    values = obj(obj(context.get('single_cell_percent_expressing')).get('values'))
    cohort = context.get('cohort_name') or context.get('cohort_code') or context.get('cancer_code')
    return context, values, values.get(population) if isinstance(population, str) else None, str(label), cohort


def cell_population_summary(value):
    if not isinstance(value, dict):
        return value
    category = str(value.get('owner_category') or 'unresolved').replace('-', ' ')
    cohort = value.get('cancer_code')
    types = value.get('highest_observed_cell_types')
    highest = value.get('highest_observed_percent_expressing')
    if isinstance(types, list) and types and number(highest):
        names = ', '.join(str(name).replace('_', ' ') for name in types)
        detail = f'highest recorded transcript detection: {names} {fmt(highest)}%'
    else:
        detail = 'transcript measurements unavailable'
    return f'{category} · {cohort + " · " if isinstance(cohort, str) else ""}{detail}; provisional transcript context'


def narrative_overview(b, plan, ledger, collections, binders, artifact_map, generated_at):
    targets = collections.get("targets.json", [])
    discovered = collections.get("discovered-entities.json", [])
    excluded = collections.get("excluded-targets.json", [])
    unresolved = obj(ledger.get("counts")).get("unresolved_records")
    if unresolved is None:
        unresolved = sum(r.get("surface_disposition") == "unresolved" for r in discovered)
    structures = collections.get("structures.json", [])
    screens = collections.get("screening-results.json", [])
    interventions = collections.get("interventions.json", [])
    molecules = collections.get("molecular-library.json", [])
    image_record = next((r for r in structures if b.structure_image_artifact(r, artifact_map)[0]), None)
    figure = ""
    if image_record:
        image_path, _ = b.structure_image_artifact(image_record, artifact_map)
        if image_path:
            accession = image_record.get("accession", image_record.get("structure_id", "Structure"))
            figure = (f'<figure class="cover-figure"><a href="structures.html#structure-{esc(b.slugify(image_record.get("structure_id", "")))}">'
                      f'<img src="{esc(image_path)}" alt="{esc(image_record.get("selection_reason", accession))}" width="1200" height="900"></a>'
                      f'<figcaption><span class="figure-number">FIG. 01</span> {esc(accession)} · '
                      f'{esc(image_record.get("evidence_class", image_record.get("structure_class", "Registered structure")))}. '
                      'Open the structure library for provenance and coordinates.</figcaption></figure>')
    disease = obj(plan.get("disease"))
    title = b.scalar_text(b.pick(disease, "name", "label"), empty="Disease-associated cell surfaces")
    body = f'''<div class="report-masthead"><span>RESEARCH ATLAS / 01</span><span>CODEX SURFACE ATLAS</span></div>
    <section class="cover{' cover-text-only' if not figure else ''}"><div class="cover-copy"><p class="eyebrow">Cell-surface target research</p>
    <h1>{esc(title)}</h1><p class="cover-deck">Compare surface targets, binding sites, and candidate results.</p>
    <p class="lede">Open each target to inspect its evidence, known interventions, structures, and screening or binder results.</p>
    <div class="cover-actions"><a class="primary-link" href="#workflow-overview">Follow the workflow <span aria-hidden="true">↓</span></a><a href="explore.html">Explore the target atlas ↗</a></div>
    <p class="snapshot-note">Report generated · {esc(generated_at)}</p></div>{figure}</section>'''
    body += '<div class="headline-metrics">' + ''.join(
        f'<a href="{href}"><strong>{count:,}</strong><span>{label}</span></a>'
        for count, label, href in [(len(targets), "retained surface targets", "explore.html"), (len(interventions), "intervention records", "treatments.html"), (len(structures), "registered structures", "structures.html"), (len(molecules), "library molecules", "molecular-library.html")]
    ) + '</div>'
    from .report_workflows import overview
    body += overview()
    census_complete = obj(ledger.get('_report_state')).get('census_accounting_validated') is True
    accounting_title = 'Target counts after review' if census_complete else 'Recorded target classifications'
    body += f'''<section id="readout" class="section brief-section"><div><p class="eyebrow">Target census</p><h2>What this atlas records</h2></div><div class="brief-copy">
    <p class="large-prose">This atlas records <strong>{len(discovered):,} discovered entities</strong> and retains <strong>{len(targets):,} cell-surface targets</strong>.</p>
    <p>Each target page lists source cohorts, surface annotations, scores, and missing measurements. Each target’s tier specifies the depth of structure review.</p>
    <a href="study.html">Study scope and source coverage →</a></div></section>'''
    total = max(len(discovered), 1)
    body += f'<section class="section"><div class="section-heading"><div><p class="eyebrow">Discovery accounting</p><h2>{accounting_title}</h2></div><a href="targets.html">Open the complete census →</a></div><div class="census-strip" aria-hidden="true">'
    for count, klass in [(len(targets), 'retained'), (len(excluded), 'excluded'), (unresolved, 'unresolved')]:
        body += f'<span class="{klass}" style="flex-grow:{count / total}"></span>'
    body += '</div><dl class="census-key">' + ''.join(
        f'<div><dt><i class="key-dot {klass}" aria-hidden="true"></i>{label}</dt><dd>{count:,}</dd></div>'
        for count, label, klass in [(len(targets), 'Retained surface targets', 'retained'), (len(excluded), 'Excluded from the surface universe', 'excluded'), (unresolved, 'Unresolved identity or evidence', 'unresolved')]
    ) + '</dl><p class="small">Open the census for each exclusion reason and the study page for searched sources and coverage gaps.</p></section>'
    body += f'''<section class="section"><div class="section-heading"><div><p class="eyebrow">Computational results</p><h2>Imported screening and binder records</h2></div></div><div class="lane-grid">
    <article class="lane"><span class="lane-index">01 / MOLECULES</span><h3>Defined-pocket screening</h3><p>Compare docking scores, saved poses, and reference controls.</p>
    <div class="lane-count">{len(screens):,}<span>screening records imported</span></div><p class="small">{'Open the screening results to compare individual runs and controls.' if screens else 'No normalized screening records are included in this report.'}</p><a href="screening.html">Inspect the molecular screen →</a></article>
    <article class="lane"><span class="lane-index">02 / PROTEIN BINDERS</span><h3>Protein-binder evaluation</h3><p>Review generated sequences, predicted complexes, and reference controls.</p>
    <div class="lane-count">{len(binders):,}<span>candidate records imported</span></div><p class="small">{'Open each candidate’s results to review its checks and selection status.' if binders else 'No normalized candidate records are included in this report.'}</p><a href="binders.html">Inspect the binder campaign →</a></article></div></section>'''
    body += '<section class="section"><div class="section-heading"><div><p class="eyebrow">Report sections</p><h2>Explore the records</h2></div></div><div class="chapter-links">'
    for index, (href, title, text) in enumerate([
        ('explore.html', 'Target atlas', 'Compare target scores and open the supporting measurements.'),
        ('structures.html', 'Structure library', 'Inspect structures, binding partners, and target constructs.'),
        ('treatments.html', 'Known interventions', 'Check which sources support each intervention’s target assignment.'),
        ('design-sources.html', 'Methods & provenance', 'Review design plans, tool availability, source records, and Binder Lane requests.')], 1):
        body += f'<a href="{href}"><span class="chapter-number">0{index}</span><div><h3>{title}</h3><p>{text}</p></div><span aria-hidden="true">↗</span></a>'
    body += '</div></section>'
    return body


def explorer_records(profiles):
    records = []
    for p in profiles:
        r = p['record']
        evidence = obj(r.get('evidence_score'))
        risk = obj(r.get('risk'))
        context, expression, measured_expression, population, cohort = expression_summary(r)
        components = object_records(evidence.get('components'))
        gaps = list(risk.get('unresolved_dimensions') or [])
        for component in components:
            if component.get('state') == 'not-measured':
                gap = str(component.get('component') or 'Evidence component') + ' — not measured'
                if gap not in gaps:
                    gaps.append(gap)
        records.append(dict(id=p['id'], name=p['name'], href=f"target-{p['slug']}.html", tier=p['tier'],
                            evidence=evidence.get('score'), risk=risk.get('observed_signal_score'), evidenceMaximum=evidence.get('maximum'), riskMaximum=risk.get('maximum'),
                            evidenceComponents=components, missingDataRule=evidence.get('missing_data_rule'), warningSignals=object_records(risk.get('observed_signals')),
                            tumor=expression.get('tumor') if not r.get('expression_context') else None,
                            expression=measured_expression, population=population, cohort=cohort,
                            interventions=obj(r.get('intervention_summary')).get('assigned_intervention_count'),
                            structures=obj(r.get('structure_anchor_summary')).get('verified_anchor_count'),
                            gaps=gaps,
                            modalities=[{'name': m.get('modality'), 'score': m.get('score')} for m in r.get('modality_fit', []) if isinstance(m, dict)]))
    return records


def render_explorer(b, profiles, collections=None):
    records = explorer_records(profiles)
    if collections is not None:
        for record in records:
            record['structures'] = sum(b.related(s, record['id'], record['name']) for s in collections.get('structures.json', []))
            record['interventions'] = sum(b.related(s, record['id'], record['name']) for s in collections.get('interventions.json', []))
    body = b.page_heading('Interactive target atlas', 'Compare target evidence',
                          'Select a target to inspect its source measurements, score components, and missing evidence.')
    tiers = sorted({str(p['tier']) for p in profiles if p.get('tier')})
    labels = {'structure-a': 'Wave A · full review', 'structure-b': 'Wave B · focused review', 'structure-c': 'Wave C · representative structure', 'retained-unmodeled': 'Retained · outside structure waves'}
    tier_options = ''.join(f'<option value="{esc(t)}">{esc(labels.get(t, t))}</option>' for t in tiers)
    colors = {'structure-a': '#146b60', 'structure-b': '#347da4', 'structure-c': '#a47126'}
    legend = ''.join(f'<span><i class="key-dot" style="background:{colors.get(t, "#96a7a0")}"></i>{esc(labels.get(t, t))}</span>' for t in tiers)
    body += f'''<div class="explorer-controls"><label>Find a target<input id="atlas-search" type="search" placeholder="Gene symbol or target ID" autocomplete="off"></label>
    <label>Structure wave<select id="atlas-tier"><option value="">All retained targets</option>{tier_options}</select></label>
    <label>Order by<select id="atlas-order"><option value="evidence">Evidence score · highest first</option><option value="name">Gene symbol · A–Z</option><option value="risk">Observed warning signals · highest first</option></select></label></div>
    <p class="small" id="atlas-count" role="status"></p><div class="explorer-layout"><div class="plot-panel"><div class="plot-title"><h2>Evidence landscape</h2><span class="small">Each point is a retained target</span></div>
    <div id="atlas-plot" class="atlas-plot"></div><div class="plot-legend">{legend}</div>
    <p class="small">Right: more evidence points under the recorded scoring policy. Up: more recorded warning signals. Select a target to see its score components and missing measurements. Lower recorded warning signals do <strong>not</strong> establish safety; scores are not probabilities.</p></div><aside id="atlas-selection" class="target-inspector" aria-label="Selected target"></aside></div>
    <section class="section"><div class="section-heading"><h2>Browse the targets</h2><a href="targets.html">Full data table & downloads →</a></div><div id="atlas-target-list" class="target-browser"></div><div class="browser-pagination"><button id="atlas-prev" type="button">Previous</button><span id="atlas-page" role="status"></span><button id="atlas-next" type="button">Next</button></div></section>
    <noscript><p>Interactive comparison requires JavaScript. The complete source-linked target census is available in the <a href="targets.html">target table</a>.</p></noscript>'''
    encoded = json.dumps(records, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return body + f'<script type="application/json" id="atlas-explorer-data">{encoded}</script>'


def render_dossier_context(b, record):
    """Expose real nested evidence without manufacturing flat measurements."""
    score = obj(record.get('evidence_score'))
    risk = obj(record.get('risk'))
    context, values, measured_expression, population, cohort = expression_summary(record)
    if not score and not risk and not context:
        return ''
    body = '<section class="section dossier-synthesis"><p class="eyebrow">Target evidence</p><h2>Measurements, cell populations, and missing data</h2>'
    body += '<div class="dossier-summary">'
    metrics = [
        ('Evidence score', score.get('score'), 'Points assigned by the recorded evidence-scoring rules.'),
        ('Observed warning signals', risk.get('observed_signal_score'), 'Higher means more measured warning signals. This is not a safety score.')]
    if context:
        kind = 'transcript detection' if context.get('measurement_kind') == 'transcript detection' else 'expressing'
        metrics.append((population + ' ' + kind, measured_expression, f"Percent in the recorded {cohort or 'source'} cohort."))
    for index, (label, value, help_text) in enumerate(metrics):
        body += f'<div><span class="small">{esc(label)}</span><strong>{fmt(value)}{"%" if index == 2 and number(value) else ""}</strong><p class="small">{esc(help_text)}</p></div>'
    body += '</div>'
    if values:
        body += '<details class="evidence-disclosure"><summary>Compare expression across recorded cell populations</summary><div class="expression-bars">'
        for name, value in sorted(values.items(), key=lambda x: x[1] if number(x[1]) else -1, reverse=True):
            body += f'<div><span>{esc(name.replace("_", " "))}</span><span class="bar-track"><i style="width:{max(0,min(100,value)) if number(value) else 0}%"></i></span><strong>{fmt(value)}{"%" if number(value) else ""}</strong></div>'
        body += f'</div><p class="small">Fraction of cells with transcript detection in the recorded {esc(cohort or "source")} cohort; RNA expression does not quantify accessible surface protein.</p>'
        if context.get('claim_ceiling'):
            body += f'<p class="small">{esc(context["claim_ceiling"])}</p>'
        body += '</details>'
    signals = object_records(risk.get('observed_signals'))
    if signals:
        body += '<details class="evidence-disclosure"><summary>Recorded warning signals</summary>'
        for signal in signals:
            body += f'<h3>{esc(str(signal.get("signal", "Recorded signal")).replace("-", " "))}</h3>'
            fields = []
            for key, value in signal.items():
                if key == 'signal':
                    continue
                label = key.replace('_', ' ').capitalize()
                display = fmt(value) if number(value) else value
                if number(value) and key.endswith('_percent'):
                    display += '%'
                fields.append((label, display))
            body += b.field_list_html(fields)
        body += f'<p class="small">{esc(risk.get("score_meaning", "These are recorded warning signals, not a normal-tissue safety assessment."))}</p></details>'
    components = score.get('components', [])
    if components:
        body += '<details class="evidence-disclosure"><summary>Evidence score components</summary><div class="score-components">'
        for c in components:
            body += f'<div><span>{esc(str(c.get("component", "Component")).replace("-", " "))}</span><strong>{fmt(c.get("points"))} / {fmt(c.get("maximum"))}</strong><span class="small">{esc(c.get("basis", c.get("state", "")))}</span></div>'
        body += f'</div><p class="small">{esc(score.get("missing_data_rule", "Missing measurements remain unresolved."))}</p></details>'
    gaps = risk.get('unresolved_dimensions', [])
    if gaps:
        body += '<div class="open-questions"><h3>Missing measurements</h3><ul>' + ''.join(f'<li>{esc(str(g).replace("-", " "))}</li>' for g in gaps) + '</ul></div>'
    modalities = record.get('modality_fit', [])
    if modalities:
        body += '<details class="evidence-disclosure"><summary>Molecule-format fit scores</summary><p class="small">These scores compare formats for research planning. Binding and efficacy require separate measurements.</p><div class="modality-list">'
        for m in modalities:
            body += f'<div><span>{esc(str(m.get("modality", "")).replace("-", " "))}</span><strong>{fmt(m.get("score"))} / {fmt(m.get("maximum"))}</strong></div>'
        body += '</div></details>'
    return body + '</section>'




def render_record_confirmation(b, record):
    assessment = obj(record.get('confirmation_assessment'))
    if not assessment:
        return ''
    identity = record.get('molecule_name') or record.get('molecule_id') or record.get('screening_result_id', 'Screening record')
    fields = [('Molecule', identity), ('Record', record.get('screening_result_id')),
              ('Assessment state', assessment.get('state')),
              ('Assessment passed', assessment.get('overall_gate_pass')),
              ('Requested seeds', assessment.get('requested_seed_count')),
              ('Successful seeds', assessment.get('successful_seed_count'))]
    return ('<div class="record-confirmation"><h4>Record confirmation assessment</h4>'
            + b.field_list_html(fields)
            + (f'<p class="small">{esc(assessment["interpretation"])}</p>' if assessment.get('interpretation') else '')
            + f'<details><summary>Assessment details · {esc(identity)}</summary><pre>{esc(json.dumps(assessment, indent=2, ensure_ascii=False))}</pre></details></div>')


def render_screen_provenance(b, metadata, records):
    runs = screening_run_contexts(metadata, records)
    assessed = [record for record in records if obj(record.get('confirmation_assessment'))]
    if not runs and not assessed:
        return ''
    body = '<section class="section"><div class="section-heading"><h2>Screen runs and confirmation</h2></div><p>Open each run to compare its requested work, returned records, and confirmation results.</p>'
    for run_id, context in runs.items():
        run_records = [record for record in records if record.get('run_id') == run_id]
        run_assessed = [record for record in run_records if obj(record.get('confirmation_assessment'))]
        body += f'<article class="evidence-disclosure"><h3>{esc(run_id)}</h3>'
        body += b.render_metrics([('Imported records', len(run_records)), ('Completed records', sum(record.get('execution_state') == 'completed' for record in run_records)), ('Run confirmations', len(context['confirmations'])), ('Record confirmations', len(run_assessed))])
        body += '<details><summary>Source run</summary><pre>' + esc(json.dumps(context['source'], indent=2, ensure_ascii=False)) + '</pre></details>'
        for index, confirmation in enumerate(context['confirmations'], 1):
            fields = [(f'Confirmation {index} state', confirmation.get('state'))]
            fields.extend((key.capitalize(), confirmation[key]) for key in ('requested', 'completed') if key in confirmation)
            body += b.field_list_html(fields)
            body += f'<details><summary>Confirmation context {index}</summary><pre>{esc(json.dumps(confirmation, indent=2, ensure_ascii=False))}</pre></details>'
        for record in run_assessed:
            body += render_record_confirmation(b, record)
        if not context['confirmations'] and not run_assessed:
            body += '<p class="small">No confirmation context recorded for this run.</p>'
        body += '</article>'
    if not runs:
        for record in assessed:
            body += render_record_confirmation(b, record)
    body += '<p><a href="data/screening-results.json" download>Download screening records and run provenance</a></p></section>'
    return body


def saved_pose_context(record):
    """Describe linked coordinates using their own recorded observation."""
    context = obj(record.get('pose_artifact_context'))
    if not context:
        return ''
    parts = [str(context[key]) for key in ('stage', 'contents') if context.get(key)]
    seed = context.get('seed')
    if seed is not None:
        parts.append(f'Seed {seed}')
        artifact = record.get('pose_artifact')
        path = artifact.get('path') if isinstance(artifact, dict) else artifact
        observations = []
        for observation in object_records(record.get('seed_observations')):
            observed_artifact = observation.get('pose_artifact')
            observed_path = observed_artifact.get('path') if isinstance(observed_artifact, dict) else observed_artifact
            if observation.get('seed') == seed and path and observed_path == path:
                observations.append(observation)
        scores = {o['top_vinardo_score_kcal_mol'] for o in observations if number(o.get('top_vinardo_score_kcal_mol'))}
        if len(scores) == 1:
            parts.append(f'Top pose Vinardo {next(iter(scores))} kcal/mol')
    return ' · '.join(parts)


def render_screen_readout(b, records, artifact_map, profiles, metadata=None):
    """A compact result narrative, grouped so unlike scoring contexts never mix."""
    body = b.page_heading('Computational results', 'Molecular screening results',
                          'Compare molecules with their reference controls, inspect saved poses, and check repeated runs. Docking scores rank computed poses; affinity requires a separate measurement.')
    body += render_screen_provenance(b, metadata, records)
    if not records:
        return body + b.empty_state('No screening results have been imported', 'Add screening records and rebuild the report to display results here.', 'molecular-library.html')
    target_links = {p['id']: (p['name'], f"target-{p['slug']}.html") for p in profiles}
    groups = {}
    for r in records:
        key = tuple(b.scalar_text(value, empty=f'Unspecified {label}') for value, label in (
            (r.get('run_id'), 'run'), (r.get('target_id'), 'target'),
            (b.pick(r, 'site_id', 'site', 'binding_site', 'epitope', 'pocket', 'docking_scope'), 'site'),
            (r.get('scoring_function'), 'score'), (r.get('score_units'), 'units'),
            (r.get('route'), 'route'), (r.get('model_version'), 'model'),
        ))
        groups.setdefault(key, []).append(r)
    for (run, target, site, scoring, units, route, model), group in groups.items():
        group_token = hashlib.sha256(json.dumps([run, target, site, scoring, units, route, model]).encode()).hexdigest()[:12]
        prospective = [r for r in group if screening_role_group(r) == 'prospective']
        controls = [r for r in group if screening_role_group(r) == 'control']
        other = [r for r in group if screening_role_group(r) == 'other']
        label, href = target_links.get(target, (target, 'targets.html'))
        completed = sum(r.get('execution_state') == 'completed' for r in group)
        body += f'<section class="section"><div class="section-heading"><div><p class="eyebrow">Primary prospective screen</p><h2>{esc(label)} · {esc(scoring)}</h2></div><a href="{esc(href)}">Open target evidence →</a></div>'
        body += f'<p class="small mono">{esc(run)} · {esc(site)}</p>'
        body += b.render_metrics([('Imported records', len(group)), ('Prospective molecules', len(prospective)), ('Control molecules', len(controls)), ('Completed records', completed)])
        one_seed = sum(obj(r.get('seed_agreement')).get('successful_comparable_seed_count', r.get('successful_seed_count', 0)) == 1 for r in prospective if r.get('execution_state') == 'completed' and number(r.get('pose_score')))
        if one_seed:
            body += f'<div class="open-questions"><h3>Molecules awaiting repeat runs</h3><p>{one_seed} prospective molecules have one comparable successful seed. Repeatability is not established by a single run; a recorded zero score span is not evidence of seed agreement.</p></div>'
        body += '<p>Compare candidate scores with the reference controls, then inspect saved poses and target contacts. Favorable scores can also occur for unrelated reference ligands; follow-up measurements determine what can be concluded.</p>'
        for heading, subset in [('Reference controls', controls), ('Prospective observations', prospective), ('Other imported observations', other)]:
            if not subset:
                continue
            rows = []
            # Preserve recorded order: ranking direction is model-specific.
            for r in subset:
                agreement = obj(r.get('seed_agreement'))
                seeds = agreement.get('successful_comparable_seed_count', r.get('successful_seed_count'))
                repeatability = f'{seeds} comparable seeds · span {fmt(agreement.get("top_score_span_kcal_mol"))}' if number(seeds) and seeds > 1 else 'One seed · repeatability not assessed' if seeds == 1 else 'Not assessed'
                observed = [o for o in r.get('seed_observations', []) if isinstance(o, dict)]
                exhaust = sorted({str(obj(o.get('parameters')).get('exhaustiveness')) for o in observed if obj(o.get('parameters')).get('exhaustiveness') is not None})
                pose_artifact = r.get('pose_artifact')
                pose_path = pose_artifact.get('path') if isinstance(pose_artifact, dict) else pose_artifact
                pose = artifact_map.get(pose_path) if isinstance(pose_path, str) else None
                molecule_id = r.get('molecule_id', '')
                name = r.get('molecule_name', molecule_id)
                score = fmt(r['pose_score']) if number(r.get('pose_score')) else 'Not computed' if r.get('execution_state') == 'planned' else 'No score recorded'
                preview = b.preview_controls(
                    r,
                    artifact_map,
                    title=f"{b.scalar_text(name, empty='Screen result')} · {b.scalar_text(target, empty='Target')}",
                    evidence=b.scalar_text(b.pick(r, 'evidence_class', 'claim_ceiling', 'evidence_state'), empty='Computational screening hypothesis'),
                    record_id=b.typed_record_id(r, 0, 'screening', 'screening_result_id', 'screening_id', 'screen_id', 'result_id'),
                )
                rows.append([
                    b.table_cell(f'<strong>{esc(name)}</strong><span class="table-id">{esc(molecule_id)}</span>', name),
                    b.table_cell(esc(screening_role(r).replace('-', ' '))),
                    b.table_cell(esc(score) + (f'<span class="table-id">{esc(r["pose_id"])}</span>' if r.get('pose_id') else ''), r.get('pose_score', '')),
                    b.table_cell(esc(repeatability)),
                    b.table_cell(esc(', '.join(exhaust) or 'Not recorded')),
                    b.table_cell(b.state_pill(r.get('execution_state')) + (f'<p class="small">{esc(b.scalar_text(r["failure_reason"]))}</p>' if r.get('failure_reason') else '')),
                    b.table_cell((b.link_html(pose, 'Download pose', download=True) + (f'<p class="small">{esc(saved_pose_context(r))}</p>' if saved_pose_context(r) else '')) if pose else 'No linked pose'),
                    b.table_cell(preview or '<span class="small">No structure preview</span>', bool(preview)),
                ])
            body += f'<h3 class="screen-subheading">{heading}</h3>'
            body += b.render_table('readout-' + group_token + '-' + b.slugify(heading), ['Molecule', 'Role', f'{scoring} ({units})', 'Score repeatability', 'Exhaustiveness', 'State', 'Pose', 'Structure preview'], rows,
                                   caption=f'{heading}. Scores are shown as recorded; sort ascending or inspect source order. Score span measures variation across comparable seeds, not pose convergence.',
                                   filter_label=f'Search {heading.lower()}', sort_labels=[(0, 'Molecule'), (2, 'Score · low to high')])
        body += '<details class="evidence-disclosure"><summary>Protocol and interpretation</summary>'
        body += b.field_list_html([('Scoring function', scoring), ('Score units', units), ('Interpretation', group[0].get('score_interpretation')), ('Route', group[0].get('route')), ('Model version', group[0].get('model_version'))])
        body += '<p class="small">Check the exhaustiveness setting before comparing runs. Controls may use different search settings. Do not interpret scores from different protocols as a calibrated affinity comparison.</p></details></section>'
    return body + '<section class="section"><a href="molecular-library.html">Open full molecule identities, preparation flags, known interactions, and complete screen records →</a></section>'
