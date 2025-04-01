"""
运行历史相关路由模块

此模块提供与工作流运行历史相关的API端点
"""

from fastapi import APIRouter, Query
from typing import Dict, List

from ..models.api_models import ApiResponse, RunInfo
from ..state import api_state

# 创建路由器
router = APIRouter(prefix="/api/runs", tags=["Runs"])


@router.get("/", response_model=List[RunInfo])
async def list_runs(limit: int = Query(10, ge=1, le=100)):
    """获取运行历史列表"""
    runs = api_state.get_all_runs()
    # 按开始时间倒序排序，并限制数量
    runs.sort(key=lambda x: x.start_time, reverse=True)
    return runs[:limit]


@router.get("/{run_id}", response_model=ApiResponse[RunInfo])
async def get_run_info(run_id: str):
    """获取指定运行的信息"""
    run = api_state.get_run(run_id)
    if not run:
        return ApiResponse(
            success=False,
            message=f"运行 '{run_id}' 不存在",
            data=None
        )
    return ApiResponse(data=run)
