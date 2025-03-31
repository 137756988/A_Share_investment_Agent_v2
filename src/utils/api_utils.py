"""
API工具模块 - 提供Agent共享的API功能组件

此模块定义了全局FastAPI应用实例和路由注册机制，
为各个Agent提供统一的API暴露方式。
"""

import json
import logging
import functools
import uuid
import threading
import time
import inspect
from typing import Dict, List, Any, Optional, Callable, TypeVar, Generic, Union
from datetime import datetime, timedelta
from contextlib import contextmanager
from pydantic import BaseModel, Field, create_model
from fastapi import FastAPI, APIRouter, HTTPException, Query, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from concurrent.futures import ThreadPoolExecutor, Future
import uvicorn
from functools import wraps
import builtins

# 设置基本日志
logger = logging.getLogger("api_utils")

# 类型定义
T = TypeVar('T')

# 增加一个全局字典用于跟踪每个agent的LLM调用
_agent_llm_calls = {}

# 增加一个记录get_chat_completion原始函数的变量
_original_get_chat_completion = None

# -----------------------------------------------------------------------------
# 数据模型
# -----------------------------------------------------------------------------


class ApiResponse(BaseModel, Generic[T]):
    """API响应的标准格式"""
    success: bool = True
    message: str = "操作成功"
    data: Optional[T] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentInfo(BaseModel):
    """Agent信息模型"""
    name: str
    description: str
    state: str = "idle"  # idle, running, completed, error
    last_run: Optional[datetime] = None


class RunInfo(BaseModel):
    """运行信息模型"""
    run_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str  # "running", "completed", "error"
    agents: List[str] = []


class StockAnalysisRequest(BaseModel):
    """股票分析请求模型"""
    ticker: str = Field(
        ...,
        description="股票代码，例如：'002848'",
        example="002848"
    )
    show_reasoning: bool = Field(
        True,
        description="是否显示分析推理过程",
        example=True
    )
    num_of_news: int = Field(
        5,
        description="用于情感分析的新闻文章数量（1-100）",
        ge=1,
        le=100,
        example=5
    )
    initial_capital: float = Field(
        100000.0,
        description="初始资金",
        gt=0,
        example=100000.0
    )
    initial_position: int = Field(
        0,
        description="初始持仓数量",
        ge=0,
        example=0
    )

    class Config:
        schema_extra = {
            "example": {
                "ticker": "002848",
                "show_reasoning": True,
                "num_of_news": 5,
                "initial_capital": 100000.0,
                "initial_position": 0
            }
        }


class StockAnalysisResponse(BaseModel):
    """股票分析响应模型"""
    run_id: str
    ticker: str
    status: str
    message: str
    submitted_at: datetime
    completed_at: Optional[datetime] = None


# -----------------------------------------------------------------------------
# 全局状态与内存存储
# -----------------------------------------------------------------------------

