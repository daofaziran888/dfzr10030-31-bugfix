"""采集日志业务规则：状态流转、字段校验与筛选口径都收在这里。

终态边界规则（修复「已处理后又被忽略覆盖」问题）：
* 未处理、处理中为非终态；已处理、已忽略为终态，二者互斥且只能落版一次。
* 终态动作统一委托 ``terminal_ledger_service`` 归并，每条日志只保留一个终态版本，
  被拒绝的动作在终态台账里留痕，处理证据与原摘要不丢失。
* 异常标记随终态版本冻结，忽略动作不能把已处理日志改成无告警，监控数量不再反复变化。
"""
from __future__ import annotations

from typing import Any

from app.services.terminal_ledger import (
    TERMINAL_ACTIONS,
    TERMINAL_STATUS,
    terminal_ledger_service,
)
from app.store import store

MODULE = "log_viewer"
LIST_FIELDS = ["日志编号", "关联任务", "日志级别", "记录时间", "日志内容", "错误堆栈", "处理状态", "处理人"]
REQUIRED_FIELDS = ["日志编号", "关联任务", "日志级别"]
STATUS_ORDER = ["未处理", "处理中", "已处理", "已忽略"]
ACTION_RULES = {"开始处理": "处理中", "标记已处理": "已处理", "忽略日志": "已忽略"}
NEGATIVE_ACTIONS = ["忽略日志"]
DEFAULT_OPERATOR = "值班管理员"


class LogViewerService:
    def list_entries(
        self,
        *,
        filters: dict[str, str] | None = None,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        terminal_ledger_service.bootstrap()
        rows = store.rows(MODULE)
        for field, expected in (filters or {}).items():
            rows = [row for row in rows if expected.casefold() in str(row.get(field, "")).casefold()]
        if keyword:
            rows = [row for row in rows if keyword.casefold() in str(row.get("日志编号", "")).casefold()]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = (page - 1) * size
        page_rows = [self._with_terminal_view(row) for row in rows[start:start + size]]
        return page_rows, total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        terminal_ledger_service.bootstrap()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._with_terminal_view(entry)

    def _with_terminal_view(self, entry: dict[str, Any]) -> dict[str, Any]:
        """列表/详情统一附带终态视图：唯一终态、版本、负责人、被拒绝动作。"""
        view = dict(entry)
        terminal = terminal_ledger_service.find_terminal(int(entry["id"]))
        if terminal is None:
            view["terminal"] = None
            view["终态版本"] = "—"
            return view
        view["terminal"] = {
            "terminal_status": terminal["terminal_status"],
            "version": terminal["version"],
            "owner": terminal["owner"],
            "in_exception_zone": terminal["in_exception_zone"],
            "rejected_actions": list(terminal.get("rejected_actions", [])),
            "created_at": terminal["created_at"],
            "summary": terminal["summary"],
        }
        view["终态版本"] = f"v{terminal['version']}·{terminal['terminal_status']}"
        return view

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in LIST_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        operator: str | None = None,
        client_token: str | None = None,
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """执行日志动作，返回 ``(条目, message, accepted)``。

        终态边界上的拒绝不会抛异常也不会改状态，调用方按 ok=False 呈现给操作人。
        """
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"日志条目 {entry_id} 不存在或已归档", False
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于采集日志可执行范围", False
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里", False

        actor = (operator or entry.get("处理人") or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR

        if action in TERMINAL_ACTIONS:
            record, accepted, message = terminal_ledger_service.submit_terminal_action(
                entry, action=action, operator=actor, client_token=client_token,
            )
            if accepted:
                # 版本处理与异常标记落在同一份终态版本上，之后不再被后续动作改写。
                entry["status"] = record["terminal_status"]
                entry["pending"] = False
                entry["abnormal"] = record["in_exception_zone"]
                entry["处理人"] = actor
            return self._with_terminal_view(entry), message, accepted

        # 非终态动作（开始处理）：已落终态的日志同样不允许回退。
        terminal = terminal_ledger_service.find_terminal(entry_id)
        if terminal is not None:
            terminal.setdefault("rejected_actions", []).append({
                "action": action,
                "target_status": target,
                "operator": actor,
                "reason": "终态边界拒绝",
                "client_token": (client_token or "").strip() or "anon",
                "rejected_at": terminal_ledger_service.now_text(),
            })
            return (
                self._with_terminal_view(entry),
                f"日志 {entry_id} 已存在终态「{terminal['terminal_status']}」，"
                f"动作「{action}」会回退终态边界，已拒绝",
                False,
            )
        if entry.get("status") == target:
            return self._with_terminal_view(entry), f"日志 {entry_id} 已处于「{target}」，重复动作被拒绝", False
        entry["status"] = target
        entry["pending"] = True
        return self._with_terminal_view(entry), f"日志条目已{action}", True

    # ---- 终态台账代理：路由层仍只面向本服务取数 --------------------------
    def list_terminal_ledger(self, *, status: str | None = None,
                             abnormal_only: bool = False) -> list[dict[str, Any]]:
        return terminal_ledger_service.list_terminal(status=status, abnormal_only=abnormal_only)

    def get_terminal_ledger(self, entry_id: int) -> dict[str, Any] | None:
        return terminal_ledger_service.get_terminal_view(entry_id)
