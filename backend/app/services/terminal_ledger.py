"""终态日志条目数据台账：按终态边界归并日志的处理/忽略动作。

背景：旧实现允许日志在已处理之后继续执行忽略动作，终态被覆盖、异常统计来回变化。
本模块把「处理状态记录」归并成不可变的终态版本：

* 已处理、已忽略同为终态；一条日志在任一方向上落版后即关闭边界，
  之后到达的跨终态动作（以及同终态重复动作）一律拒绝，拒绝记录作为证据保留。
* 默认取舍为「已处理终态优先并拒绝忽略」：处理完成成为最终可见状态，
  忽略请求进入被拒绝动作列表，已处理证据不丢失。
* 同窗口并发由进程内锁串行化，同一 client_token 的重复提交只产生一份结果。
* 异常标记（in_exception_zone）在终态版本落版时冻结，后续动作不得改写，
  监控侧据此统计，异常数不再来回变化。
"""
from __future__ import annotations

import threading
import time
from typing import Any

from app.store import store

MODULE = "log_viewer"
LEDGER_TABLE = "terminal_log_ledger"
REVIEW_TABLE = "monitor_pending_review"

# 非终态 -> 终态的动作集合；终态之外的流转（开始处理）不参与终态边界。
TERMINAL_STATUS = ("已处理", "已忽略")
TERMINAL_ACTIONS = ("标记已处理", "忽略日志")
# 终态取舍规则：已处理优先并拒绝忽略。另一种「忽略终态优先并保留已处理证据」
# 同样满足一条日志只有一个终态版本，本平台固定采用前者，规则在此显式声明。
TERMINAL_PRIORITY = {"已处理": 1, "已忽略": 2}
# 无 client_token 时，同一日志同一动作在该窗口（秒）内的重复提交按重复拒绝处理。
IDEMPOTENT_WINDOW_SECONDS = 60.0


