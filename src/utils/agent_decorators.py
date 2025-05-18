"""
Agent装饰器模块 - 提供Agent装饰器功能

此模块提供了agent_endpoint装饰器，用于将Agent函数注册为API端点。
这个模块被单独分离出来以避免循环导入问题。
"""

import sys
import io
import functools
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime, UTC

# 存储所有已注册的agents
registered_agents = {}

def agent_endpoint(name: str, description: Optional[str] = None) -> Callable:
    """
    注册一个Agent函数为API端点

    Args:
        name: Agent的唯一名称标识符
        description: Agent的描述信息

    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        # 注册agent到全局字典
        registered_agents[name] = {
            "function": func,
            "name": name,
            "description": description or func.__doc__ or f"Agent: {name}"
        }
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 在函数被调用时可以添加metadata
            if args and isinstance(args[0], dict) and "metadata" in args[0]:
                args[0]["metadata"]["current_agent_name"] = name
            
            try:
                # 尝试更新backend的状态（如果可用）
                from backend.state import api_state
                api_state.current_agent_name = name
            except ImportError:
                pass  # 忽略未找到模块的错误
                
            # 调用原始函数
            return func(*args, **kwargs)
            
        return wrapper
    return decorator


def get_registered_agents() -> Dict[str, Dict[str, Any]]:
    """
    获取所有已注册的Agents

    Returns:
        Dict[str, Dict[str, Any]]: 包含所有已注册Agent信息的字典
    """
    return registered_agents

# agent_endpoint装饰器
def agent_endpoint_old(agent_name: str, description: str = ""):
    """
    为Agent创建API端点的装饰器

    用法:
    @agent_endpoint("sentiment")
    def sentiment_agent(state: AgentState) -> AgentState:
        ...
    """
    def decorator(agent_func):
        # 当装饰器被应用时导入，避免循环导入
        from backend.state import api_state
        from src.utils.serialization import serialize_agent_state
        
        # 初始化agent_llm_calls跟踪字典（如果不存在）
        global _agent_llm_calls
        if '_agent_llm_calls' not in globals():
            _agent_llm_calls = {}
        
        # 注册Agent
        api_state.register_agent(agent_name, description)

        # 初始化此agent的LLM调用跟踪
        _agent_llm_calls[agent_name] = False

        @functools.wraps(agent_func)
        def wrapper(state):
            # 当函数被调用时导入，避免循环导入
            from backend.state import api_state
            from backend.schemas import AgentExecutionLog
            
            # 确定是否有日志系统
            has_log_system = False
            try:
                from backend.dependencies import get_log_storage
                has_log_system = True
            except ImportError:
                pass
            
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
            
            logger = logging.getLogger("agent_decorators")

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
                    if has_log_system:
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
                    if has_log_system:
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