class ApiState:
    """API状态管理类，存储全局共享状态"""

    def __init__(self):
        self._lock = threading.RLock()
        self._agent_data: Dict[str, Dict] = {}
        self._runs: Dict[str, RunInfo] = {}
        self._current_run_id: Optional[str] = None
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._analysis_tasks: Dict[str, Future] = {}  # 跟踪分析任务

    @property
    def current_run_id(self) -> Optional[str]:
        """获取当前运行ID"""
        with self._lock:
            return self._current_run_id

    @current_run_id.setter
    def current_run_id(self, run_id: str):
        """设置当前运行ID"""
        with self._lock:
            self._current_run_id = run_id

    def register_agent(self, agent_name: str, description: str = ""):
        """注册一个Agent"""
        with self._lock:
            if agent_name not in self._agent_data:
                self._agent_data[agent_name] = {
                    "info": {
                        "name": agent_name,
                        "description": description,
                        "state": "idle",
                        "last_run": None
                    },
                    "latest": {
                        "input_state": None,
                        "output_state": None,
                        "llm_request": None,
                        "llm_response": None,
                        "reasoning": None,
                        "timestamp": None
                    },
                    "history": []  # 保存历史执行记录
                }

    def update_agent_state(self, agent_name: str, state: str):
        """更新Agent状态"""
        with self._lock:
            if agent_name in self._agent_data:
                self._agent_data[agent_name]["info"]["state"] = state
                if state in ["completed", "error"]:
                    self._agent_data[agent_name]["info"]["last_run"] = datetime.utcnow(
                    )

    def update_agent_data(self, agent_name: str, field: str, data: Any):
        """更新Agent数据"""
        with self._lock:
            if agent_name in self._agent_data:
                self._agent_data[agent_name]["latest"][field] = data
                self._agent_data[agent_name]["latest"]["timestamp"] = datetime.utcnow(
                )

                # 添加到历史记录
                if self._current_run_id:
                    history_entry = {
                        "run_id": self._current_run_id,
                        "timestamp": datetime.utcnow(),
                        field: data
                    }
                    self._agent_data[agent_name]["history"].append(
                        history_entry)

    def get_agent_info(self, agent_name: str) -> Optional[Dict]:
        """获取Agent信息"""
        with self._lock:
            if agent_name in self._agent_data:
                return self._agent_data[agent_name]["info"]
            return None

    def get_agent_data(self, agent_name: str, field: str = None) -> Optional[Dict]:
        """获取Agent数据"""
        with self._lock:
            if agent_name in self._agent_data:
                if field:
                    return self._agent_data[agent_name]["latest"].get(field)
                return self._agent_data[agent_name]["latest"]
            return None

    def get_all_agents(self) -> List[Dict]:
        """获取所有Agent信息"""
        with self._lock:
            return [data["info"] for data in self._agent_data.values()]

    def register_run(self, run_id: str):
        """注册新的运行"""
        with self._lock:
            self._runs[run_id] = RunInfo(
                run_id=run_id,
                start_time=datetime.utcnow(),
                status="running"
            )
            self._current_run_id = run_id

    def complete_run(self, run_id: str, status: str = "completed"):
        """完成运行"""
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].end_time = datetime.utcnow()
                self._runs[run_id].status = status

                # 更新参与的Agent列表
                agents = set()
                for agent_name, agent_data in self._agent_data.items():
                    for entry in agent_data["history"]:
                        if entry["run_id"] == run_id:
                            agents.add(agent_name)
                            break

                self._runs[run_id].agents = list(agents)

    def get_run(self, run_id: str) -> Optional[RunInfo]:
        """获取运行信息"""
        with self._lock:
            return self._runs.get(run_id)

    def get_all_runs(self) -> List[RunInfo]:
        """获取所有运行信息"""
        with self._lock:
            return list(self._runs.values())

    def register_analysis_task(self, run_id: str, future: Future):
        """注册分析任务"""
        with self._lock:
            self._analysis_tasks[run_id] = future

    def get_analysis_task(self, run_id: str) -> Optional[Future]:
        """获取分析任务"""
        with self._lock:
            return self._analysis_tasks.get(run_id)


# 创建全局API状态
api_state = ApiState()

# -----------------------------------------------------------------------------
# FastAPI应用
# -----------------------------------------------------------------------------

