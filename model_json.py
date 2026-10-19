"""Lossless JSON text for models whose tokenizer applies Unicode NFC.

Escape only JSON string tokens that NFC would change. json.loads restores the
original code points; ordinary Traditional Chinese stays readable. This does
not normalize user data or promise that a model will reproduce it correctly.
"""
import json
import re
import unicodedata

_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def dumps(value, **kwargs):
    kwargs['ensure_ascii'] = False
    text = json.dumps(value, **kwargs)
    if unicodedata.is_normalized('NFC', text):
        return text

    def preserve(match):
        token = match.group()
        if unicodedata.is_normalized('NFC', token):
            return token
        return json.dumps(json.loads(token), ensure_ascii=True)

    return _STRING.sub(preserve, text)
