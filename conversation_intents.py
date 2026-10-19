"""Conservative handling of pure greetings, with no inferred desktop actions."""
import re


def greeting_reply(prompt):
    if not isinstance(prompt, str):
        return None
    if re.fullmatch(r'\s*(?:你好|您好|哈囉|哈啰|嗨|早安|午安|晚安|hello|hi)[!！。.?？～~\s]*', prompt, re.IGNORECASE):
        return '你好！有什麼需要我幫忙的？'
    return None