# 创建FastAPI应用
app = FastAPI(
    title="A股投资Agent API",
    description="A股投资Agent系统API接口",
    version="1.0.3",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# 路由管理
# -----------------------------------------------------------------------------

# 创建各个路由器，不使用嵌套前缀
agents_router = APIRouter(tags=["Agents"])
runs_router = APIRouter(tags=["Runs"])
workflow_router = APIRouter(tags=["Workflow"])

# -----------------------------------------------------------------------------
# 基础路由定义
# -----------------------------------------------------------------------------


@app.get("/", tags=["Root"])
async def read_root():
    """API根端点"""
    return {
        "message": "欢迎使用A股投资Agent API",
        "docs": "/docs",
        "version": "1.0.3"
    }


@app.get("/agents", response_model=List[AgentInfo], tags=["Agents"])
async def list_agents():
    """获取所有Agent列表"""
    agents = api_state.get_all_agents()
    return agents


@app.get("/agents/{agent_name}", response_model=ApiResponse[Dict], tags=["Agents"])
async def get_agent_info(agent_name: str):
    """获取指定Agent的信息"""
    info = api_state.get_agent_info(agent_name)
    if not info:
        return ApiResponse(
            success=False,
            message=f"Agent '{agent_name}' 不存在",
            data=None
        )
    return ApiResponse(data=info)


@app.get("/runs", response_model=List[RunInfo], tags=["Runs"])
async def list_runs(limit: int = Query(10, ge=1, le=100)):
    """获取运行历史列表"""
    runs = api_state.get_all_runs()
    # 按开始时间倒序排序，并限制数量
    runs.sort(key=lambda x: x.start_time, reverse=True)
    return runs[:limit]


@app.get("/runs/{run_id}", response_model=ApiResponse[RunInfo], tags=["Runs"])
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


@app.get("/workflow/status", response_model=ApiResponse[Dict], tags=["Workflow"])
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


# -----------------------------------------------------------------------------
# 股票分析接口
# -----------------------------------------------------------------------------

def execute_stock_analysis(request: StockAnalysisRequest, run_id: str):
    """执行股票分析任务"""
    from src.main import run_hedge_fund  # 避免循环导入

    try:
        # 初始化投资组合
        portfolio = {
            "cash": request.initial_capital,
            "stock": request.initial_position
        }

        # 执行分析 - 让系统自动计算日期
        logger.info(f"开始执行股票 {request.ticker} 的分析任务 (运行ID: {run_id})")
        with workflow_run(run_id):
            result = run_hedge_fund(
                ticker=request.ticker,
                start_date=None,  # 使用系统默认值
                end_date=None,    # 使用系统默认值
                portfolio=portfolio,
                show_reasoning=request.show_reasoning,
                num_of_news=request.num_of_news
            )

        logger.info(f"股票分析任务完成 (运行ID: {run_id})")
        return result
    except Exception as e:
        logger.error(f"股票分析任务失败: {str(e)}")
        # 更新运行状态为错误
        api_state.complete_run(run_id, "error")
        raise


@app.post("/analysis/start", response_model=StockAnalysisResponse, tags=["Analysis"])
async def start_stock_analysis(request: StockAnalysisRequest):
    """开始股票分析任务

    此API端点允许前端触发新的股票分析。分析将在后台进行，
    前端可通过返回的run_id查询分析状态和结果。

    参数说明:
    - ticker: 股票代码，如"002848"（必填）
    - show_reasoning: 是否显示分析推理过程，默认为true
    - num_of_news: 用于情感分析的新闻数量(1-100)，默认为5
    - initial_capital: 初始资金，默认为100000
    - initial_position: 初始持仓数量，默认为0

    分析日期说明:
    - 系统会自动使用最近一年的数据进行分析，无需手动指定日期范围

    示例请求:
    ```json
    {
        "ticker": "002848",
        "show_reasoning": true,
        "num_of_news": 5,
        "initial_capital": 100000.0,
        "initial_position": 0
    }
    ```

    简化请求(仅提供必填参数):
    ```json
    {
        "ticker": "002848"
    }
    ```
    """
    # 生成唯一ID
    run_id = str(uuid.uuid4())

    # 将任务提交到线程池
    future = api_state._executor.submit(
        execute_stock_analysis,
        request=request,
        run_id=run_id
    )

    # 注册任务
    api_state.register_analysis_task(run_id, future)

    # 注册运行
    api_state.register_run(run_id)

    return StockAnalysisResponse(
        run_id=run_id,
        ticker=request.ticker,
        status="running",
        message="分析任务已启动",
        submitted_at=datetime.utcnow()
    )


@app.get("/analysis/{run_id}/status", response_model=ApiResponse[Dict], tags=["Analysis"])
async def get_analysis_status(run_id: str):
    """获取股票分析任务的状态"""
    task = api_state.get_analysis_task(run_id)
    run_info = api_state.get_run(run_id)

    if not run_info:
        return ApiResponse(
            success=False,
            message=f"分析任务 '{run_id}' 不存在",
            data=None
        )

    status_data = {
        "run_id": run_id,
        "status": run_info.status,
        "start_time": run_info.start_time,
        "end_time": run_info.end_time,
    }

    if task:
        if task.done():
            if task.exception():
                status_data["error"] = str(task.exception())
            status_data["is_complete"] = True
        else:
            status_data["is_complete"] = False

    return ApiResponse(data=status_data)


@app.get("/analysis/{run_id}/result", response_model=ApiResponse[Dict], tags=["Analysis"])
async def get_analysis_result(run_id: str):
    """获取股票分析任务的结果数据

    此接口返回最终的投资决策结果以及各个Agent的分析数据摘要。
    分析必须已经完成才能获取结果。
    """
    try:
        task = api_state.get_analysis_task(run_id)
        run_info = api_state.get_run(run_id)

        if not run_info:
            return ApiResponse(
                success=False,
                message=f"分析任务 '{run_id}' 不存在",
                data=None
            )

        # 检查任务是否完成
        if run_info.status != "completed":
            return ApiResponse(
                success=False,
                message=f"分析任务尚未完成或已失败，当前状态: {run_info.status}",
                data={"status": run_info.status}
            )

        # 收集所有参与此运行的Agent数据
        agent_results = {}
        ticker = ""
        for agent_name in run_info.agents:
            agent_data = api_state.get_agent_data(agent_name)
            if agent_data and "reasoning" in agent_data:
                # 尝试解析和序列化推理数据
                reasoning_data = safe_parse_json(agent_data["reasoning"])
                agent_results[agent_name] = serialize_for_api(reasoning_data)

            # 尝试从market_data_agent获取ticker
            if agent_name == "market_data" and agent_data and "output_state" in agent_data:
                try:
                    output = agent_data["output_state"]
                    if "data" in output and "ticker" in output["data"]:
                        ticker = output["data"]["ticker"]
                except Exception:
                    pass

        # 尝试获取portfolio_management的最终决策
        final_decision = None
        portfolio_data = api_state.get_agent_data("portfolio_management")
        if portfolio_data and "output_state" in portfolio_data:
            try:
                output = portfolio_data["output_state"]
                messages = output.get("messages", [])
                # 获取最后一个消息
                if messages:
                    last_message = messages[-1]
                    if hasattr(last_message, "content"):
                        # 尝试解析content，可能是JSON字符串
                        final_decision = safe_parse_json(last_message.content)
            except Exception as e:
                logger.error(f"解析最终决策时出错: {str(e)}")

        result_data = {
            "run_id": run_id,
            "ticker": ticker,
            "completion_time": run_info.end_time,
            "final_decision": serialize_for_api(final_decision),
            "agent_results": agent_results
        }

        return ApiResponse(data=result_data)
    except Exception as e:
        logger.error(f"获取分析结果时出错: {str(e)}")
        return ApiResponse(
            success=False,
            message=f"获取分析结果时出错: {str(e)}",
            data={"error": str(e)}
        )


# -----------------------------------------------------------------------------
# 装饰器和工具函数
# -----------------------------------------------------------------------------

def safe_parse_json(data):
    """
    安全地解析可能是字符串形式的 JSON 数据

    如果输入是字符串并包含 JSON 内容，尝试解析为字典
    否则返回原始数据
    """
    if not isinstance(data, str):
        return data

    # 如果是字符串，尝试解析为 JSON
    try:
        # 如果字符串包含代码块格式，先清理一下
        if data.startswith("```") and "```" in data:
            # 去除 markdown 代码块标记
            lines = data.split("\n")
            # 找到真正的 JSON 开始行和结束行
            start_idx = 0
            end_idx = len(lines)
            for i, line in enumerate(lines):
                if line.startswith("```") and i == 0:
                    start_idx = 1
                elif line.startswith("```") and i > 0:
                    end_idx = i
                    break

            # 提取 JSON 内容
            json_content = "\n".join(lines[start_idx:end_idx])
            return json.loads(json_content)

        # 直接尝试解析
        return json.loads(data)
    except (json.JSONDecodeError, ValueError):
        # 如果解析失败，返回原始字符串
        return data


def serialize_for_api(obj: Any) -> Any:
    """将任意对象转换为API友好的格式，确保可JSON序列化"""
    if obj is None:
        return None

    # 首先尝试解析可能的 JSON 字符串
    obj = safe_parse_json(obj)

    if isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_api(x) for x in obj]
    elif isinstance(obj, dict):
        return {str(k): serialize_for_api(v) for k, v in obj.items()}
    elif hasattr(obj, 'dict') and callable(getattr(obj, 'dict')):
        # 处理Pydantic模型
        return serialize_for_api(obj.dict())
    elif hasattr(obj, 'to_dict') and callable(getattr(obj, 'to_dict')):
        # 处理有to_dict方法的对象
        return serialize_for_api(obj.to_dict())
    elif hasattr(obj, '__dict__'):
        # 处理一般Python对象
        return serialize_for_api(obj.__dict__)
    else:
        # 其他情况转为字符串
        return str(obj)


