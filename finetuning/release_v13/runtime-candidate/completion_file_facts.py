"""Derived comparisons of observed files; never an overall completion verdict.

No file I/O, task interpretation, model output, or assumed source/destination.
The caller supplies the same validated whole-file assemblies used by its
existing completion check. Facts describe historical observations, not current
disk state or proof that the user's intended transformation was correct.
"""
from itertools import combinations
import re


def build(file_contents, history):
    files = []
    for path, record in file_contents.items():
        text, digest, segments = record['text'], record['sha256'], record['source_segments']
        if (not isinstance(path, str) or not isinstance(text, str)
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
                or type(record['total_chars']) is not int or len(text) != record['total_chars']
                or not segments or any(type(s.get('sequence_index')) is not int
                                       or not 1 <= s['sequence_index'] <= len(history) for s in segments)):
            raise ValueError('Invalid verified file assembly for comparison')
        files.append((path, record))
    pairs = []
    for (left_path, left), (right_path, right) in combinations(files, 2):
        pairs.append({'left_path': left_path, 'right_path': right_path,
                      'observed_text_identical': left['text'] == right['text'],
                      'observed_sha256_identical': left['sha256'] == right['sha256'],
                      'left_chars': len(left['text']), 'right_chars': len(right['text'])})
    writes = []
    copies = []
    for index, item in enumerate(history, 1):
        evidence = item.get('evidence') or {}
        if item.get('ok') is not True or item.get('verified') is not True or evidence.get('condition_skipped'):
            continue
        output = item.get('output')
        if item.get('tool') == 'COPY_FILE_VERIFIED' and isinstance(output, dict):
            if (output.get('copied') is True and output.get('skipped_existing') is False
                    and output.get('source_read') is True and output.get('content_verified') is True
                    and output.get('destination_readback_verified') is True):
                copies.append({'sequence_index': index, 'step_id': item.get('step_id'),
                               'operation_result': 'source_read_and_byte_copy_and_destination_readback_verified',
                               'source': output.get('source'), 'destination': output.get('destination'),
                               'bytes': output.get('bytes'), 'sha256': output.get('sha256'),
                               'whole_task_completion_inferred': False})
        if item.get('tool') != 'WRITE_TEXT_FILE' or not isinstance(output, dict):
            continue
        body = item.get('args', {}).get('content')
        if not isinstance(body, str):
            continue
        destination = output.get('path')
        if destination not in file_contents:
            continue
        observed = file_contents[destination]
        read_indices = [s['sequence_index'] for s in observed['source_segments']]
        if min(read_indices) <= index:
            continue  # A pre-write read cannot verify the subsequent write.
        writes.append({'write_sequence_index': index, 'write_step_id': item.get('step_id'),
                       'destination': destination, 'read_sequence_indices': read_indices,
                       'written_text_equals_observed_readback': body == observed['text'],
                       'written_chars': len(body), 'readback_chars': len(observed['text']),
                       'requested_transformation_correctness_inferred': False})
    return {'scope': 'Comparisons of supplied verified historical observations only. Equality does not establish correct targets, ordering, user-requested transformation, absence of later changes, or whole-task completion.',
            'file_pairs': pairs, 'write_readback_comparisons': writes, 'verified_copy_observations': copies}
