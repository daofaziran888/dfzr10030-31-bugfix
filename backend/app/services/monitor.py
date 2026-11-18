"""采集监控 分析看板服务：汇总指标、运行分析并生成模拟结果。

终态联动：监控分析服务同步消费「终态日志条目数据台账」，把每条终态日志落到
待复核台账，并在此写回核对结果；异常数按终态版本统计，已处理日志不会被随后的
忽略动作改成无告警，因此监控数量不再来回变化。
"""
from __future__ import annotations

import random
from typing import Any

from app.services.terminal_ledger import terminal_ledger_service
from app.store import store

MODULE = "monitor"
REQUIRED_FIELDS = ["面板编号", "采集源总数", "今日采集量"]
STATUS_ORDER = ["正常", "预警", "告警"]
ACTION_RULES = {"查看详情": "正常"}
NEGATIVE_ACTIONS = []
DEFAULT_REVIEWER = "监控分析服务"


class MonitorService:
    def list_results(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        results: list[dict] = []
        for row in rows:
            d = dict(row)
            d["指标值"] = round(random.uniform(0.65, 0.98), 3)
            d["对比基准"] = round(random.uniform(0.60, 0.92), 3)
            d["差异"] = round(d["指标值"] - d["对比基准"], 3)
            results.append(d)
        return results

    def run_analysis(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        count = int(params.get("样本范围", params.get("并行数量", "6")))
        results: list[dict[str, Any]] = []
        for i in range(count):
            results.append({
                "id": i + 1,
                "分组": f"分组{(i%3)+1}",
                "指标值": round(random.uniform(0.62, 1.02), 3),
                "对比基准": round(random.uniform(0.58, 0.95), 3),
                "差异": round(random.uniform(-0.2, 0.3), 3),
            })
        return results

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    # ---- 终态台账消费 ---------------------------------------------------
    def terminal_ledger(self, *, status: str | None = None,
                        abnormal_only: bool = False) -> list[dict[str, Any]]:
        """读取采集日志服务产出的终态日志条目数据台账。"""
        return terminal_ledger_service.list_terminal(
            status=status, abnormal_only=abnormal_only)

    def terminal_stats(self) -> dict[str, Any]:
        """按处理状态版本计算已处理、忽略与异常数量，口径与终态台账一致。"""
        return terminal_ledger_service.terminal_stats()

    def pending_review(self, *, review_status: str | None = None) -> list[dict[str, Any]]:
        return terminal_ledger_service.list_pending_review(review_status=review_status)

    def write_check_result(
        self, log_id: int, *, result: str, reviewer: str | None = None
    ) -> tuple[dict[str, Any] | None, str, bool]:
        actor = (reviewer or DEFAULT_REVIEWER).strip() or DEFAULT_REVIEWER
        return terminal_ledger_service.write_check_result(
            log_id, result=result, reviewer=actor)
