from __future__ import annotations

def _execute_step(self, ctx: ExecutionContext, step: PlanStep) -> ToolResult:
    if getattr(step, 'when', None) is not None:
        from step_conditions import check_condition
        try:
            applies, proof = check_condition(step.when, ctx.step_results)
        except ValueError as exc:
            return ToolResult(False, error=f'條件無法判定，未派發動作：{exc}', terminal=step.on_failure not in ('replan', 'retry'))
        if not applies:
            write_event(ctx.settings, 'step_skipped', {'request_id': ctx.request_id, 'step_id': step.id, 'planned_tool': step.tool, **proof})
            return ToolResult(True, verified=True, evidence={'condition_skipped': True, **proof})
    spec = TOOL_REGISTRY[step.tool]
    try:
        resolved_args = resolve_references(step.args, ctx.step_results, getattr(ctx, 'history', []))
        if not isinstance(resolved_args, dict):
            return ToolResult(False, error='解析後 args 不是 object。')
        validate_tool_arguments(resolved_args, spec.parameters)
    except Exception as exc:
        return ToolResult(False, error=f'步驟輸出引用解析失敗：{exc}')
    mutation_tools = {'WRITE_TEXT_FILE', 'APPEND_TEXT_FILE', 'DOWNLOAD_FILE', 'TYPE_TEXT', 'WRITE_CLIPBOARD', 'HOTKEY', 'PRESS_KEY', 'MOUSE_CLICK', 'VISION_CLICK', 'BROWSER_CLICK', 'BROWSER_FILL', 'BROWSER_PRESS', 'RUN_PROCESS', 'RUN_SHELL', 'DELETE_PATH', 'GIT_PULL'}
    if getattr(ctx, 'replan_number', 0) and step.tool in mutation_tools:
        if any((item.get('ok') and item.get('tool') == step.tool and (item.get('args') == resolved_args) for item in ctx.history)):
            return ToolResult(False, error='重規劃要求重複已成功的相同操作，已停止此任務以避免重送或改做其他寫入；目前缺少可靠的完成判定。', terminal=True)
    if hasattr(ctx, 'resolved_arguments'):
        ctx.resolved_arguments[step.id] = json.loads(json.dumps(resolved_args, ensure_ascii=False, default=str))
    if not self._confirm_step(step, resolved_args):
        return ToolResult(False, error='使用者拒絕高風險步驟。', terminal=True)
    repeatable_reads = {'READ_TEXT_FILE', 'LIST_DIRECTORY', 'READ_CLIPBOARD', 'GET_ACTIVE_WINDOW', 'BROWSER_GET_TEXT', 'BROWSER_WAIT_FOR', 'ANALYZE_SCREEN', 'VERIFY_SCREEN'}
    attempts = 1 + (max(0, step.retries) if step.tool in repeatable_reads else 0)
    last_result = ToolResult(False, error='尚未執行。')
    for attempt in range(1, attempts + 1):
        event = getattr(ctx, 'cancel_event', None)
        if event is not None and event.is_set():
            return ToolResult(False, error='使用者已取消，未派發本次操作。', terminal=True)
        console_print(f'\n⚙️ [步驟 {step.id}/{step.tool}] {step.goal}｜嘗試 {attempt}/{attempts}')
        journal = getattr(getattr(ctx, 'runtime', None), 'journal', None)
        receipt = None
        if journal is not None:
            try:
                receipt = journal.begin(ctx.request_id, step.id, attempt, step.tool, step.goal, resolved_args)
            except Exception as exc:
                return ToolResult(False, error=f'無法保存操作紀錄，尚未派發此步驟：{exc}', terminal=True)
        try:
            result = spec.handler(ctx, **resolved_args)
            if not isinstance(result, ToolResult):
                result = ToolResult(True, output=result, verified=False)
        except TypeError as exc:
            result = ToolResult(False, error=f'工具參數錯誤：{exc}')
        except Exception as exc:
            result = ToolResult(False, error=f'工具未捕捉異常：{exc}')
        if journal is not None:
            try:
                journal.finish(receipt, {'ok': result.ok, 'verified': result.verified, 'output': result.output, 'error': result.error, 'terminal': result.terminal, 'evidence': result.evidence})
            except Exception as exc:
                return ToolResult(False, output=result.output, error=f'操作已嘗試，但無法保存結果；停止後續操作，需重新核對：{exc}', terminal=True)
        last_result = result
        console_print(f'   {('✅' if result.ok else '❌')} verified={result.verified}｜{result.short(1000)}')
        write_event(self.settings, 'tool_result', {'request_id': ctx.request_id, 'step_id': step.id, 'tool': step.tool, 'attempt': attempt, 'ok': result.ok, 'verified': result.verified, 'output': result.short(1200), 'error': result.error})
        if result.ok or result.terminal:
            break
        if attempt < attempts:
            time.sleep(min(2.0, 0.4 * attempt))
    return last_result
