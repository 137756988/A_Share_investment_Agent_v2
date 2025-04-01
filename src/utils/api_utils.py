"""
API工具模块 - 提供Agent共享的API功能组件

此模块定义了全局FastAPI应用实例和路由注册机制，
为各个Agent提供统一的API暴露方式。

注意: 大部分功能已被重构到backend目录，此模块仅为向后兼容性而保留。
"""

from fastapi import APIRouter
from backend.main import app
import json
import logging
import functools
import uuid
import threading
import time
import inspect
from typing import Dict, List, Any, Optional, Callable, TypeVar, Generic, Union
from datetime import datetime, timedelta, UTC
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, Future
import uvicorn
from functools import wraps
import builtins

# 导入重构后的模块
from backend.models.api_models import (
    ApiResponse, AgentInfo, RunInfo,
    StockAnalysisRequest, StockAnalysisResponse
)
from backend.state import api_state
from backend.utils.api_utils import (
    serialize_for_api,
    safe_parse_json,
    format_llm_request,
    format_llm_response
)
from backend.utils.context_managers import workflow_run
from backend.services import execute_stock_analysis
from backend.schemas import LLMInteractionLog

# 导入日志记录器
try:
    from src.utils.llm_interaction_logger import log_agent_execution, set_global_log_storage
    from backend.dependencies import get_log_storage
    _has_log_system = True
except ImportError:
    _has_log_system = False

    def log_agent_execution(agent_name):
        def decorator(func):
            return func
        return decorator

# 设置全局日志存储器
if _has_log_system:
    try:
        storage = get_log_storage()
        set_global_log_storage(storage)
    except Exception as e:
        logger.warning(f"设置全局日志存储器失败: {str(e)}")

# 设置基本日志
logger = logging.getLogger("api_utils")

# 类型定义
T = TypeVar('T')

# 增加一个全局字典用于跟踪每个agent的LLM调用
_agent_llm_calls = {}

# 增加一个记录get_chat_completion原始函数的变量
_original_get_chat_completion = None

# -----------------------------------------------------------------------------
# FastAPI应用
# -----------------------------------------------------------------------------

# 从backend中导入FastAPI应用

# 这些路由器不再使用，仅为向后兼容性保留定义
agents_router = APIRouter(tags=["Agents"])
runs_router = APIRouter(tags=["Runs"])
workflow_router = APIRouter(tags=["Workflow"])

# -----------------------------------------------------------------------------
# 装饰器和工具函数
# -----------------------------------------------------------------------------


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

            timestamp = datetime.now(UTC)

            # 获取当前运行ID
            run_id = api_state.current_run_id

            api_state.update_agent_data(
                agent_name, "llm_request", formatted_request)
            api_state.update_agent_data(
                agent_name, "llm_response", formatted_response)

            # 记录交互的时间戳
            api_state.update_agent_data(
                agent_name, "llm_timestamp", timestamp.isoformat())

            # 同时保存到BaseLogStorage (解决/logs端点返回空问题)
            try:
                # 获取log_storage实例
                if _has_log_system:
                    log_storage = get_log_storage()
                    # 创建LLMInteractionLog对象
                    log_entry = LLMInteractionLog(
                        agent_name=agent_name,
                        run_id=run_id,
                        request_data=formatted_request,
                        response_data=formatted_response,
                        timestamp=timestamp
                    )
                    # 添加到存储
                    log_storage.add_log(log_entry)
                    logger.debug(f"已将直接调用的LLM交互保存到日志存储: {agent_name}")
            except Exception as log_err:
                logger.warning(f"保存直接调用的LLM交互到日志存储失败: {str(log_err)}")

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
            run_id = state.get("metadata", {}).get("run_id")

            if agent_name:
                timestamp = datetime.now(UTC)

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
                    agent_name, "llm_timestamp", timestamp.isoformat())

                # 同时保存到BaseLogStorage (解决/logs端点返回空问题)
                try:
                    # 获取log_storage实例
                    if _has_log_system:
                        log_storage = get_log_storage()
                        # 创建LLMInteractionLog对象
                        log_entry = LLMInteractionLog(
                            agent_name=agent_name,
                            run_id=run_id,
                            request_data=formatted_request,
                            response_data=formatted_response,
                            timestamp=timestamp
                        )
                        # 添加到存储
                        log_storage.add_log(log_entry)
                        logger.debug(f"已将装饰器捕获的LLM交互保存到日志存储: {agent_name}")
                except Exception as log_err:
                    logger.warning(f"保存装饰器捕获的LLM交互到日志存储失败: {str(log_err)}")

            return result
        return wrapper
    return decorator


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
                start_time = datetime.now(UTC)
                response = _original_get_chat_completion(
                    messages,
                    model=model,
                    max_retries=max_retries,
                    initial_retry_delay=initial_retry_delay,
                    client_type=client_type,
                    api_key=api_key,
                    base_url=base_url
                )
                end_time = datetime.now(UTC)
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

                    # 同时保存到BaseLogStorage (解决/logs端点返回空问题)
                    try:
                        # 获取log_storage实例
                        if _has_log_system:
                            log_storage = get_log_storage()
                            # 创建LLMInteractionLog对象
                            log_entry = LLMInteractionLog(
                                agent_name=current_agent,
                                run_id=run_id,
                                request_data=formatted_request,
                                response_data=formatted_response,
                                timestamp=end_time
                            )
                            # 添加到存储
                            log_storage.add_log(log_entry)
                            logger.debug(f"已将LLM交互保存到日志存储: {current_agent}")
                    except Exception as log_err:
                        logger.error(f"保存LLM交互到日志存储失败: {str(log_err)}")

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

        # 首先应用日志记录器装饰器
        if _has_log_system:
            logged_func = log_agent_execution(agent_name)(agent_func)
        else:
            logged_func = agent_func

        @functools.wraps(agent_func)
        def wrapper(state):
            # 更新Agent状态为运行中
            api_state.update_agent_state(agent_name, "running")

            # 添加当前agent名称到状态元数据
            if "metadata" not in state:
                state["metadata"] = {}
            state["metadata"]["current_agent_name"] = agent_name

            # 确保run_id在元数据中，这对日志记录至关重要
            if "run_id" not in state.get("metadata", {}):
                # 尝试从api_state获取当前run_id
                current_run_id = api_state.current_run_id
                if current_run_id:
                    state["metadata"]["run_id"] = current_run_id

            # 记录输入状态
            api_state.update_agent_data(agent_name, "input_state", state)

            try:
                # 执行带日志记录的函数
                result = logged_func(state)

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
