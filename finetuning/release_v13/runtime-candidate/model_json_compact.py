"""NFC-safe JSON preserving stable text around non-normalized substrings.

No content is summarized, normalized or removed. ASCII starts separate chunks;
any unusual cross-boundary normalization falls back to full ASCII escaping.
"""
import json
import re
import unicodedata

_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_CHUNKS = re.compile(r'[\x00-\x7f][^\x00-\x7f]*|[^\x00-\x7f]+')


def dumps(value, **kwargs):
    kwargs['ensure_ascii'] = False
    text = json.dumps(value, **kwargs)
    if unicodedata.is_normalized('NFC', text):
        return text

    def preserve(match):
        token = match.group()
        if unicodedata.is_normalized('NFC', token):
            return token
        decoded = json.loads(token)
        parts = [json.dumps(chunk, ensure_ascii=not unicodedata.is_normalized('NFC', chunk))[1:-1]
                 for chunk in _CHUNKS.findall(decoded)]
        encoded = '"' + ''.join(parts) + '"'
        if not unicodedata.is_normalized('NFC', encoded):
            return json.dumps(decoded, ensure_ascii=True)
        return encoded

    return _STRING.sub(preserve, text)
