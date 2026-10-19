"""Compute a declared text relation; do not infer user intent or completion."""
from itertools import chain, zip_longest


def compare(source_texts, target_text):
    if not isinstance(source_texts, (list, tuple)) or not source_texts:
        raise ValueError('At least one explicitly ordered source is required')
    if not all(isinstance(text, str) for text in source_texts) or not isinstance(target_text, str):
        raise TypeError('Only actual decoded text can be compared')
    missing = object()
    difference = None
    for index, (left, right) in enumerate(zip_longest(chain.from_iterable(source_texts), target_text, fillvalue=missing)):
        if left != right:
            difference = {'character_index': index,
                          'source_character': None if left is missing else left,
                          'target_character': None if right is missing else right}
            break
    return {'text_equal': difference is None, 'source_count': len(source_texts),
            'source_total_chars': sum(len(text) for text in source_texts),
            'target_total_chars': len(target_text), 'first_difference': difference,
            'scope': 'Exact decoded text concatenation in supplied order, with no normalization or separator. Does not prove byte encoding, correct source selection, user intent, or whole-task completion.'}


def from_verified_files(file_contents, source_paths, target_path):
    if not isinstance(source_paths, list) or not source_paths or not all(isinstance(p, str) for p in source_paths):
        raise ValueError('Explicit ordered source paths are required')
    if not isinstance(target_path, str):
        raise TypeError('Target path must be a string')
    # Unknown files/partial unassembled reads must not become empty strings.
    records = [file_contents[path] for path in [*source_paths, target_path]]
    texts = []
    for record in records:
        text = record['text']
        if not isinstance(text, str) or type(record['total_chars']) is not int or len(text) != record['total_chars']:
            raise ValueError('Invalid complete text assembly')
        texts.append(text)
    return {'source_paths': list(source_paths), 'target_path': target_path,
            **compare(texts[:-1], texts[-1])}
