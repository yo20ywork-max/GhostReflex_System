from __future__ import annotations

def fallback_blocked_plan(prompt: str, reason: str) -> TaskPlan:
    return TaskPlan(objective=prompt, assumptions=[], steps=[PlanStep(id=1, goal='回報未能產生可驗證的計畫', tool='BLOCKED', args={'reason': {'$literal': reason}, 'missing_capability': '本次尚未取得符合工具規格與實際觀察的計畫', 'suggested_next_action': '依上方具體錯誤檢查連線、模型回應或計畫內容；已有成功操作不應重做。'}, success_check='已明確回報阻塞原因', on_failure='stop', retries=0)], completion_criteria=['不偽裝成已完成。'], model='fallback')
