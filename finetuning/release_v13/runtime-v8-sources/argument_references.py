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


def validate_file_text_sources(plan, history=()):
    """Check anchor tool types before dispatch, without reading or guessing text.

    A planned READ may still fail, be skipped, or return a partial segment.
    Runtime file_text_from_step remains responsible for verified full coverage
    and version identity. Incomplete historical reads may be completed by a
    preceding continuation in this plan; do not reject those here.
    """
    pattern = re.compile(r'\{\{step:(\d+)\.(output|file_text)\}\}')
    sources = {}
    for item in history:
        if type(item.get('step_id')) is int:
            sources.setdefault(item['step_id'], []).append(item.get('tool'))

    def anchors(value):
        if isinstance(value, dict):
            if set(value) == {'$literal'}:
                return
            for child in value.values():
                yield from anchors(child)
        elif isinstance(value, list):
            for child in value:
                yield from anchors(child)
        elif isinstance(value, str):
            for match in pattern.finditer(value):
                if match.group(2) == 'file_text':
                    yield int(match.group(1))

    for step in plan.steps:
        for anchor in anchors(step.args):
            tools = sources.get(anchor, [])
            if tools != ['READ_TEXT_FILE']:
                raise ValueError(
                    f'步驟 {step.id} 的 {{{{step:{anchor}.file_text}}}} 無法使用：'
                    f'引用來源為 {tools}；全文引用只能指向前面的唯一 READ_TEXT_FILE 步驟。'
                    '請使用實際讀取來源的步驟編號；寫入回報或生成文字不是已讀取的檔案全文。'
                    '仍須保留使用者指定的原文、對象與必要步驟。'
                )
        sources.setdefault(step.id, []).append(step.tool)
