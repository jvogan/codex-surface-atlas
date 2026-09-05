"""Shared run scoping for atlas validation and report generation."""

import re


def screening_role(record):
    """Read an explicit role; use only role-valued legacy status strings."""
    for key in ('screen_role', 'control_role'):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return re.sub(r'[\s_]+', '-', value.strip().casefold())
    value = record.get('control_status')
    if isinstance(value, str):
        role = re.sub(r'[\s_]+', '-', value.strip().casefold())
        if role in {'control', 'positive-control', 'negative-control', 'reference-control', 'reference'}:
            return role
    return 'not-recorded'


def screening_role_group(record):
    role = screening_role(record)
    if role == 'prospective':
        return 'prospective'
    if {'control', 'reference'} & set(role.split('-')):
        return 'control'
    return 'other'

def screening_run_contexts(metadata, records):
    """Resolve optional run metadata without assigning contexts across runs."""
    metadata = metadata or {}
    if 'source_run' in metadata and 'source_runs' in metadata:
        raise ValueError('screening-results.json: use source_run or source_runs, not both')
    runs = [metadata['source_run']] if 'source_run' in metadata else metadata.get('source_runs', [])
    if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
        raise ValueError('screening-results.json: source runs must be objects')
    if 'source_runs' in metadata and not runs:
        raise ValueError('screening-results.json: source_runs must not be empty')
    if 'confirmation_context' in metadata and 'confirmation_contexts' in metadata:
        raise ValueError('screening-results.json: use confirmation_context or confirmation_contexts, not both')
    contexts = metadata.get('confirmation_contexts', [])
    if not isinstance(contexts, list) or any(not isinstance(context, dict) for context in contexts):
        raise ValueError('screening-results.json: confirmation_contexts must contain objects')
    contexts = list(contexts)
    by_run = {}
    for run in runs:
        run_id = run.get('run_id')
        if not isinstance(run_id, str) or not run_id.strip() or run_id != run_id.strip() or run_id in by_run:
            raise ValueError('screening-results.json: source run IDs must be non-empty and unique')
        by_run[run_id] = {'source': run, 'confirmations': []}
    if metadata.get('confirmation_context') is not None:
        context = metadata['confirmation_context']
        if not isinstance(context, dict) or len(runs) != 1:
            raise ValueError('screening-results.json: confirmation_context requires one source run')
        contexts.append({'run_id': runs[0]['run_id'], **context})
    for context in contexts:
        run_id = context.get('run_id')
        if not isinstance(run_id, str) or run_id not in by_run:
            raise ValueError('screening-results.json: confirmation context must reference a source run')
        source_screen = by_run[run_id]['source'].get('screen_id')
        if source_screen is not None and context.get('screen_id', source_screen) != source_screen:
            raise ValueError('screening-results.json: confirmation screen_id does not match its source run')
        by_run[run_id]['confirmations'].append(context)
    if runs:
        for record in records:
            if not isinstance(record.get('run_id'), str) or record['run_id'] not in by_run:
                raise ValueError('screening-results.json: each record must reference a source run')
    return by_run
