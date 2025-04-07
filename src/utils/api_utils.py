"""
API工具模块 - 提供Agent共享的API功能组件

此模块定义了全局FastAPI应用实例和路由注册机制，
为各个Agent提供统一的API暴露方式。

注意: 大部分功能已被重构到backend目录，此模块仅为向后兼容性而保留。
"""

from fastapi import APIRouter
from backend.main import app  # Restore this import
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
            """拦截get_chat_completion调用的猴子补丁
            (注意: 已移除日志记录和状态更新逻辑，仅保留调用原始函数)
            """
            # --- 移除了尝试获取上下文 (current_agent, run_id) 的逻辑 ---
            # --- 移除了记录请求详情的日志 ---
            try:
                # 直接调用原始函数获取LLM响应
                response = _original_get_chat_completion(
                    messages,
                    model=model,
                    max_retries=max_retries,
                    initial_retry_delay=initial_retry_delay,
                    client_type=client_type,
                    api_key=api_key,
                    base_url=base_url
                )
                # --- 移除了记录耗时、格式化数据、更新api_state、添加到BaseLogStorage的逻辑 ---
                return response

            except Exception as e:
                logger.error(f"执行原始LLM调用时出错: {str(e)}")
                # 出错时仍然尝试调用原始函数 (这是原始代码的逻辑，保留)
                # 或者可以直接抛出异常，取决于期望行为
                raise  # Re-raise the exception to let the caller handle it
                # Original code attempted to call again, which might not be ideal
                # return _original_get_chat_completion(
                #     messages,
                #     model=model,
                #     max_retries=max_retries,
                #     initial_retry_delay=initial_retry_delay,
                #     client_type=client_type,
                #     api_key=api_key,
                #     base_url=base_url
                # )

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

        @functools.wraps(agent_func)
        def wrapper(state):
            # 更新Agent状态为运行中
            api_state.update_agent_state(agent_name, "running")

            # 添加当前agent名称到状态元数据
            if "metadata" not in state:
                state["metadata"] = {}
            state["metadata"]["current_agent_name"] = agent_name

            # 确保run_id在元数据中，这对日志记录至关重要
            run_id = state.get("metadata", {}).get("run_id")
            # 记录输入状态
            timestamp_start = datetime.now(UTC)
            serialized_input = serialize_agent_state(state)
            api_state.update_agent_data(
                agent_name, "input_state", serialized_input)

            result = None
            error = None
            terminal_outputs = []  # Capture terminal output

            # Capture stdout/stderr and logs during agent execution
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            log_stream = io.StringIO()
            log_handler = logging.StreamHandler(log_stream)
            log_handler.setLevel(logging.INFO)
            root_logger = logging.getLogger()
            root_logger.addHandler(log_handler)

            redirect_stdout = io.StringIO()
            redirect_stderr = io.StringIO()
            sys.stdout = redirect_stdout
            sys.stderr = redirect_stderr

            try:
                # --- 执行Agent核心逻辑 ---
                # 直接调用原始 agent_func
                result = agent_func(state)
                # --------------------------

                timestamp_end = datetime.now(UTC)

                # 恢复标准输出/错误
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                root_logger.removeHandler(log_handler)

                # 获取捕获的输出
                stdout_content = redirect_stdout.getvalue()
                stderr_content = redirect_stderr.getvalue()
                log_content = log_stream.getvalue()
                if stdout_content:
                    terminal_outputs.append(stdout_content)
                if stderr_content:
                    terminal_outputs.append(stderr_content)
                if log_content:
                    terminal_outputs.append(log_content)

                # 序列化输出状态
                serialized_output = serialize_agent_state(result)
                api_state.update_agent_data(
                    agent_name, "output_state", serialized_output)

                # 从状态中提取推理细节（如果有）
                reasoning_details = None
                if result.get("metadata", {}).get("show_reasoning", False):
                    if "agent_reasoning" in result.get("metadata", {}):
                        reasoning_details = result["metadata"]["agent_reasoning"]
                        api_state.update_agent_data(
                            agent_name,
                            "reasoning",
                            reasoning_details
                        )

                # 更新Agent状态为已完成
                api_state.update_agent_state(agent_name, "completed")

                # --- 添加Agent执行日志到BaseLogStorage ---
                try:
                    if _has_log_system:
                        log_storage = get_log_storage()
                        if log_storage:
                            log_entry = AgentExecutionLog(
                                agent_name=agent_name,
                                run_id=run_id,
                                timestamp_start=timestamp_start,
                                timestamp_end=timestamp_end,
                                input_state=serialized_input,
                                output_state=serialized_output,
                                reasoning_details=reasoning_details,
                                terminal_outputs=terminal_outputs
                            )
                            log_storage.add_agent_log(log_entry)
                            logger.debug(
                                f"已将Agent执行日志保存到存储: {agent_name}, run_id: {run_id}")
                        else:
                            logger.warning(
                                f"无法获取日志存储实例，跳过Agent执行日志记录: {agent_name}")
                except Exception as log_err:
                    logger.error(
                        f"保存Agent执行日志到存储失败: {agent_name}, {str(log_err)}")
                # -----------------------------------------

                return result
            except Exception as e:
                # Record end time even on error
                timestamp_end = datetime.now(UTC)
                error = str(e)
                # 恢复标准输出/错误
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                root_logger.removeHandler(log_handler)
                # 获取捕获的输出
                stdout_content = redirect_stdout.getvalue()
                stderr_content = redirect_stderr.getvalue()
                log_content = log_stream.getvalue()
                if stdout_content:
                    terminal_outputs.append(stdout_content)
                if stderr_content:
                    terminal_outputs.append(stderr_content)
                if log_content:
                    terminal_outputs.append(log_content)

                # 更新Agent状态为错误
                api_state.update_agent_state(agent_name, "error")
                # 记录错误信息
                api_state.update_agent_data(agent_name, "error", error)

                # --- 添加错误日志到BaseLogStorage ---
                try:
                    if _has_log_system:
                        log_storage = get_log_storage()
                        if log_storage:
                            log_entry = AgentExecutionLog(
                                agent_name=agent_name,
                                run_id=run_id,
                                timestamp_start=timestamp_start,
                                timestamp_end=timestamp_end,
                                input_state=serialized_input,
                                output_state={"error": error},
                                reasoning_details=None,
                                terminal_outputs=terminal_outputs
                            )
                            log_storage.add_agent_log(log_entry)
                            logger.debug(
                                f"已将Agent错误日志保存到存储: {agent_name}, run_id: {run_id}")
                        else:
                            logger.warning(
                                f"无法获取日志存储实例，跳过Agent错误日志记录: {agent_name}")
                except Exception as log_err:
                    logger.error(
                        f"保存Agent错误日志到存储失败: {agent_name}, {str(log_err)}")
                # --------------------------------------

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
