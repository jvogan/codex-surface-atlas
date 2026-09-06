"""Transparent action-specific evidence comparison; no efficacy or safety score."""
from __future__ import annotations

import html
import json
import re
from typing import Any

SCHEMA_VERSION = 'codex-surface-action-evidence/v0.1'
TOKEN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:-]{0,119}$')
CRITERIA = {
    'surface_access': ('Surface access', 'Measure binding to the intended extracellular target on intact cells in the relevant context.'),
    'internalization': ('Internalization', 'Measure uptake and intracellular trafficking after target binding in the relevant cells.'),
    'payload_response': ('Target-dependent payload response', 'Compare payload response with target-negative and unconjugated controls.'),
    'partner_site_access': ('Partner-site access', 'Measure access and occupancy at the specified functional partner site.'),
    'functional_blockade': ('Functional blockade', 'Measure the intended functional blockade with target-specific and pathway controls.'),
    'tissue_contrast': ('Tissue contrast', 'Measure target-associated signal relative to matched background and relevant normal tissues.'),
    'tracer_retention': ('Tracer retention', 'Measure tracer retention and clearance over the intended observation interval.'),
}
ACTIONS = {
    'payload-delivery': {'label': 'Payload delivery', 'modality': 'Targeted carrier or conjugate experiment', 'criteria': ['surface_access', 'internalization', 'payload_response']},
    'blockade': {'label': 'Blockade', 'modality': 'Site-directed blocking reagent experiment', 'criteria': ['surface_access', 'partner_site_access', 'functional_blockade']},
    'imaging': {'label': 'Imaging', 'modality': 'Targeted tracer experiment', 'criteria': ['surface_access', 'tissue_contrast', 'tracer_retention']},
}
CAVEAT = ('Evidence coverage only, not affinity, safety, efficacy, or a therapeutic recommendation. '
          'Source claims are recorded interpretations, not independently verified findings; contexts may differ. '
          'Existing target scores, expression, structure tiers, and modality labels do not affect ordering.')
ORDER_RULE = ('Order by the number of supported criteria for the selected action, descending; '
              'ties use exact target ID. Contradicted and missing criteria each add zero support. '
              'Missing evidence is never evidence of suitability. Counts are not weighted and do not resolve conflicting contexts.')


def _rows(targets: Any) -> list:
    rows = targets.get('records', []) if isinstance(targets, dict) else targets
    if not isinstance(rows, list):
        raise ValueError('targets must be a collection or record list')
    return rows


def _text(value: Any, maximum: int = 2000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum and '\x00' not in value


def validate_action_evidence(targets: Any) -> list[str]:
    """Strict optional contract. Unknown/missing observations confer no support."""
    errors = []
    seen = set()
    try:
        rows = _rows(targets)
    except ValueError as exc:
        return [str(exc)]
    for target in rows:
        identifier = target.get('target_id') if isinstance(target, dict) else None
        context = f'targets.json: {identifier} action_evidence'
        try:
            if not isinstance(identifier, str) or not TOKEN.fullmatch(identifier) or identifier in seen:
                raise ValueError('target identity must be exact, valid, and unique')
            seen.add(identifier)
            if 'action_evidence' not in target:
                continue
            evidence = target['action_evidence']
            if not isinstance(evidence, dict) or set(evidence) != {'schema_version', 'target_id', 'sources', 'observations'}:
                raise ValueError('requires only schema_version, target_id, sources, observations')
            if evidence['schema_version'] != SCHEMA_VERSION or evidence['target_id'] != identifier:
                raise ValueError('schema version or exact target identity mismatch')
            sources = evidence['sources']
            if not isinstance(sources, list) or len(sources) > 64:
                raise ValueError('sources must be an array of at most 64 entries')
            source_ids = set()
            for source in sources:
                if not isinstance(source, dict) or set(source) != {'source_id', 'citation'}:
                    raise ValueError('source requires only source_id and citation')
                sid = source['source_id']
                if not isinstance(sid, str) or not TOKEN.fullmatch(sid) or sid in source_ids or not _text(source['citation']):
                    raise ValueError('source IDs must be unique and citations nonempty')
                source_ids.add(sid)
            observations = evidence['observations']
            if not isinstance(observations, dict) or set(observations) - set(CRITERIA):
                raise ValueError('observations must use the named action criteria only')
            for name, observation in observations.items():
                if not isinstance(observation, dict) or set(observation) != {'state', 'basis', 'source_ids'}:
                    raise ValueError(f'{name} requires only state, basis, source_ids')
                state, basis, refs = (observation[k] for k in ('state', 'basis', 'source_ids'))
                if state not in ('supported', 'contradicted', 'unknown') or not _text(basis):
                    raise ValueError(f'{name} needs a valid state and explicit contextual basis')
                if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs) or len(refs) != len(set(refs)) or set(refs) - source_ids:
                    raise ValueError(f'{name} source references do not resolve uniquely')
                if state != 'unknown' and not refs:
                    raise ValueError(f'{name} supported/contradicted observations need source references')
        except (ValueError, TypeError) as exc:
            errors.append(f'{context}: {exc}')
    return errors


