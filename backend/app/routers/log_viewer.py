"""采集日志接口：维护日志条目，覆盖开始处理、标记已处理、忽略日志等动作。"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas import ActionPayload, ActionResult, PageResult
from app.services.log_viewer import LogViewerService

router = APIRouter(prefix="/api/log_viewer", tags=["采集日志"])

service = LogViewerService()

LIST_FIELDS = ["日志编号", "关联任务", "日志级别", "记录时间", "日志内容", "错误堆栈", "处理状态", "处理人"]
STATUSES = ["未处理", "处理中", "已处理", "已忽略"]


def query_filters(request: Request) -> dict[str, str]:
    """只接受当前模块声明过的字段，忽略分页等保留参数。"""
    return {
        key: value.strip()
        for key, value in request.query_params.items()
        if key in LIST_FIELDS and value.strip()
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    request: Request,
    keyword: str | None = Query(default=None, description="按日志编号检索"),
    status: str | None = Query(default=None, description="未处理、处理中、已处理、已忽略"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    """按页面字段、日志编号关键字与状态过滤采集日志列表。"""
    items, total = service.list_entries(
        filters=query_filters(request), keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries(
    request: Request,
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> StreamingResponse:
    """下载当前筛选条件下的 UTF-8 CSV；必须声明在 /{entry_id} 之前。"""
    items, _ = service.list_entries(
        filters=query_filters(request), keyword=keyword, status=status, page=1, size=1000000)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["id", *LIST_FIELDS, "status"])
    for item in items:
        row = []
        for value in [item.get("id"), *(item.get(field, "") for field in LIST_FIELDS), item.get("status", "")]:
            text = "" if value is None else str(value)
            row.append("'" + text if text.startswith(("=", "+", "-", "@")) else text)
        writer.writerow(row)
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="log_viewer.csv"'})


@router.get("/terminal-ledger", response_model=PageResult[dict])
def list_terminal_ledger(
    status: str | None = Query(default=None, description="按终态过滤：已处理、已忽略"),
    abnormal_only: bool = Query(default=False, description="仅看异常区条目"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
) -> PageResult[dict]:
    """终态日志条目数据台账：每条日志只保留一个终态版本，拒绝动作与负责人可查。"""
    items = service.list_terminal_ledger(status=status, abnormal_only=abnormal_only)
    total = len(items)
    start = (page - 1) * size
    return PageResult(items=items[start:start + size], total=total, page=page, size=size)


@router.get("/terminal-ledger/{entry_id}", response_model=dict)
def get_terminal_ledger(entry_id: int) -> dict:
    """单条日志的终态版本详情；未命中终态时给出原因，避免详情页报错。"""
    record = service.get_terminal_ledger(entry_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"日志条目 {entry_id} 尚未产生终态版本，终态台账暂无该记录（仍处于未处理/处理中）",
        )
    return record


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条日志条目明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"日志条目 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: dict[str, object]) -> ActionResult:
    """登记一条日志条目，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="日志条目已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    """对单条日志执行动作；触碰终态边界的动作会被拒绝（HTTP 仍为 200，ok=False 并说明原因）。"""
    entry, message, accepted = service.run_action(
        entry_id,
        payload.action.strip(),
        operator=payload.operator,
        client_token=payload.client_token,
    )
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=accepted, message=message, entry=entry)
