"""采集监控 分析看板接口：汇总指标、参数运行与结果导出。"""
from __future__ import annotations

import csv
import io
import random
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, CheckResultPayload, EntryPayload
from app.services.monitor import MonitorService

router = APIRouter(prefix="/api/monitor", tags=["采集监控"])
service = MonitorService()
LIST_FIELDS = ["面板编号", "采集源总数", "今日采集量", "成功率", "平均延迟", "失败重试", "异常告警", "更新时间"]
STATUSES = ["正常", "预警", "告警"]


def csv_cell(value: Any) -> str:
    text = str(value) if value is not None else ""
    if text and text[0] in "=+-@":
        text = "'" + text
    return '"' + text.replace('"', '""') + '"'


@router.get("/summary")
def get_summary() -> dict[str, Any]:
    # 异常记录改为按终态日志台账统计：终态版本冻结后数量不再随后续忽略动作来回变化。
    terminal_stats = service.terminal_stats()
    return {"metrics": [
        {"label": "覆盖数据源", "value": random.randint(12, 45), "trend": random.randint(-12, 25)},
        {"label": "最新指标值", "value": round(random.uniform(0.72, 0.99), 3), "trend": random.randint(-8, 15)},
        {"label": "异常记录", "value": terminal_stats["exception_count"], "trend": -random.randint(1, 10)},
    ], "terminal_stats": terminal_stats}


@router.get("/terminal-ledger")
def get_terminal_ledger(
    status: str | None = Query(default=None, description="已处理 / 已忽略"),
    abnormal_only: bool = Query(default=False),
) -> dict[str, Any]:
    """监控分析服务读取的终态日志条目数据台账（来自采集日志服务）。"""
    items = service.terminal_ledger(status=status, abnormal_only=abnormal_only)
    return {"items": items, "stats": service.terminal_stats()}


@router.get("/pending-review")
def get_pending_review(
    review_status: str | None = Query(default=None, description="待复核 / 已复核"),
) -> dict[str, Any]:
    """终态台账同步落到待复核台账后的复核列表，附空态原因与异常区条目。"""
    items = service.pending_review(review_status=review_status)
    stats = service.terminal_stats()
    empty_reason = "" if items else "暂无待复核数据：终态日志台账尚未产生条目，或全部条目均已复核"
    return {"items": items, "stats": stats, "empty_reason": empty_reason}


@router.post("/pending-review/{log_id}/check", response_model=ActionResult)
def write_check_result(log_id: int, payload: CheckResultPayload) -> ActionResult:
    """监控分析服务写回核对结果；同窗口重复核对只保留第一份结果，重复请求被拒绝。"""
    result = payload.result.strip()
    if not result:
        return ActionResult(ok=False, message="核对结果不能为空")
    item, message, accepted = service.write_check_result(log_id, result=result, reviewer=payload.reviewer)
    if item is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=accepted, message=message, entry=item)


@router.get("")
def list_results() -> dict[str, Any]:
    return {"items": service.list_results()}


@router.post("/run")
def run_analysis(payload: EntryPayload) -> dict[str, Any]:
    results = service.run_analysis(payload.values)
    return {"items": results}


@router.get("/export")
def export_entries() -> StreamingResponse:
    items = service.list_results()
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    all_keys = ["id"]
    if items:
        all_keys = list(items[0].keys())
    writer.writerow(all_keys)
    for item in items:
        writer.writerow([csv_cell(item.get(k, "")) for k in all_keys])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": "attachment; filename=monitor.csv"})


@router.get("/{entry_id}")
def get_entry(entry_id: int) -> dict:
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"监控面板 {entry_id} 不存在")
    return entry
