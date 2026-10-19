from __future__ import annotations

def _request_valid_plan(self, messages: list[dict[str, Any]], reserved_ids: Optional[set[int]]=None, observed_history: Optional[list[dict[str, Any]]]=None) -> TaskPlan:
    from model_json import dumps as model_json_dumps
    errors: list[str] = []
    request_schema = json.loads(json.dumps(self.schema))
    next_step_id = max(reserved_ids or {0}) + 1
    item_schema = request_schema.get('properties', {}).get('steps', {}).get('items', {})
    for branch in item_schema.get('oneOf', [item_schema]):
        id_schema = branch.get('properties', {}).get('id')
        if isinstance(id_schema, dict):
            id_schema['minimum'] = max(id_schema.get('minimum', 1), next_step_id)
    for candidate in self.settings.planner_models:
        attempt_messages = list(messages)
        for attempt in range(2):
            raw = None
            try:
                raw, used_model = self.gateway.chat_json(messages=attempt_messages, schema=request_schema, models=(candidate,))
                plan = validate_plan(raw, self.settings, used_model, reserved_ids)
                from tool_result_contracts import validate_plan_conditions
                validate_plan_conditions(plan, observed_history or [])
                from text_reader import validate_read_continuations
                validate_read_continuations(plan, observed_history or [])
                return plan
            except Exception as exc:
                errors.append(f'{candidate}: {exc}')
                previous = []
                attempt_messages = [*messages, *previous, {'role': 'user', 'content': '上次計畫未通過驗證，請修正後重新輸出完整 JSON。錯誤：' + str(exc)[:1200] + '。未知參數必須移除，不是只改變它的值；保留使用者指定的對象、原文與所有必要步驟' + f'。歷史已使用的 step id：{sorted(reserved_ids or ())}；新步驟從 {next_step_id} 起編號，引用歷史輸出仍保留原編號。'}]
    raise RuntimeError('沒有模型產生可驗證計畫：' + ' | '.join(errors[-8:]))
