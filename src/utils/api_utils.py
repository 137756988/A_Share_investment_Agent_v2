"""
API工具模块 - 提供Agent共享的API功能组件

此模块定义了全局FastAPI应用实例和路由注册机制，
为各个Agent提供统一的API暴露方式。

注意: 大部分功能已被重构到backend目录，此模块仅为向后兼容性而保留。
"""

from fastapi import APIRouter
# 修改导入方式，避免直接导入
# from backend.main import app  # Restore this import
import json  # Keep - Used implicitly?
import logging
import functools
# import uuid # Unused
import threading  # Used for server stop event
import time  # Used for server stop event
import inspect  # Used in log_llm_interaction (decorator mode)
from typing import Dict, List, Any, Optional, Callable, TypeVar  # Keep needed types
from datetime import datetime, UTC  # Keep needed datetime objects
# from contextlib import contextmanager # Unused
# from concurrent.futures import ThreadPoolExecutor, Future # Unused
import uvicorn  # Used in start_api_server
# from functools import wraps # Redundant, imported via functools
# import builtins # Unused
import sys
import io

# 导入agent_endpoint装饰器
from src.utils.agent_decorators import agent_endpoint

# 导入重构后的模块
from backend.models.api_models import (
    # ApiResponse, AgentInfo, # Potentially unused
    RunInfo,  # Keep
    # StockAnalysisRequest, StockAnalysisResponse # Potentially unused
)
from backend.state import api_state
from backend.utils.api_utils import (
    # serialize_for_api, # Unused
    safe_parse_json,  # Keep
    format_llm_request,  # Keep
    format_llm_response  # Keep
)
# from backend.utils.context_managers import workflow_run # Unused
# from backend.services import execute_stock_analysis # Unused
from backend.schemas import LLMInteractionLog  # Keep
from backend.schemas import AgentExecutionLog  # Keep
from src.utils.serialization import serialize_agent_state  # Keep

# 导入日志记录器
try:
    # log_agent_execution is no longer needed here
    from src.utils.llm_interaction_logger import set_global_log_storage  # Keep
    from backend.dependencies import get_log_storage
    _has_log_system = True
except ImportError:
    _has_log_system = False
    # Define a dummy set_global_log_storage if import fails

    def set_global_log_storage(storage):
        pass
    # Define a dummy get_log_storage if import fails

    def get_log_storage():
        return None

# 统一在此处定义 logger，无论 _has_log_system 如何
logger = logging.getLogger("api_utils")

# 设置全局日志存储器
if _has_log_system:
    try:
        storage = get_log_storage()
        set_global_log_storage(storage)
    except Exception as e:
        # logger 此时必定已定义
        logger.warning(f"设置全局日志存储器失败: {str(e)}")

# 类型定义
T = TypeVar('T')

# 增加一个全局字典用于跟踪每个agent的LLM调用
_agent_llm_calls = {}

# -----------------------------------------------------------------------------
# FastAPI应用
# -----------------------------------------------------------------------------

# 改为动态导入FastAPI应用
app = None
def get_app():
    """动态获取FastAPI应用实例，避免循环导入"""
    global app
    if app is None:
        try:
            from backend.main import app as fastapi_app
            app = fastapi_app
        except ImportError:
            logger.warning("无法导入FastAPI应用，API功能可能不可用")
    return app

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

            # 执行原始函数获取结果
            result = llm_func(*args, **kwargs)

            # 从state中提取agent_name和run_id
            agent_name = None
            run_id = None

            # 尝试从state参数中提取
            if isinstance(state, dict):
                agent_name = state.get("metadata", {}).get(
                    "current_agent_name")
                run_id = state.get("metadata", {}).get("run_id")

            # 如果state中没有，尝试从上下文变量中获取
            if not agent_name:
                try:
                    from src.utils.llm_interaction_logger import current_agent_name_context, current_run_id_context
                    agent_name = current_agent_name_context.get()
                    run_id = current_run_id_context.get()
                except (ImportError, AttributeError):
                    pass

            # 如果仍然没有，尝试从api_state中获取当前运行的agent
            if not agent_name and hasattr(api_state, "current_agent_name"):
                agent_name = api_state.current_agent_name
                run_id = api_state.current_run_id

            if agent_name:
                timestamp = datetime.now(UTC)

                # 提取messages参数
                messages = None
                if "messages" in kwargs:
                    messages = kwargs["messages"]
                elif args and len(args) > 0:
                    messages = args[0]

                # 提取其他参数
                model = kwargs.get("model")
                client_type = kwargs.get("client_type", "auto")

                # 准备格式化的请求数据
                formatted_request = {
                    "caller": caller_info,
                    "messages": messages,
                    "model": model,
                    "client_type": client_type,
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


# 启动API服务器的函数
def start_api_server(host="0.0.0.0", port=8000, stop_event=None):
    """在独立线程中启动API服务器"""
    # 获取应用程序实例
    app_instance = get_app()
    if app_instance is None:
        logger.error("无法获取FastAPI应用实例，API服务无法启动")
        return

    if stop_event:
        # 使用支持优雅关闭的配置
        config = uvicorn.Config(
            app=app_instance,
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
            # 当stop_event被设置，发送中断信号
            logger.info("检测到stop_event被设置，正在中断服务器...")
            server.should_exit = True

        # 启动监听线程
        stop_listener = threading.Thread(
            target=check_stop_event, daemon=True)
        stop_listener.start()

        # 启动服务器（这是阻塞的，但在stop_event设置时会被中断）
        try:
            server.run()
        except KeyboardInterrupt:
            logger.info("捕获到KeyboardInterrupt，正在关闭服务器...")
        finally:
            logger.info("服务器已关闭")
    else:
        # 无优雅关闭的标准启动模式
        uvicorn.run(app_instance, host=host, port=port, log_config=None)
