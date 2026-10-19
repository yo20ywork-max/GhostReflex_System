"""Known top-level boolean outputs for preflight condition type checking.

These describe possible successful results, not guaranteed keys or current
state. Runtime verification remains authoritative, including for unknown tools.
"""
from types import SimpleNamespace

from step_conditions import check_condition


BOOLEAN_FIELDS = {
    'PATH_INFO': ('exists', 'is_file', 'is_directory', 'is_symlink', 'content_read'),
    'COPY_FILE_VERIFIED': ('copied', 'skipped_existing', 'source_read', 'content_verified',
                           'destination_readback_verified', 'whole_task_verified',
                           'cancel_requested_after_commit'),
    'MAKE_DIRECTORY': (),
    'READ_TEXT_FILE': (),
    'WRITE_TEXT_FILE': (),
    'APPEND_TEXT_FILE': (),
    'MODEL_GENERATE': (),
    'TRANSLATE_TEXT': (),
}


def describe_catalog(catalog):
    """Keep original argument contracts; disclose only known result contracts."""
    return [{**entry, **({'when_boolean_fields': list(BOOLEAN_FIELDS[entry['name']])}
                        if entry['name'] in BOOLEAN_FIELDS else {})}
            for entry in catalog]


def validate_plan_conditions(plan, history=()):
    """Reject impossible predicates before any action; never rewrite a branch."""
    observed = {item['step_id']: item for item in history if type(item.get('step_id')) is int}
    previous_tools = {}
    for step in plan.steps:
        condition = step.when
        if condition is not None:
            source_id = condition['step_id']
            if source_id in observed:
                item = observed[source_id]
                result = SimpleNamespace(ok=item.get('ok'), verified=item.get('verified'),
                                         output=item.get('output'), evidence=item.get('evidence'))
                # Validate actual type and trust, but do not require the branch
                # to match: a legitimate false predicate must remain skippable.
                check_condition(condition, {source_id: result})
            elif source_id in previous_tools:
                tool = previous_tools[source_id]
                fields = BOOLEAN_FIELDS.get(tool)
                if fields is not None and condition['field'] not in fields:
                    raise ValueError(
                        f"步驟 {step.id} 的 when 無法使用 step:{source_id}（{tool}）的 "
                        f"{condition['field']!r}：該工具的頂層 boolean 欄位為 {list(fields)}。"
                        "不要把文字、檔案全文引用、位元組數或工具成功狀態當成不存在的欄位；"
                        "修正條件依據並保留使用者要求的分支，不可直接刪除必要條件。"
                    )
        previous_tools[step.id] = step.tool
