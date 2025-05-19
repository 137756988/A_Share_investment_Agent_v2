from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict
import uuid
import os
import re
from pathlib import Path
from fastapi.responses import FileResponse

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

class ReportResponse(BaseModel):
    content: str = Field(..., description="分析报告内容")
    filename: str = Field(..., description="报告文件名")
    ticker: str = Field(..., description="股票代码")

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

@router.get("/reports")
async def list_reports():
    """获取所有可用的报告文件列表"""
    # 尝试多个可能的路径
    possible_paths = [
        Path("result"),                     # 相对于当前目录
        Path("../result"),                  # 相对于上级目录
        Path("../../result"),               # 相对于上上级目录
        Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "result")),  # 相对于项目根目录
        Path("/Users/zhouangguo/Desktop/Competitions/智能投顾/A_Share_investment_Agent_V2/result"),  # 绝对路径（紧急情况）
    ]
    
    result_dir = None
    
    # 尝试所有可能的路径
    for path in possible_paths:
        if path.exists() and path.is_dir():
            result_dir = path
            break
    
    if result_dir is None:
        return {
            "reports": [],
            "error": "无法找到报告目录",
            "searched_paths": [str(p) for p in possible_paths]
        }
    
    print(f"找到报告目录: {result_dir}")  # 添加调试信息
    
    # 获取所有MD文件
    report_files = list(result_dir.glob("*.md"))
    print(f"找到 {len(report_files)} 个报告文件")  # 添加调试信息
    
    # 提取股票代码和文件信息
    reports = []
    for file in report_files:
        print(f"处理文件: {file.name}")  # 添加调试信息
        # 使用正则表达式尝试提取股票代码
        match = re.search(r'股票(\d+)', file.name)
        ticker = match.group(1) if match else "未知"
        
        reports.append({
            "filename": file.name,
            "ticker": ticker,
            "modified_time": file.stat().st_mtime,
            "size": file.stat().st_size,
            "created": file.stat().st_ctime
        })
    
    # 按修改时间降序排序
    reports.sort(key=lambda x: x["modified_time"], reverse=True)
    
    return {
        "reports": reports,
        "directory": str(result_dir),
        "count": len(reports)
    }

@router.get("/report/{ticker}")
async def get_report(ticker: str) -> Dict[str, Any]:
    """获取特定股票的最新分析报告内容"""
    # 尝试多个可能的路径
    possible_paths = [
        Path("result"),                     # 相对于当前目录
        Path("../result"),                  # 相对于上级目录
        Path("../../result"),               # 相对于上上级目录
        Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "result")),  # 相对于项目根目录
        Path("/Users/zhouangguo/Desktop/Competitions/智能投顾/A_Share_investment_Agent_V2/result"),  # 绝对路径（紧急情况）
    ]
    
    result_dir = None
    
    # 尝试所有可能的路径
    for path in possible_paths:
        if path.exists() and path.is_dir():
            result_dir = path
            break
    
    if result_dir is None:
        raise HTTPException(
            status_code=404, 
            detail=f"找不到报告目录: 尝试了以下路径: {[str(p) for p in possible_paths]}"
        )
    
    print(f"找到报告目录: {result_dir}")  # 添加调试信息
    
    # 构建匹配此股票的文件名的正则表达式
    pattern = re.compile(f".*股票{ticker}.*分析报告.*\.md", re.IGNORECASE)
    
    # 查找最新的匹配文件
    matching_files = [f for f in result_dir.glob("*.md") if pattern.match(f.name)]
    print(f"找到 {len(matching_files)} 个匹配的报告文件")  # 添加调试信息
    
    if not matching_files:
        raise HTTPException(status_code=404, detail=f"找不到股票代码 {ticker} 的分析报告")
    
    # 按文件修改时间排序，获取最新的
    latest_file = max(matching_files, key=lambda f: f.stat().st_mtime)
    print(f"选择最新的报告文件: {latest_file.name}")  # 添加调试信息
    
    # 读取文件内容
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            content = f.read()
        return {
            "content": content,
            "filename": latest_file.name,
            "ticker": ticker
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取报告文件时出错: {str(e)}")

@router.get("/report/{ticker}/download")
async def download_report(ticker: str):
    """下载特定股票的最新分析报告文件"""
    # 尝试多个可能的路径
    possible_paths = [
        Path("result"),                     # 相对于当前目录
        Path("../result"),                  # 相对于上级目录
        Path("../../result"),               # 相对于上上级目录
        Path(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "result")),  # 相对于项目根目录
        Path("/Users/zhouangguo/Desktop/Competitions/智能投顾/A_Share_investment_Agent_V2/result"),  # 绝对路径（紧急情况）
    ]
    
    result_dir = None
    
    # 尝试所有可能的路径
    for path in possible_paths:
        if path.exists() and path.is_dir():
            result_dir = path
            break
    
    if result_dir is None:
        raise HTTPException(
            status_code=404, 
            detail=f"找不到报告目录: 尝试了以下路径: {[str(p) for p in possible_paths]}"
        )
    
    print(f"找到报告目录: {result_dir}")  # 添加调试信息
    
    # 构建匹配此股票的文件名的正则表达式
    pattern = re.compile(f".*股票{ticker}.*分析报告.*\.md", re.IGNORECASE)
    
    # 查找最新的匹配文件
    matching_files = [f for f in result_dir.glob("*.md") if pattern.match(f.name)]
    print(f"找到 {len(matching_files)} 个匹配的报告文件")  # 添加调试信息
    
    if not matching_files:
        raise HTTPException(status_code=404, detail=f"找不到股票代码 {ticker} 的分析报告")
    
    # 按文件修改时间排序，获取最新的
    latest_file = max(matching_files, key=lambda f: f.stat().st_mtime)
    print(f"选择最新的报告文件: {latest_file.name}")  # 添加调试信息
    
    # 返回文件作为下载
    return FileResponse(
        path=latest_file,
        filename=latest_file.name,
        media_type="text/markdown"
    ) 