def format_llm_request(request_data: Any) -> Dict:
    """格式化LLM请求数据为可读格式"""
    if request_data is None:
        return {"message": "没有记录LLM请求"}

    # 先尝试解析可能的JSON字符串
    request_data = safe_parse_json(request_data)

    # 处理元组，通常是*args形式
    if isinstance(request_data, tuple):
        # 如果元组中有消息列表
        if len(request_data) > 0 and isinstance(request_data[0], list):
            messages = request_data[0]
            # 尝试将消息整理为统一格式
            formatted_messages = []
            message_texts = []

            for msg in messages:
                if isinstance(msg, dict):
                    formatted_msg = msg
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    message_texts.append(f"[{role}] {content}")
                elif hasattr(msg, 'type') and hasattr(msg, 'content'):
                    # 处理LangChain消息
                    formatted_msg = {
                        "role": msg.type,
                        "content": msg.content
                    }
                    message_texts.append(f"[{msg.type}] {msg.content}")
                else:
                    # 其他类型
                    formatted_msg = {"content": str(msg)}
                    message_texts.append(str(msg))

                formatted_messages.append(formatted_msg)

            return {
                "messages": formatted_messages,
                "formatted": "\n".join(message_texts)
            }
        # 处理其他参数形式
        return {"args": [serialize_for_api(arg) for arg in request_data]}

    # 处理字典，通常是**kwargs形式
    if isinstance(request_data, dict):
        return serialize_for_api(request_data)

    # 如果是列表，可能是消息列表
    if isinstance(request_data, list):
        try:
            # 尝试按消息列表处理
            formatted_messages = []
            message_texts = []

            for msg in request_data:
                if isinstance(msg, dict):
                    formatted_msg = msg
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    message_texts.append(f"[{role}] {content}")
                elif hasattr(msg, 'type') and hasattr(msg, 'content'):
                    # 处理LangChain消息
                    formatted_msg = {
                        "role": msg.type,
                        "content": msg.content
                    }
                    message_texts.append(f"[{msg.type}] {msg.content}")
                else:
                    # 其他类型
                    formatted_msg = {"content": str(msg)}
                    message_texts.append(str(msg))

                formatted_messages.append(formatted_msg)

            return {
                "messages": formatted_messages,
                "formatted": "\n".join(message_texts)
            }
        except Exception:
            # 如果无法处理为消息列表，按一般列表处理
            return {"items": [serialize_for_api(item) for item in request_data]}

    # 默认情况
    return {"data": serialize_for_api(request_data)}


