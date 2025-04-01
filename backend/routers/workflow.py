"""
工作流相关路由模块

此模块提供与工作流状态、执行和管理相关的API端点
"""

from fastapi import APIRouter
from typing import Dict

from ..models.api_models import ApiResponse
from ..state import api_state

# 创建路由器
router = APIRouter(prefix="/api/workflow", tags=["Workflow"])


@router.get("/status", response_model=ApiResponse[Dict])
async def get_workflow_status():
    """获取当前工作流状态"""
    current_run_id = api_state.current_run_id
    if not current_run_id:
        return ApiResponse(
            data={
                "status": "idle",
                "message": "当前没有运行中的工作流"
            }
        )

    run = api_state.get_run(current_run_id)
    agents = api_state.get_all_agents()

    return ApiResponse(
        data={
            "status": run.status,
            "run_id": current_run_id,
            "start_time": run.start_time,
            "agents": [a for a in agents if a["state"] != "idle"]
        }
    )