def _evaluation(observations: dict, action: str) -> dict:
    criteria = []
    for name in ACTIONS[action]['criteria']:
        observation = observations.get(name, {'state': 'unknown', 'basis': 'Not measured or not supplied.', 'source_ids': []})
        criteria.append({'criterion': name, 'label': CRITERIA[name][0], **observation})
    counts = {state: sum(row['state'] == state for row in criteria) for state in ('supported', 'contradicted', 'unknown')}
    unresolved = [row for row in criteria if row['state'] != 'supported']
    next_row = next((row for row in unresolved if row['state'] == 'contradicted'), unresolved[0] if unresolved else criteria[0])
    if unresolved:
        outcomes = ('A supported result adds one supported criterion; a contradicted or unresolved result adds none. '
                    'Recompute the displayed count and order; a contradiction still needs explicit resolution before advancing the experiment.')
    else:
        outcomes = ('Replicate the support in the intended context. Confirmation preserves the count; a contradicted or unresolved result removes one supported criterion and changes the evidence order accordingly.')
    return {'criteria': criteria, 'supported': counts['supported'], 'contradicted': counts['contradicted'], 'missing': counts['unknown'],
            'next_measurement': CRITERIA[next_row['criterion']][1], 'decision_sensitivity': outcomes}


def build_action_comparison(targets: Any, target_hrefs: dict[str, str] | None = None) -> dict:
    errors = validate_action_evidence(targets)
    if errors:
        raise ValueError('\n'.join(errors))
    records = []
    for target in _rows(targets):
        identifier = target['target_id']
        evidence = target.get('action_evidence', {})
        href = (target_hrefs or {}).get(identifier)
        if href is not None and (not isinstance(href, str) or not re.fullmatch(r'[A-Za-z0-9_-]+\.html(?:#[A-Za-z0-9_.:-]+)?', href)):
            raise ValueError('target links must be report-local HTML filenames')
        records.append({'target_id': identifier, 'name': str(target.get('preferred_name', identifier)), 'href': href,
                        'sources': evidence.get('sources', []), 'evaluations': {action: _evaluation(evidence.get('observations', {}), action) for action in ACTIONS}})
    return {'schema_version': 'codex-surface-action-comparison/v0.1', 'actions': ACTIONS, 'order_rule': ORDER_RULE, 'caveat': CAVEAT, 'records': records}


def render_action_comparison(targets: Any, target_hrefs: dict[str, str] | None = None) -> str:
    """Return the comparison section; the report wrapper loads the two assets."""
    data = build_action_comparison(targets, target_hrefs)
    payload = html.escape(json.dumps(data, ensure_ascii=True, separators=(',', ':')), quote=True)
    return ('<section class="action-comparison" data-action-comparison="' + payload + '">'
            '<h2>Compare the evidence for a molecular action</h2>'
            '<p>' + html.escape(CAVEAT) + '</p><p class="action-order-rule">' + html.escape(ORDER_RULE) + '</p>'
            '<div class="action-controls"><label>Intended action <select data-action-select>'
            + ''.join('<option value="' + key + '">' + value['label'] + '</option>' for key, value in ACTIONS.items())
            + '</select></label><button type="button" data-action-csv>Download comparison CSV</button>'
            '<button type="button" data-action-copy>Copy selected request</button></div>'
            '<p data-action-summary role="status" aria-live="polite"></p><div data-action-rows></div>'
            '<label>Portable request (select and copy if clipboard is unavailable)'
            '<textarea data-action-request rows="8" readonly></textarea></label>'
            '<noscript>Enable JavaScript to select targets, compare actions, and export the comparison. The input target records retain the source evidence.</noscript></section>')
