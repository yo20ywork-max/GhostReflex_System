"""Additional veto for a narrow, explicit Traditional Chinese reply directive.

This never proves task completion or synthesizes a success message. Unknown or
ambiguous grammar returns no contract and must retain the ordinary verifier.
Not installed in the frozen comparison runtime.
"""
from dataclasses import dataclass
import re

from completion_requirements import request_clauses


@dataclass(frozen=True)
class ReplyRequirement:
    text: str
    start: int
    end: int


_DIRECTIVE = re.compile(
    r'(?P<prefix>.*?)(?:請)?(?:只|僅)?(?:回覆|回答|告訴我)'
    r'\s*(?:「(?P<corner>[^「」]*)」|『(?P<double>[^『』]*)』)'
    r'\s*[。！？!?；;]?\s*', re.S)
_UNSAFE_PREFIX = re.compile(
    r'不要|不必|不用|不需|禁止|取消|勿|別|如果|假如|若|失敗|否則|例如|範例|示範|未|沒')
_NEGATIVE_REPLY = re.compile(r'(?:不要|不必|不用|不需|不能|不可以|不應|禁止|勿|別)\s*(?:再|只|任何文字|直接)?\s*(?:回覆|回答|告訴我)')


def _unquoted(text):
    """Remove literal interiors only for detecting contradictory directives."""
    return re.sub(r'「[^「」]*」|『[^『』]*』|"[^"\n]*"|`[^`]*`', '', text)


def explicit_reply_requirement(request):
    if not isinstance(request, str):
        return None
    try:
        clauses = request_clauses(request)
    except ValueError:
        return None
    nonempty = [c for c in clauses if c['text'].strip()]
    unquoted = _unquoted(request)
    # A condition in an earlier sentence can govern the final reply. This
    # grammar does not resolve branches, so it must not select the last branch.
    if (not nonempty or _NEGATIVE_REPLY.search(unquoted)
            or re.search(r'如果|假如|若|否則|只有|是否|的話|時|就', unquoted)
            or len(re.findall(r'回覆|回答|告訴我', unquoted)) != 1):
        return None
    # A unique reply directive remains binding when later clauses add work
    # constraints, e.g. do not repeat an already successful write. Quoted data
    # and branching/contradictory directives are still handled conservatively.
    candidates = [(clause, _DIRECTIVE.fullmatch(clause['text'].strip()))
                  for clause in nonempty]
    candidates = [(clause, match) for clause, match in candidates if match]
    if len(candidates) != 1:
        return None
    clause, match = candidates[0]
    suffix = _unquoted(request[clause['end']:])
    if re.search(r'取消|作廢|撤回|忽略|改成|改為|更正|當我沒說|算了|範例|示範|舉例|不是要求|不是指令|並非要求|並非指令|不用照做|不必照做', suffix):
        return None
    prefix = match['prefix'].strip()
    # Only direct replies or an explicit preceding completion condition. The
    # condition itself still needs the ordinary evidence checker.
    if prefix and (not prefix.endswith(('後', '後再', '才', '最後', '再'))
                   or _UNSAFE_PREFIX.search(_unquoted(prefix))):
        return None
    group = 'corner' if match['corner'] is not None else 'double'
    literal = match[group]
    if not literal:  # The current runtime cannot render an empty final message.
        return None
    leading = len(clause['text']) - len(clause['text'].lstrip())
    start = clause['start'] + leading + match.start(group)
    end = start + len(literal)
    assert request[start:end] == literal
    return ReplyRequirement(literal, start, end)


def reply_completion_veto(request, history):
    """Return an unmet response requirement, or None (never a success proof)."""
    required = explicit_reply_requirement(request)
    if required is None:
        return None
    last = next((row for row in reversed(history)
                 if row.get('tool') == 'FINAL_RESPONSE'), None)
    message = None
    if last is not None:
        if last.get('ok') is True and last.get('verified') is True:
            message = last.get('output')
        else:
            # A failed final-response attempt can change ctx.final_message;
            # do not claim that an older successful response will be rendered.
            message = object()
    if message is None and history:
        latest = next((row for row in reversed(history) if row.get('tool') != 'CONDITION_SKIP'), {})
        if (latest.get('tool') in {'MODEL_GENERATE', 'TRANSLATE_TEXT',
                                  'READ_TEXT_FILE', 'BROWSER_GET_TEXT', 'HTTP_GET'}
                and latest.get('ok') is True
                and latest.get('verified') is True
                and isinstance(latest.get('output'), str)):
            # The current runtime renders this exact string when no
            # explicit final response exists. Do not demand an extra tool call.
            message = latest['output']
    if message == required.text:
        return None
    return ('尚未提供原始需求指定的最後回覆：'
            + repr(required.text)
            + '。此項只核對回覆，不能代替前置工作與結果驗證；'
              '不得重做已成功的寫入或送出。')


def install_reply_completion_guard(planner_class):
    """Optional integration: can only veto an existing positive assessment."""
    original = planner_class.assess_completion
    if getattr(original, '_crossgen_explicit_reply_guard', False):
        return False

    def guarded(self, prompt, history):
        complete, reason = original(self, prompt, history)
        if complete is not True:
            return complete, reason
        veto = reply_completion_veto(prompt, history)
        return (False, veto) if veto else (complete, reason)

    guarded._crossgen_explicit_reply_guard = True
    planner_class.assess_completion = guarded
    return True
