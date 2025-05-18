"""
用户查询API路由

此模块提供处理用户查询的API端点，使用意图识别决定处理流程。
"""

import uuid
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

# 改为动态导入process_user_query，避免循环导入
# from src.main import process_user_query
from backend.utils.context_managers import workflow_run
from backend.dependencies import get_log_storage
from backend.state import api_state

# 创建router实例
router = APIRouter(
    prefix="/query",
    tags=["user_queries"],
    responses={404: {"description": "未找到"}},
)

# 定义请求模型
class UserQueryRequest(BaseModel):
    """用户查询请求模型"""
    
    query: str = Field(..., description="用户查询文本")
    show_reasoning: bool = Field(False, description="是否显示推理过程")


# 定义响应模型
class UserQueryResponse(BaseModel):
    """用户查询响应模型"""
    
    run_id: str = Field(..., description="执行ID")
    query: str = Field(..., description="原始查询文本")
    intent: str = Field(..., description="识别的意图")
    response: str = Field(..., description="回答内容")
    success: bool = Field(..., description="是否成功")
    message: Optional[str] = Field(None, description="附加消息")


# 后台任务函数：处理用户查询
def process_query_task(run_id: str, query: str, show_reasoning: bool = False):
    """
    后台执行用户查询处理
    
    Args:
        run_id: 运行ID
        query: 用户查询
        show_reasoning: 是否显示推理过程
    """
    # 设置当前运行ID
    api_state.current_run_id = run_id
    
    # 动态导入process_user_query
    from src.main import process_user_query
    
    # 使用workflow_run上下文管理器执行处理
    with workflow_run(run_id):
        result = process_user_query(
            run_id=run_id,
            query=query,
            show_reasoning=show_reasoning
        )
    
    # 处理完成后更新状态
    api_state.last_result = result
    api_state.current_run_id = None


@router.post("/process", response_model=UserQueryResponse)
async def process_query(
    request: UserQueryRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """
    处理用户查询，根据意图识别结果执行不同的流程
    
    Args:
        request: 包含查询文本和选项的请求
        background_tasks: FastAPI后台任务对象
        
    Returns:
        包含处理结果和元数据的响应
    """
    # 验证输入
    if not request.query:
        raise HTTPException(status_code=400, detail="查询文本不能为空")
    
    # 生成唯一运行ID
    run_id = str(uuid.uuid4())
    
    # 添加后台任务
    background_tasks.add_task(
        process_query_task,
        run_id=run_id,
        query=request.query,
        show_reasoning=request.show_reasoning
    )
    
    # 尝试立即进行意图识别以便返回意图类型
    try:
        from src.utils.intent_detector import detect_intent
        intent_result = detect_intent(request.query)
        intent = intent_result.get("intent", "UNKNOWN")
    except Exception as e:
        intent = "UNKNOWN"
        print(f"意图识别失败: {e}")
    
    # 返回响应
    return {
        "run_id": run_id,
        "query": request.query,
        "intent": intent,
        "response": "处理已开始，请通过轮询 /logs/{run_id} 端点查看进度和结果",
        "success": True,
        "message": f"意图识别为: {intent}，处理已在后台启动 (运行ID: {run_id})"
    } 