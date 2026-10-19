"""Validate reserved step placeholders, with an explicit lossless literal form."""
import re

_PLACEHOLDER = re.compile(r'\{\{step:')


def referenced_ids(value, pattern):
    if isinstance(value, dict):
        if set(value) == {'$literal'}:
            return set()
        return set().union(*(referenced_ids(v, pattern) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(referenced_ids(v, pattern) for v in value))
    if not isinstance(value, str):
        return set()
    for item in _PLACEHOLDER.finditer(value):
        if pattern.match(value, item.start()) is None:
            raise ValueError('不支援的步驟輸出引用：' + value[item.start():item.start() + 80] + '。只支援 step:N.output 或 step:N.file_text；'
                             '若使用者要的是這段原文字面，請用 {"$literal":原文}，不能把錯誤引用寫進檔案。')
    return {int(match.group(1)) for match in pattern.finditer(value)}
