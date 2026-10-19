"""Join interpreted artifact requirements to trusted historical observations.

No I/O, user-intent inference or whole-task verdict. This is an evidence view,
not a replacement for checking operation constraints, semantic quality and
delivery. A recorded observation is never advertised as current disk state.
"""
import importlib.util
from pathlib import Path, PureWindowsPath
import re

from text_reader import completed_file_contents


def _load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


intent = _load('artifact_intent_contract_v2')
relation = _load('exact_text_relation')


def _trusted(item):
    return (item.get('ok') is True and item.get('verified') is True
            and not (item.get('evidence') or {}).get('condition_skipped'))


def catalog_from_history(history):
    """Use only handler-returned paths and their corresponding request aliases.

    Contents, success criteria and expected answers are absent from the catalog.
    In particular an unobserved destination is not invented from a source path.
    """
    paths = {}

    def add(path, alias):
        if not isinstance(path, str) or not path:
            return
        aliases = paths.setdefault(path, [])
        if isinstance(alias, str) and alias and alias not in aliases:
            aliases.append(alias)

    for item in history:
        if not _trusted(item):
            continue
        tool, args = item.get('tool'), item.get('args') or {}
        output, evidence = item.get('output'), item.get('evidence') or {}
        if tool == 'READ_TEXT_FILE':
            add(evidence.get('path'), args.get('path'))
        elif tool == 'WRITE_TEXT_FILE' and isinstance(output, dict):
            add(output.get('path'), args.get('path'))
        elif tool == 'COPY_FILE_VERIFIED' and isinstance(output, dict):
            if output.get('source_read') is True:
                add(output.get('source'), args.get('source'))
            add(output.get('destination'), args.get('destination'))
    return [{'file_id': f'f{i}', 'observed_path': path,
             'filename': PureWindowsPath(path).name, 'request_paths': aliases}
            for i, (path, aliases) in enumerate(paths.items(), 1)]


def build(value, prompt, history):
    catalog = catalog_from_history(history)
    bound = intent.bind(value, prompt, catalog)
    paths = {row['file_id']: row['observed_path'] for row in catalog}
    aliases = {}
    for row in catalog:
        for alias in [row['observed_path'], *row['request_paths']]:
            aliases.setdefault(alias, set()).add(row['observed_path'])
    # Rebuild from handler records, never trust model-supplied assembled contents.
    contents = completed_file_contents(history)
    writes, copies, deliveries, unknown = [], [], [], []
    known_read_only = {'READ_TEXT_FILE', 'PATH_INFO', 'LIST_DIRECTORY', 'MODEL_GENERATE',
                       'FINAL_RESPONSE', 'CONDITION_SKIP'}
    for index, item in enumerate(history, 1):
        tool = item.get('tool')
        output, args = item.get('output'), item.get('args') or {}
        if tool not in known_read_only | {'COPY_FILE_VERIFIED', 'WRITE_TEXT_FILE', 'MAKE_DIRECTORY'}:
            # An unclassified tool (including a failed shell action) may change files.
            unknown.append(index)
        if not _trusted(item):
            continue
        if tool == 'FINAL_RESPONSE' and isinstance(output, str):
            deliveries.append({'sequence_index': index, 'text': output})
        if tool == 'WRITE_TEXT_FILE' and isinstance(output, dict) and isinstance(output.get('path'), str):
            writes.append({'sequence_index': index, 'path': output['path'],
                           'exclusive_creation': args.get('overwrite', False) is False})
        if tool == 'COPY_FILE_VERIFIED' and isinstance(output, dict):
            if (all(output.get(k) is True for k in ('copied', 'source_read', 'content_verified', 'destination_readback_verified'))
                    and output.get('skipped_existing') is False
                    and all(isinstance(output.get(k), str) and output[k] for k in ('source', 'destination'))
                    and type(output.get('bytes')) is int and output['bytes'] >= 0
                    and isinstance(output.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', output['sha256'])):
                copies.append({'sequence_index': index, 'source': output['source'],
                               'destination': output['destination'], 'bytes': output['bytes'],
                               'sha256': output['sha256'], 'exclusive_creation': True,
                               'source_read_and_destination_byte_readback_verified': True})
    artifacts = []
    for item in bound['artifacts']:
        sources = [paths[i] for i in item['source_file_ids']]
        target = paths.get(item['destination_file_id'])
        artifact = {**item, 'source_paths': sources, 'destination_path': target,
                    'content_relation': {'status': 'unknown'},
                    'destination_creation_observations': [w for w in writes if w['path'] == target],
                    'copy_observations': [c for c in copies if c['destination'] == target],
                    'source_write_observations': [w for w in writes if w['path'] in sources],
                    'source_copy_destination_observations': [c for c in copies if c['destination'] in sources]}
        if item['kind'] == 'semantic_generation':
            artifact['content_relation'] = {'status': 'semantic_review_required',
                                            'destination_full_text_observed': target in contents}
        elif target is None:
            artifact['content_relation']['reason'] = 'Requested destination has no bound observation.'
        else:
            candidates = [c for c in copies if item['kind'] == 'exact_copy'
                          and c['source'] == sources[0] and c['destination'] == target]
            if candidates:
                last = candidates[-1]
                artifact['content_relation'] = {'status': 'byte_copy_observed',
                                                'evidence_sequence_indices': [last['sequence_index']],
                                                'sha256': last['sha256'], 'bytes': last['bytes']}
            elif all(p in contents for p in [*sources, target]):
                comparison = relation.from_verified_files(contents, sources, target)
                indices = sorted({s['sequence_index'] for p in [*sources, target]
                                  for s in contents[p]['source_segments']})
                artifact['content_relation'] = {'status': 'text_equal' if comparison['text_equal'] else 'text_different',
                                                'evidence_sequence_indices': indices, 'comparison': comparison}
            else:
                artifact['content_relation']['reason'] = 'Complete source/target text or matching verified byte copy is missing.'
        # Provide chronology explicitly without inventing a disk-freshness guarantee.
        indices = artifact['content_relation'].get('evidence_sequence_indices', [])
        if indices:
            end = max(indices)
            involved = [*sources, target]
            later = []
            for i, event in enumerate(history, 1):
                if i <= end or event.get('tool') not in ('WRITE_TEXT_FILE', 'COPY_FILE_VERIFIED', 'READ_TEXT_FILE'):
                    continue
                args = event.get('args') or {}
                output = event.get('output') if isinstance(event.get('output'), dict) else {}
                names = [args.get('path'), args.get('source'), args.get('destination'),
                         output.get('path'), output.get('source'), output.get('destination'),
                         (event.get('evidence') or {}).get('path')]
                if any(isinstance(name, str) and aliases.get(name, set()).intersection(involved) for name in names):
                    later.append(i)
            artifact['later_file_actions'] = later
            artifact['later_unclassified_actions'] = [i for i in unknown if i > end]
        artifacts.append(artifact)
    return {'request_sha256': bound['request_sha256'], 'artifacts': artifacts,
            'verified_response_observations': deliveries, 'unclassified_action_indices': unknown,
            'whole_task_completion_inferred': False,
            'scope': 'Historical evidence for interpreted artifact requirements. Check original intent, branch conditions, preservation, later actions, semantic quality and delivery independently. Empty artifacts, equal text or a successful copy alone do not establish whole-task completion or current disk state.'}