def format_llm_response(response_data: Any) -> Dict:
    """格式化LLM响应数据为可读格式"""
    if response_data is None:
        return {"message": "没有记录LLM响应"}

    # 先尝试解析可能的JSON字符串
    response_data = safe_parse_json(response_data)

    # 处理有content属性的对象（如Gemini响应）
    if hasattr(response_data, 'text'):
        return {
            "text": response_data.text,
            "original": serialize_for_api(response_data)
        }

    # 处理字符串（直接返回的文本）
    if isinstance(response_data, str):
        return {"text": response_data}

    # 处理字典（可能是API响应）
    if isinstance(response_data, dict):
        if "choices" in response_data and isinstance(response_data["choices"], list):
            # 可能是OpenAI风格的响应
            try:
                messages = []
                for choice in response_data["choices"]:
                    if "message" in choice:
                        messages.append(choice["message"])

                if messages:
                    return {
                        "messages": messages,
                        "original": serialize_for_api(response_data)
                    }
            except Exception:
                pass

        # 一般的字典响应
        return serialize_for_api(response_data)

    # 处理字典或其他复杂对象
    return serialize_for_api(response_data)


def log_llm_interaction(state):
    """记录LLM交互的装饰器函数

    这个函数可以以两种方式使用：
    1. 作为装饰器工厂：log_llm_interaction(state)(llm_func)
    2. 作为直接调用函数：用于已有的log_llm_interaction兼容模式
    """
    # 检查是否是直接函数调用模式（向后兼容）
    if isinstance(state, str) and len(state) > 0:
        # 兼容原有直接调用方式
        agent_name = state  # 第一个参数是agent_name

        def direct_logger(request_data, response_data):
            # 保存格式化的请求和响应
            formatted_request = format_llm_request(request_data)
            formatted_response = format_llm_response(response_data)

            api_state.update_agent_data(
                agent_name, "llm_request", formatted_request)
            api_state.update_agent_data(
                agent_name, "llm_response", formatted_response)

            # 记录交互的时间戳
            api_state.update_agent_data(
                agent_name, "llm_timestamp", datetime.utcnow().isoformat())

            return response_data

        return direct_logger

    # 装饰器工厂模式
    def decorator(llm_func):
        @functools.wraps(llm_func)
        def wrapper(*args, **kwargs):
            # 获取函数调用信息，以便更好地记录请求
            caller_frame = inspect.currentframe().f_back
            caller_info = {
                "function": llm_func.__name__,
                "file": caller_frame.f_code.co_filename,
                "line": caller_frame.f_lineno
            }

            result = llm_func(*args, **kwargs)

            # 如果有当前运行的Agent名称，记录LLM交互
            agent_name = state.get("metadata", {}).get("current_agent_name")
            if agent_name:
                # 准备格式化的请求数据
                formatted_request = {
                    "caller": caller_info,
                    "arguments": format_llm_request(args),
                    "kwargs": format_llm_request(kwargs) if kwargs else {}
                }

                # 准备格式化的响应数据
                formatted_response = format_llm_response(result)

                # 记录到API状态
                api_state.update_agent_data(
                    agent_name, "llm_request", formatted_request)
                api_state.update_agent_data(
                    agent_name, "llm_response", formatted_response)
                api_state.update_agent_data(
                    agent_name, "llm_timestamp", datetime.utcnow().isoformat())

            return result
        return wrapper
    return decorator


