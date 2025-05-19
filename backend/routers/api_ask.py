from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict
import uuid

router = APIRouter(
    prefix="/api",
    tags=["webui_api"],
    responses={404: {"description": "未找到"}},
)

class AskRequest(BaseModel):
    query: str = Field(..., description="用户自然语言分析请求")

class AskResponse(BaseModel):
    result: str = Field(..., description="分析结果文本")
    run_id: str = Field(..., description="本次分析ID")
    intent: str = Field(..., description="识别意图")
    success: bool = Field(..., description="是否成功")
    message: str = Field(None, description="附加消息")

@router.post("/ask", response_model=AskResponse)
async def ask_agent(request: AskRequest) -> Dict[str, Any]:
    if not request.query:
        raise HTTPException(status_code=400, detail="请求内容不能为空")
    run_id = str(uuid.uuid4())
    try:
        # 在函数内部导入，避免循环依赖
        from src.main import process_user_query
        
        final_state = process_user_query(run_id=run_id, query=request.query, show_reasoning=False)
        # 提取最终回复
        if isinstance(final_state, dict):
            result = final_state["messages"][-1].content if final_state.get("messages") else "无回复"
            intent = final_state.get("data", {}).get("intent", "未知")
        else:
            result = str(final_state)
            intent = "未知"
        return {
            "result": result,
            "run_id": run_id,
            "intent": intent,
            "success": True,
            "message": "分析完成"
        }
    except Exception as e:
        return {
            "result": f"分析失败: {e}",
            "run_id": run_id,
            "intent": "未知",
            "success": False,
            "message": str(e)
        } 