class TerminalLedgerService:
    """终态台账与待复核台账的唯一写入入口，采集日志与监控分析两个服务共用。"""

    def __init__(self) -> None:
        self._locks: dict[int, threading.RLock] = {}
        self._guard = threading.Lock()
        self._bootstrap_done = False

    # ---- 基础读取 -------------------------------------------------------
    def _lock_for(self, log_id: int) -> threading.RLock:
        with self._guard:
            lock = self._locks.get(log_id)
            if lock is None:
                lock = threading.RLock()
                self._locks[log_id] = lock
            return lock

    def _table(self, name: str) -> list[dict[str, Any]]:
        return store.rows(name)

    def bootstrap(self) -> None:
        """把种子数据里已经处于终态的日志补登为终态版本，仅执行一次。"""
        if self._bootstrap_done:
            return
        with self._guard:
            if self._bootstrap_done:
                return
            for entry in store.rows(MODULE):
                status = entry.get("status")
                if status in TERMINAL_STATUS:
                    log_id = int(entry["id"])
                    if self.find_terminal(log_id) is None:
                        in_exception_zone = status == "已忽略"
                        record = self._persist_terminal(
                            entry,
                            terminal_status=status,
                            action="标记已处理" if status == "已处理" else "忽略日志",
                            operator=entry.get("处理人") or "系统初始化",
                            client_token="seed-bootstrap",
                            in_exception_zone=in_exception_zone,
                        )
                        # 旧数据可能残留与终态不一致的异常标记，按终态版本统一口径。
                        entry["abnormal"] = in_exception_zone
                        entry["pending"] = False
                        # 监控分析服务对补登的终态版本同样同步落待复核台账。
                        self._sync_to_review(record)
                elif entry.get("abnormal"):
                    # 非终态日志尚未落版，异常统计不应提前计入。
                    entry["abnormal"] = False
            self._bootstrap_done = True

    def list_terminal(self, *, status: str | None = None,
                      abnormal_only: bool = False) -> list[dict[str, Any]]:
        self.bootstrap()
        rows = [self._public(row) for row in self._table(LEDGER_TABLE)]
        if status:
            rows = [row for row in rows if row["terminal_status"] == status]
        if abnormal_only:
            rows = [row for row in rows if row["in_exception_zone"]]
        rows.sort(key=lambda row: int(row["log_id"]))
        return rows

    def find_terminal(self, log_id: int) -> dict[str, Any] | None:
        """内部使用的原始终态记录（含幂等去重等内部字段），不直接出现在接口响应里。"""
        for row in self._table(LEDGER_TABLE):
            if int(row["log_id"]) == log_id:
                return row
        return None

    def get_terminal_view(self, log_id: int) -> dict[str, Any] | None:
        """对外只读视图：剥离下划线开头的内部字段。"""
        record = self.find_terminal(log_id)
        return self._public(record) if record is not None else None

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in record.items() if not key.startswith("_")}

    def now_text(self) -> str:
        """对外暴露的时间戳工具，避免其他服务直接依赖私有 _ts。"""
        return self._ts()

    # ---- 终态落版与边界拒绝 ---------------------------------------------
    def submit_terminal_action(
        self,
        entry: dict[str, Any],
        *,
        action: str,
        operator: str,
        client_token: str | None,
    ) -> tuple[dict[str, Any], bool, str]:
        """尝试把一条终态动作落到台账。

        返回 ``(终态条目, accepted, message)``：accepted=False 表示动作被终态
        边界拒绝（终态版本保持不变，拒绝动作留痕），调用方据此返回 ok=False。
        """
        self.bootstrap()
        log_id = int(entry["id"])
        target_status = "已处理" if action == "标记已处理" else "已忽略"
        with self._lock_for(log_id):
            existing = self.find_terminal(log_id)
            now = time.time()
            token = (client_token or "").strip() or f"anon:{log_id}:{action}"

            if existing is not None:
                # 同窗口并发 / 重复提交：相同动作只保留第一份结果。
                last = existing.get("_last_submit", {})
                same_window = (
                    last.get("token") == token
                    and now - float(last.get("at", 0.0)) < IDEMPOTENT_WINDOW_SECONDS
                )
                if existing["terminal_status"] == target_status:
                    reason = "重复拒绝"
                    message = (
                        f"日志 {log_id} 已处于终态「{target_status}」，"
                        "同窗口重复动作仅保留第一份结果"
                        if same_window
                        else f"日志 {log_id} 终态已落版为「{target_status}」，重复动作被拒绝"
                    )
                else:
                    reason = "终态边界拒绝"
                    message = (
                        f"日志 {log_id} 已存在终态版本「{existing['terminal_status']}」，"
                        f"按已处理优先规则拒绝「{action}」；处理证据已保留"
                    )
                existing.setdefault("rejected_actions", []).append({
                    "action": action,
                    "target_status": target_status,
                    "operator": operator,
                    "reason": reason,
                    "client_token": token,
                    "rejected_at": self._ts(now),
                })
                existing["_last_submit"] = {"token": token, "at": now}
                return existing, False, message

            # 首次终态落版：终态版本与异常标记同时冻结在同一份版本上。
            in_exception_zone = target_status == "已忽略"
            record = self._persist_terminal(
                entry,
                terminal_status=target_status,
                action=action,
                operator=operator,
                client_token=token,
                in_exception_zone=in_exception_zone,
                now=now,
            )
            # 监控分析服务同步消费终态台账，落到待复核台账。
            self._sync_to_review(record)
            return record, True, f"日志 {log_id} 终态已落版为「{target_status}」（版本 {record['version']}）"

    def _persist_terminal(
        self,
        entry: dict[str, Any],
        *,
        terminal_status: str,
        action: str,
        operator: str,
        client_token: str,
        in_exception_zone: bool,
        now: float | None = None,
    ) -> dict[str, Any]:
        now = time.time() if now is None else now
        rows = self._table(LEDGER_TABLE)
        record = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "log_id": int(entry["id"]),
            "日志编号": entry.get("日志编号"),
            "关联任务": entry.get("关联任务"),
            "日志级别": entry.get("日志级别"),
            "记录时间": entry.get("记录时间"),
            "summary": entry.get("日志内容"),          # 原摘要，落版后保留不变
            "错误堆栈": entry.get("错误堆栈"),
            "terminal_status": terminal_status,
            "version": 1,                               # 一条日志只允许一个终态版本
            "terminal_action": action,
            "owner": operator,
            "in_exception_zone": in_exception_zone,
            "evidence": [                               # 已完成的处理证据不丢失
                {
                    "action": action,
                    "status": terminal_status,
                    "operator": operator,
                    "client_token": client_token,
                    "at": self._ts(now),
                }
            ],
            "rejected_actions": [],
            "created_at": self._ts(now),
            "_last_submit": {"token": client_token, "at": now},
        }
        rows.append(record)
        return record

    # ---- 监控分析服务：待复核台账与核对结果 ------------------------------
    def _sync_to_review(self, record: dict[str, Any]) -> dict[str, Any]:
        rows = self._table(REVIEW_TABLE)
        item = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "ledger_id": record["id"],
            "log_id": record["log_id"],
            "日志编号": record["日志编号"],
            "关联任务": record["关联任务"],
            "terminal_status": record["terminal_status"],
            "version": record["version"],
            "owner": record["owner"],
            "in_exception_zone": record["in_exception_zone"],
            "review_status": "待复核",
            "check_result": None,
            "reviewer": None,
            "reviewed_at": None,
            "synced_at": record["created_at"],
        }
        rows.append(item)
        return item

    def list_pending_review(self, *, review_status: str | None = None) -> list[dict[str, Any]]:
        self.bootstrap()
        rows = [self._public(row) for row in self._table(REVIEW_TABLE)]
        if review_status:
            rows = [row for row in rows if row["review_status"] == review_status]
        rows.sort(key=lambda row: int(row["log_id"]))
        return rows

    def find_review_by_log(self, log_id: int) -> dict[str, Any] | None:
        for row in self._table(REVIEW_TABLE):
            if int(row["log_id"]) == log_id:
                return row
        return None

    def write_check_result(
        self, log_id: int, *, result: str, reviewer: str
    ) -> tuple[dict[str, Any] | None, str, bool]:
        """监控分析服务把核对结果写回待复核台账；重复核对按重复拒绝处理。

        返回 ``(条目, message, accepted)``。
        """
        self.bootstrap()
        with self._lock_for(log_id):
            item = self.find_review_by_log(log_id)
            if item is None:
                return None, f"日志 {log_id} 尚未产生终态版本，待复核台账没有对应条目", False
            if item["review_status"] != "待复核":
                return item, (
                    f"日志 {log_id} 的核对结果已为「{item['review_status']}」，"
                    "同窗口重复核对仅保留第一份结果"
                ), False
            item["review_status"] = "已复核"
            item["check_result"] = result
            item["reviewer"] = reviewer
            item["reviewed_at"] = self._ts()
            return item, f"日志 {log_id} 核对结果已写回：{result}", True

    # ---- 监控口径：按处理状态版本统计 ------------------------------------
    def terminal_stats(self) -> dict[str, Any]:
        self.bootstrap()
        rows = self._table(LEDGER_TABLE)
        processed = sum(1 for row in rows if row["terminal_status"] == "已处理")
        ignored = sum(1 for row in rows if row["terminal_status"] == "已忽略")
        exception = sum(1 for row in rows if row["in_exception_zone"])
        rejected = sum(len(row.get("rejected_actions", [])) for row in rows)
        review_rows = self._table(REVIEW_TABLE)
        return {
            "total_terminal": len(rows),
            "processed_count": processed,
            "ignored_count": ignored,
            "exception_count": exception,
            "rejected_action_count": rejected,
            "pending_review_count": sum(1 for row in review_rows if row["review_status"] == "待复核"),
            "reviewed_count": sum(1 for row in review_rows if row["review_status"] == "已复核"),
            # 空态说明：没有命中终态台账时前端据此解释原因，而不是展示裸空表。
            "empty_reason": "" if rows else "暂无终态日志：所有日志仍处于未处理/处理中，尚无终态版本落版",
        }

    @staticmethod
    def _ts(now: float | None = None) -> str:
        now = time.time() if now is None else now
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))


terminal_ledger_service = TerminalLedgerService()