@contextmanager
def workflow_run(run_id: str):
    """
    工作流运行上下文管理器

    用法:
    with workflow_run(run_id):
        # 执行工作流
    """
    api_state.register_run(run_id)
    try:
        yield
        api_state.complete_run(run_id, "completed")
    except Exception as e:
        api_state.complete_run(run_id, "error")
        raise


def patch_get_chat_completion():
    """
    使用猴子补丁拦截所有get_chat_completion调用，确保能够捕获任何agent中的LLM交互
    """
    try:
        # 避免循环导入
        from src.tools.openrouter_config import get_chat_completion as original_func
        global _original_get_chat_completion

        if _original_get_chat_completion is not None:
            logger.debug("get_chat_completion已经被拦截，不再重复应用补丁")
            return  # 已经打过补丁了

        logger.info("正在应用get_chat_completion拦截补丁...")
        _original_get_chat_completion = original_func

        def patched_get_chat_completion(messages, model=None, max_retries=3, initial_retry_delay=1,
                                        client_type="auto", api_key=None, base_url=None):
            """拦截get_chat_completion调用的猴子补丁"""
            # 获取当前正在运行的agent名称
            current_agent = None
            run_id = None

            try:
                # 从当前上下文中获取当前agent
                with api_state._lock:
                    run_id = api_state._current_run_id
                    for agent_name, agent_data in api_state._agent_data.items():
                        if agent_data["info"]["state"] == "running":
                            current_agent = agent_name
                            break

                # 记录请求详情（for调试）
                if current_agent:
                    logger.debug(
                        f"拦截到{current_agent}的LLM请求: 消息数: {len(messages)}")
                else:
                    logger.debug(f"拦截到匿名LLM请求: 消息数: {len(messages)}")

                # 调用原始函数获取LLM响应
                start_time = datetime.utcnow()
                response = _original_get_chat_completion(
                    messages,
                    model=model,
                    max_retries=max_retries,
                    initial_retry_delay=initial_retry_delay,
                    client_type=client_type,
                    api_key=api_key,
                    base_url=base_url
                )
                end_time = datetime.utcnow()
                duration_ms = (end_time - start_time).total_seconds() * 1000

                # 如果找到当前运行的agent，记录LLM调用
                if current_agent:
                    # 格式化请求和响应
                    formatted_request = format_llm_request(messages)
                    formatted_response = format_llm_response(response)

                    # 添加额外元数据
                    formatted_request["meta"] = {
                        "model": model,
                        "client_type": client_type,
                        "timestamp": start_time.isoformat()
                    }
                    formatted_response["meta"] = {
                        "duration_ms": duration_ms,
                        "timestamp": end_time.isoformat()
                    }

                    # 保存到API状态
                    api_state.update_agent_data(
                        current_agent, "llm_request", formatted_request)
                    api_state.update_agent_data(
                        current_agent, "llm_response", formatted_response)
                    api_state.update_agent_data(
                        current_agent, "llm_timestamp", end_time.isoformat())

                    # 跟踪此agent有LLM调用
                    _agent_llm_calls[current_agent] = True

                    logger.debug(
                        f"已记录{current_agent}的LLM交互 (耗时: {duration_ms:.0f}ms)")

                return response

            except Exception as e:
                logger.error(f"拦截LLM调用时出错: {str(e)}")
                # 出错时仍然调用原始函数，确保业务流程不中断
                return _original_get_chat_completion(
                    messages,
                    model=model,
                    max_retries=max_retries,
                    initial_retry_delay=initial_retry_delay,
                    client_type=client_type,
                    api_key=api_key,
                    base_url=base_url
                )

        # 应用猴子补丁
        import src.tools.openrouter_config
        src.tools.openrouter_config.get_chat_completion = patched_get_chat_completion

        logger.info("✅ get_chat_completion拦截器应用成功")
        return True
    except Exception as e:
        logger.error(f"应用get_chat_completion拦截器失败: {str(e)}")
        return False


# 在模块导入时尝试应用补丁
try:
    patch_result = patch_get_chat_completion()
    if patch_result:
        logger.info("LLM交互拦截器已准备就绪")
    else:
        logger.warning("LLM交互拦截器未能初始化，LLM请求和响应API可能无法工作")
except Exception as e:
    logger.error(f"初始化LLM交互拦截器时出错: {str(e)}")
    # 不阻止其他功能初始化


def agent_endpoint(agent_name: str, description: str = ""):
    """
    为Agent创建API端点的装饰器

    用法:
    @agent_endpoint("sentiment")
    def sentiment_agent(state: AgentState) -> AgentState:
        ...
    """
    def decorator(agent_func):
        # 注册Agent
        api_state.register_agent(agent_name, description)

        # 初始化此agent的LLM调用跟踪
        _agent_llm_calls[agent_name] = False

        # 标记此Agent的LLM端点是否已注册
        has_registered_llm_endpoints = [False]  # 使用列表以便闭包内可修改

        # 添加LLM相关端点的函数
        def register_llm_endpoints():
            """为Agent注册LLM相关端点"""
            if has_registered_llm_endpoints[0]:
                return  # 已经注册过了

            # 3. 获取LLM请求
            @app.get(f"/agents/{agent_name}/latest_llm_request", response_model=ApiResponse[Dict], tags=["Agents"])
            async def get_latest_llm_request():
                try:
                    data = api_state.get_agent_data(agent_name, "llm_request")
                    # 确保返回有意义的数据
                    if data is None:
                        return ApiResponse(
                            success=True,
                            message=f"没有找到{agent_name}的LLM请求记录",
                            data={"message": f"没有找到{agent_name}的LLM请求记录"}
                        )

                    # 尝试解析和序列化数据
                    serialized_data = serialize_for_api(data)

                    # 确保结果是字典类型
                    if not isinstance(serialized_data, dict):
                        # 如果不是字典，包装为字典返回
                        serialized_data = {
                            "content": serialized_data, "type": "raw_content"}

                    return ApiResponse(data=serialized_data)
                except Exception as e:
                    logger.error(f"处理{agent_name}的LLM请求数据时出错: {str(e)}")
                    return ApiResponse(
                        success=False,
                        message=f"无法处理{agent_name}的LLM请求数据: {str(e)}",
                        data={"error": str(e)}
                    )

            # 4. 获取LLM响应
            @app.get(f"/agents/{agent_name}/latest_llm_response", response_model=ApiResponse[Dict], tags=["Agents"])
            async def get_latest_llm_response():
                try:
                    data = api_state.get_agent_data(agent_name, "llm_response")
                    # 确保返回有意义的数据
                    if data is None:
                        return ApiResponse(
                            success=True,
                            message=f"没有找到{agent_name}的LLM响应记录",
                            data={"message": f"没有找到{agent_name}的LLM响应记录"}
                        )

                    # 尝试解析和序列化数据
                    serialized_data = serialize_for_api(data)

                    # 确保结果是字典类型
                    if not isinstance(serialized_data, dict):
                        # 如果不是字典，包装为字典返回
                        serialized_data = {
                            "content": serialized_data, "type": "raw_content"}

                    return ApiResponse(data=serialized_data)
                except Exception as e:
                    logger.error(f"处理{agent_name}的LLM响应数据时出错: {str(e)}")
                    return ApiResponse(
                        success=False,
                        message=f"无法处理{agent_name}的LLM响应数据: {str(e)}",
                        data={"error": str(e)}
                    )

            has_registered_llm_endpoints[0] = True
            logger.info(f"已为{agent_name}添加LLM相关端点")

        @functools.wraps(agent_func)
        def wrapper(state):
            # 更新Agent状态为运行中
            api_state.update_agent_state(agent_name, "running")

            # 添加当前agent名称到状态元数据
            if "metadata" not in state:
                state["metadata"] = {}
            state["metadata"]["current_agent_name"] = agent_name

            # 记录输入状态
            api_state.update_agent_data(agent_name, "input_state", state)

            try:
                # 执行原始函数
                result = agent_func(state)

                # 记录输出状态
                api_state.update_agent_data(agent_name, "output_state", result)

                # 从状态中提取推理细节（如果有）
                if result.get("metadata", {}).get("show_reasoning", False):
                    if "agent_reasoning" in result.get("metadata", {}):
                        api_state.update_agent_data(
                            agent_name,
                            "reasoning",
                            result["metadata"]["agent_reasoning"]
                        )

                # 检查是否应该添加LLM端点 - agent执行后可能会有LLM调用
                if _agent_llm_calls.get(agent_name, False) and not has_registered_llm_endpoints[0]:
                    register_llm_endpoints()

                # 更新Agent状态为已完成
                api_state.update_agent_state(agent_name, "completed")

                return result
            except Exception as e:
                # 更新Agent状态为错误
                api_state.update_agent_state(agent_name, "error")
                # 记录错误信息
                api_state.update_agent_data(agent_name, "error", str(e))
                # 重新抛出异常
                raise

        # 为此Agent添加通用路由
        # 1. 获取输入状态
        @app.get(f"/agents/{agent_name}/latest_input", response_model=ApiResponse[Dict], tags=["Agents"])
        async def get_latest_input():
            data = api_state.get_agent_data(agent_name, "input_state")
            return ApiResponse(data=serialize_for_api(data))

        # 2. 获取输出状态
        @app.get(f"/agents/{agent_name}/latest_output", response_model=ApiResponse[Dict], tags=["Agents"])
        async def get_latest_output():
            data = api_state.get_agent_data(agent_name, "output_state")
            return ApiResponse(data=serialize_for_api(data))

        # 5. 获取推理详情 - 修改此函数
        @app.get(f"/agents/{agent_name}/reasoning", response_model=ApiResponse[Dict], tags=["Agents"])
        async def get_reasoning():
            try:
                # 获取数据
                data = api_state.get_agent_data(agent_name, "reasoning")

                # 如果数据不存在
                if data is None:
                    return ApiResponse(
                        success=False,
                        message=f"没有找到{agent_name}的推理记录",
                        data={"message": f"Agent {agent_name} 没有推理数据"}
                    )

                # 尝试解析和序列化数据
                serialized_data = serialize_for_api(data)

                # 确保结果是字典类型
                if not isinstance(serialized_data, dict):
                    # 如果不是字典，包装为字典返回
                    return ApiResponse(
                        data={"content": serialized_data,
                              "type": "raw_content"}
                    )

                return ApiResponse(data=serialized_data)
            except Exception as e:
                # 记录错误并返回友好的错误信息
                logger.error(f"序列化{agent_name}的推理数据时出错: {str(e)}")
                return ApiResponse(
                    success=False,
                    message=f"无法处理{agent_name}的推理数据: {str(e)}",
                    data={"error": str(e), "original_type": str(type(data))}
                )

        # 在启动时可能需要检查历史调用并注册端点
        @app.on_event("startup")
        async def init_check_llm_endpoints():
            # 如果有历史记录表明该agent使用了LLM，那么创建端点
            if api_state.get_agent_data(agent_name, "llm_request") is not None:
                _agent_llm_calls[agent_name] = True
                if not has_registered_llm_endpoints[0]:
                    register_llm_endpoints()

        return wrapper
    return decorator

# 启动API服务器的函数


def start_api_server(host="0.0.0.0", port=8000, stop_event=None):
    """在独立线程中启动API服务器"""
    if stop_event:
        # 使用支持优雅关闭的配置
        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_config=None,
            # 开启ctrl+c处理
            use_colors=True
        )
        server = uvicorn.Server(config)

        # 运行服务器并在单独线程中监听stop_event
        def check_stop_event():
            # 在后台检查stop_event
            while not stop_event.is_set():
                time.sleep(0.5)
            # 当stop_event被设置时，请求服务器退出
            logger.info("收到停止信号，正在关闭API服务器...")
            server.should_exit = True

        # 启动stop_event监听线程
        stop_monitor = threading.Thread(
            target=check_stop_event,
            daemon=True
        )
        stop_monitor.start()

        # 运行服务器（阻塞调用，但会响应should_exit标志）
        try:
            server.run()
        except KeyboardInterrupt:
            # 如果还是收到了KeyboardInterrupt，确保我们的stop_event也被设置
            stop_event.set()
        logger.info("API服务器已关闭")
    else:
        # 默认方式启动，不支持外部停止控制但仍响应Ctrl+C
        uvicorn.run(app, host=host, port=port, log_config=None)
