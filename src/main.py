#!/usr/bin/env python
import sys
import argparse
import uuid  # Import uuid for run IDs
import threading  # Import threading for background task
import uvicorn  # Import uvicorn to run FastAPI

from datetime import datetime, timedelta
from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage
import pandas as pd
import akshare as ak

# --- Agent Imports ---
from src.agents.valuation import valuation_agent
from src.agents.state import AgentState
from src.agents.sentiment import sentiment_agent
from src.agents.risk_manager import risk_management_agent
from src.agents.technicals import technical_analyst_agent
from src.agents.portfolio_manager import portfolio_management_agent
from src.agents.market_data import market_data_agent
from src.agents.fundamentals import fundamentals_agent
from src.agents.researcher_bull import researcher_bull_agent
from src.agents.researcher_bear import researcher_bear_agent
from src.agents.debate_room import debate_room_agent
from src.agents.macro_analyst import macro_analyst_agent
from src.agents.report_analyzer import report_analyzer_agent  # 添加财务报告分析助手
from src.agents.knowledge_query import knowledge_query_agent  # 添加金融知识查询助手

# --- 添加意图识别工具 ---
from src.utils.intent_detector import detect_intent, extract_stock_info

# --- Logging and Backend Imports ---
from src.utils.output_logger import OutputLogger
# 导入原始函数，但不再进行猴子补丁
from src.tools.openrouter_config import get_chat_completion
from src.utils.llm_interaction_logger import (
    log_agent_execution,
    set_global_log_storage
)
from backend.dependencies import get_log_storage
# 移除这行直接导入
# from backend.main import app as fastapi_app  # Import the FastAPI app

# --- Import Summary Report Generator ---
try:
    from src.utils.summary_report import print_summary_report
    from src.utils.agent_collector import store_final_state, get_enhanced_final_state
    HAS_SUMMARY_REPORT = True
except ImportError:
    HAS_SUMMARY_REPORT = False

# --- Import Structured Terminal Output ---
try:
    from src.utils.structured_terminal import print_structured_output
    HAS_STRUCTURED_OUTPUT = True
except ImportError:
    HAS_STRUCTURED_OUTPUT = False

# --- Initialize Logging ---

# 1. Initialize Log Storage
log_storage = get_log_storage()
set_global_log_storage(log_storage)  # Set storage in context for the wrapper

# 移除猴子补丁逻辑
# 2. Wrap the original LLM call function
# logged_get_chat_completion = wrap_llm_call(original_get_chat_completion)

# 3. Monkey-patch the function in its original module
# src.tools.openrouter_config.get_chat_completion = logged_get_chat_completion
# Optional: Confirmation message
# print("--- Patched get_chat_completion for logging ---")

# Initialize standard output logging
# This will create a timestamped log file in the logs directory
sys.stdout = OutputLogger()

# --- 添加新函数: 判断输入是股票代码还是股票名称，并在需要时自动搜索股票代码 ---
def resolve_stock_input(input_value, non_interactive=False):
    """
    判断输入是股票代码还是股票名称，并返回对应的股票代码
    
    Args:
        input_value: 输入值，可能是股票代码或股票名称
        non_interactive: 是否为非交互式环境，如果是则自动选择第一个匹配项
        
    Returns:
        str: 股票代码
    """
    try:
        # 获取A股股票代码和名称对照表
        df = ak.stock_info_a_code_name()
        
        # 检查1: 是否为股票代码格式 (纯数字或字母数字组合，长度为6)
        if input_value.isdigit() or (len(input_value) == 6 and input_value.isalnum()):
            # 验证股票代码是否存在
            if input_value in df['code'].values:
                stock_name = df[df['code'] == input_value]['name'].values[0]
                print(f"找到股票: {input_value} - {stock_name}")
                return input_value
            else:
                print(f"警告: 股票代码 '{input_value}' 不存在于当前A股市场，请检查输入")
        
        # 检查2: 是否为精确的股票名称
        exact_match = df[df['name'] == input_value]
        if not exact_match.empty:
            selected_ticker = exact_match.iloc[0]['code']
            selected_name = exact_match.iloc[0]['name']
            print(f"精确匹配股票: {selected_ticker} - {selected_name}")
            return selected_ticker
        
        # 检查3: 模糊匹配股票名称
        print(f"尝试模糊匹配股票名称: '{input_value}'")
        # 根据名称模糊查询
        result = df[df['name'].str.contains(input_value)]
        
        # 如果没有找到，尝试关键词搜索
        if result.empty:
            print(f"未找到包含 '{input_value}' 的股票名称，尝试关键词搜索...")
            keywords = input_value.split()
            for keyword in keywords:
                if len(keyword) >= 2:  # 只搜索长度大于等于2的关键词
                    result = df[df['name'].str.contains(keyword)]
                    if not result.empty:
                        print(f"通过关键词 '{keyword}' 找到相关股票")
                        break
        
        # 处理搜索结果
        if result.empty:
            print(f"未找到与 '{input_value}' 匹配的股票，请使用有效的股票代码或名称")
            sys.exit(1)
        
        # 显示匹配的股票列表
        print("\n找到以下匹配的股票:")
        for i, (_, row) in enumerate(result.iterrows()):
            print(f"{i+1}. {row['code']} - {row['name']}")
        
        # 处理匹配结果
        if len(result) == 1:
            # 只有一个匹配项，自动选择
            selected_ticker = result.iloc[0]['code']
            selected_name = result.iloc[0]['name']
            print(f"\n自动选择唯一匹配项: {selected_ticker} - {selected_name}")
            return selected_ticker
        
        elif non_interactive:
            # 非交互式模式下自动选择第一个匹配项
            selected_ticker = result.iloc[0]['code']
            selected_name = result.iloc[0]['name']
            print(f"\n非交互模式: 自动选择第一个匹配项: {selected_ticker} - {selected_name}")
            return selected_ticker
        
        else:
            # 交互式选择
            while True:
                try:
                    user_input = input("\n请选择要分析的股票编号 [1-{}]: ".format(len(result)))
                    if not user_input:  # 如果输入为空，默认选择第一项
                        selected_index = 0
                        break
                    
                    selected_index = int(user_input) - 1
                    if 0 <= selected_index < len(result):
                        break
                    else:
                        print(f"请输入1到{len(result)}之间的数字")
                except ValueError:
                    print("请输入有效的数字")
                except EOFError:
                    # 处理EOF错误（可能在某些环境中发生）
                    print("\n检测到EOF错误，自动选择第一个匹配项")
                    selected_index = 0
                    break
                except KeyboardInterrupt:
                    print("\n操作已取消")
                    sys.exit(1)
            
            selected_ticker = result.iloc[selected_index]['code']
            selected_name = result.iloc[selected_index]['name']
            print(f"\n您选择了: {selected_ticker} - {selected_name}")
            return selected_ticker
        
    except Exception as e:
        print(f"搜索股票时出错: {e}")
        print("请使用有效的股票代码或名称")
        sys.exit(1)


# --- Run the Hedge Fund Workflow ---
def run_hedge_fund(run_id: str, ticker: str, start_date: str, end_date: str, portfolio: dict, show_reasoning: bool = False, num_of_news: int = 5, show_summary: bool = False, generate_report: bool = True):
    print(f"--- Starting Workflow Run ID: {run_id} ---")

    # 设置backend的run_id
    try:
        from backend.state import api_state
        api_state.current_run_id = run_id
        print(f"--- API State updated with Run ID: {run_id} ---")
    except Exception as e:
        print(f"Note: Could not update API state: {str(e)}")
    
    # 获取股票名称
    stock_name = ""
    try:
        # 先尝试获取股票信息
        stock_df = ak.stock_info_a_code_name()
        stock_row = stock_df[stock_df['code'] == ticker]
        if not stock_row.empty:
            stock_name = stock_row.iloc[0]['name']
            print(f"✓ 获取到股票名称: {stock_name}")
    except Exception as e:
        print(f"获取股票名称时出错: {str(e)}")

    initial_state = {
        "messages": [
            HumanMessage(
                content="Make a trading decision based on the provided data.",
            )
        ],
        "data": {
            "ticker": ticker,
            "portfolio": portfolio,
            "start_date": start_date,
            "end_date": end_date,
            "num_of_news": num_of_news,
        },
        "metadata": {
            "show_reasoning": show_reasoning,
            "run_id": run_id,  # Pass run_id in metadata
            "show_summary": show_summary,  # 是否显示汇总报告
            "generate_report": generate_report,  # 是否生成中文解析报告
        }
    }
    
    # 添加股票名称到state
    if stock_name:
        initial_state["data"]["stock_name"] = stock_name

    # 使用backend的workflow_run上下文管理器（如果可用）
    try:
        from backend.utils.context_managers import workflow_run
        with workflow_run(run_id):
            final_state = app.invoke(initial_state)
            print(f"--- Finished Workflow Run ID: {run_id} ---")

            # 在工作流结束后保存最终状态并生成汇总报告（如果启用）
            if HAS_SUMMARY_REPORT and show_summary:
                # 保存最终状态到收集器
                store_final_state(final_state)
                # 获取增强的最终状态（包含所有收集到的数据）
                enhanced_state = get_enhanced_final_state()
                # 打印汇总报告
                print_summary_report(enhanced_state)

            # 如果启用了显示推理，显示结构化输出
            if HAS_STRUCTURED_OUTPUT and show_reasoning:
                print_structured_output(final_state)
    except ImportError:
        # 如果未能导入，直接执行
        final_state = app.invoke(initial_state)
        print(f"--- Finished Workflow Run ID: {run_id} ---")

        # 在工作流结束后保存最终状态并生成汇总报告（如果启用）
        if HAS_SUMMARY_REPORT and show_summary:
            # 保存最终状态到收集器
            store_final_state(final_state)
            # 获取增强的最终状态（包含所有收集到的数据）
            enhanced_state = get_enhanced_final_state()
            # 打印汇总报告
            print_summary_report(enhanced_state)

        # 如果启用了显示推理，显示结构化输出
        if HAS_STRUCTURED_OUTPUT and show_reasoning:
            print_structured_output(final_state)

        # 尝试更新API状态（如果可用）
        try:
            api_state.complete_run(run_id, "completed")
        except Exception:
            pass

    # 保持原有的返回格式：最后一条消息的内容
    return final_state["messages"][-1].content


# --- 新增功能: 处理用户查询，根据意图执行不同的流程 ---
def process_user_query(run_id: str, query: str, show_reasoning: bool = False) -> AgentState:
    """
    处理用户查询，根据意图识别结果执行不同的流程
    
    Args:
        run_id: 运行ID
        query: 用户查询
        show_reasoning: 是否显示推理过程
        
    Returns:
        AgentState: 最终状态
    """
    print(f"\n=== 开始处理用户查询 [ID: {run_id[:8]}] ===")
    print(f"📝 用户查询: '{query}'")
    
    try:
        # 识别用户意图
        print("🔍 正在识别意图...")
        intent_result = detect_intent(query)
        intent = intent_result["intent"]
        print(f"✅ 成功识别意图: {intent}")
        
        # 打印详细的意图识别结果
        print(f"🔹 原始文本: {intent_result['text']}")
        print(f"🔹 领域: {intent_result['domain']}")
        
        # 如果有槽位信息，也打印出来
        if "slots" in intent_result and intent_result["slots"]:
            print("🔹 识别到的槽位信息:")
            for slot_name, slot_values in intent_result["slots"].items():
                if isinstance(slot_values, list):
                    slot_value = ", ".join(slot_values)
                else:
                    slot_value = slot_values
                print(f"  - {slot_name}: {slot_value}")
    except Exception as e:
        # 意图识别失败时记录错误并返回错误消息
        print(f"❌ 意图识别失败: {str(e)}")
        print("⚠️ 将尝试使用备用方法判断意图...")
        
        # 简单的备份判断逻辑：如果包含股票、基金等关键词，可能是股票分析
        stock_keywords = ["股票", "基金", "投资", "涨跌", "买入", "卖出", "持有", "市值", 
                         "估值", "分析", "趋势", "技术面", "基本面", "短线", "长线"]
        
        is_likely_stock_query = any(keyword in query for keyword in stock_keywords)
        
        if is_likely_stock_query:
            intent = "STOCK_ANALYSIS"
            print(f"✓ 备用判断结果: 可能是股票分析查询")
        else:
            intent = "KNOWLEDGE_QUERY"
            print(f"✓ 备用判断结果: 可能是金融知识查询")
            
        error_message = f"意图识别模型出错，已使用备用方法判断。原始错误: {str(e)}"
        
        # 构建错误响应
        initial_state = {
            "messages": [
                HumanMessage(content=query)
            ],
            "data": {
                "user_query": query,
                "intent": intent,
                "error": str(e)
            },
            "metadata": {
                "show_reasoning": show_reasoning,
                "run_id": run_id
            }
        }
        
        # 根据备用判断结果执行相应的逻辑
        if intent == "KNOWLEDGE_QUERY":
            return knowledge_query_agent(initial_state)
        else:
            return initial_state
    
    # 初始化状态
    initial_state = {
        "messages": [
            HumanMessage(content=query)
        ],
        "data": {
            "user_query": query,
            "intent": intent
        },
        "metadata": {
            "show_reasoning": show_reasoning,
            "run_id": run_id
        }
    }
    
    # 根据意图执行不同的流程
    if intent == "KNOWLEDGE_QUERY":
        print("\n🧠 执行金融知识查询流程")
        # 直接调用金融知识查询助手
        try:
            print("⏳ 正在处理知识查询，这可能需要一些时间...")
            final_state = knowledge_query_agent(initial_state)
            print("✅ 知识查询处理完成")
        except Exception as e:
            # 处理知识查询中的错误
            print(f"❌ 知识查询处理失败: {str(e)}")
            error_message = f"知识查询处理失败: {str(e)}"
            messages = initial_state["messages"]
            messages.append(HumanMessage(content=error_message))
            final_state = {
                "messages": messages,
                "data": initial_state["data"],
                "metadata": initial_state["metadata"]
            }
    else:  # STOCK_ANALYSIS 或其他默认为股票分析
        print("\n📊 执行股票分析流程")
        # 提取可能的股票代码或名称
        try:
            # 使用extract_stock_info函数从意图识别结果中提取股票信息
            print("🔍 从意图识别结果中提取股票信息...")
            stock_code, stock_name, has_stock_info = extract_stock_info(intent_result)
            
            # 决定使用哪种方式获取股票代码
            if has_stock_info:
                if stock_code:
                    print(f"✅ 从槽位中直接提取到股票代码: {stock_code}")
                    ticker = stock_code
                elif stock_name:
                    print(f"✅ 从槽位中提取到股票名称: {stock_name}")
                    # 解析股票代码
                    ticker = resolve_stock_input(stock_name, non_interactive=True)
                    print(f"✓ 根据股票名称查找到股票代码: {ticker}")
                    # 保存原始股票名称供后续使用
                    stock_name_for_report = stock_name
            else:
                # 没有从槽位中找到股票信息，尝试从整个查询中查找
                print("⚠️ 未从槽位中识别到股票信息，尝试从整个查询中分析...")
                # 尝试判断查询文本中是否包含股票名称或代码
                try:
                    stock_df = ak.stock_info_a_code_name()
                    # 首先尝试找股票名称
                    for _, row in stock_df.iterrows():
                        if row['name'] in query:
                            stock_name_for_report = row['name']
                            ticker = row['code']
                            print(f"✓ 从查询文本中找到股票名称: {stock_name_for_report}, 对应代码: {ticker}")
                            break
                    else:
                        # 如果没找到名称，再尝试解析
                        ticker = resolve_stock_input(query, non_interactive=True)
                        # 尝试获取解析出的代码对应的名称
                        stock_row = stock_df[stock_df['code'] == ticker]
                        if not stock_row.empty:
                            stock_name_for_report = stock_row.iloc[0]['name']
                        else:
                            stock_name_for_report = ""
                        print(f"✓ 从查询文本中解析出股票代码: {ticker}, 对应名称: {stock_name_for_report}")
                except Exception as e:
                    print(f"❌ 从查询文本分析股票信息时出错: {e}")
                    ticker = resolve_stock_input(query, non_interactive=True)
                    stock_name_for_report = ""
                    print(f"✓ 从查询文本中解析出股票代码: {ticker}")
            
            # 设置当前日期和日期范围
            current_date = datetime.now()
            yesterday = current_date - timedelta(days=1)
            end_date = yesterday
            start_date = end_date - timedelta(days=365)
            
            # 更新状态
            initial_state["data"]["ticker"] = ticker
            # 传递股票名称到state
            if stock_name_for_report:
                initial_state["data"]["stock_name"] = stock_name_for_report
            initial_state["data"]["start_date"] = start_date.strftime('%Y-%m-%d')
            initial_state["data"]["end_date"] = end_date.strftime('%Y-%m-%d')
            initial_state["data"]["portfolio"] = {
                "cash": 100000.0,
                "stock": 0
            }
            initial_state["data"]["num_of_news"] = 5
            initial_state["metadata"]["generate_report"] = True
            
            print(f"\n🚀 开始执行股票分析工作流")
            print(f"🔖 股票代码: {ticker}")
            print(f"📅 分析时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
            print(f"⏳ 分析进行中，这可能需要几分钟时间...")
            
            # 调用股票分析流程
            final_state = app.invoke(initial_state)
            print(f"✅ 股票分析完成")
        except Exception as e:
            # 如果提取股票失败，返回错误消息
            print(f"❌ 股票分析处理失败: {str(e)}")
            error_message = f"无法识别有效的股票代码或名称: {str(e)}。请提供明确的股票代码或名称进行分析。"
            messages = initial_state["messages"]
            messages.append(HumanMessage(content=error_message))
            final_state = {
                "messages": messages,
                "data": initial_state["data"],
                "metadata": initial_state["metadata"]
            }
    
    print(f"=== 用户查询处理完成 [ID: {run_id[:8]}] ===\n")
    return final_state


# --- Create the LangGraph StateGraph ---
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("market_data_agent", market_data_agent)
workflow.add_node("technical_analyst_agent", technical_analyst_agent)
workflow.add_node("fundamentals_agent", fundamentals_agent)
workflow.add_node("sentiment_agent", sentiment_agent)
workflow.add_node("valuation_agent", valuation_agent)
workflow.add_node("researcher_bull_agent", researcher_bull_agent)
workflow.add_node("researcher_bear_agent", researcher_bear_agent)
workflow.add_node("debate_room_agent", debate_room_agent)
workflow.add_node("risk_management_agent", risk_management_agent)
workflow.add_node("macro_analyst_agent", macro_analyst_agent)
workflow.add_node("portfolio_management_agent", portfolio_management_agent)
workflow.add_node("report_analyzer_agent", report_analyzer_agent)  # 财务报告分析助手节点
workflow.add_node("knowledge_query_agent", knowledge_query_agent)  # 金融知识查询助手节点

# Define the workflow edges
workflow.set_entry_point("market_data_agent")

# Market Data to Analysts
workflow.add_edge("market_data_agent", "technical_analyst_agent")
workflow.add_edge("market_data_agent", "fundamentals_agent")
workflow.add_edge("market_data_agent", "sentiment_agent")
workflow.add_edge("market_data_agent", "valuation_agent")

# Analysts to Researchers
workflow.add_edge("technical_analyst_agent", "researcher_bull_agent")
workflow.add_edge("fundamentals_agent", "researcher_bull_agent")
workflow.add_edge("sentiment_agent", "researcher_bull_agent")
workflow.add_edge("valuation_agent", "researcher_bull_agent")

workflow.add_edge("technical_analyst_agent", "researcher_bear_agent")
workflow.add_edge("fundamentals_agent", "researcher_bear_agent")
workflow.add_edge("sentiment_agent", "researcher_bear_agent")
workflow.add_edge("valuation_agent", "researcher_bear_agent")

# Researchers to Debate Room
workflow.add_edge("researcher_bull_agent", "debate_room_agent")
workflow.add_edge("researcher_bear_agent", "debate_room_agent")

# Debate Room to Risk Management
workflow.add_edge("debate_room_agent", "risk_management_agent")

# Risk Management to Macro Analyst
workflow.add_edge("risk_management_agent", "macro_analyst_agent")

# Macro Analyst to Portfolio Management
workflow.add_edge("macro_analyst_agent", "portfolio_management_agent")

# Portfolio Management to Report Analyzer 或 END
# 添加条件路由：如果需要生成报告则进入报告分析节点，否则直接结束
def router(state: AgentState):
    # 首先检查是否为知识查询意图
    intent = state.get('data', {}).get('intent')
    if intent == "KNOWLEDGE_QUERY":
        return "knowledge_query_agent"
    
    # 然后检查元数据中是否设置了generate_report标志
    if state.get('metadata', {}).get('generate_report', True):
        return "report_analyzer_agent"
    else:
        return END

workflow.add_conditional_edges(
    "portfolio_management_agent",
    router
)

# 报告分析器和知识查询到结束
workflow.add_edge("report_analyzer_agent", END)
workflow.add_edge("knowledge_query_agent", END)

# Compile the workflow graph
app = workflow.compile()


# --- FastAPI Background Task ---
def run_fastapi():
    """启动FastAPI服务器作为后台任务"""
    try:
        from backend.main import app as fastapi_app
        print("--- Starting FastAPI server in background (port 8000) ---")
        # Note: Change host/port/log_level as needed
        # Disable Uvicorn's own logging config to avoid conflicts with app's logging
        uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_config=None)
    except ImportError as e:
        print(f"注意: 无法启动FastAPI服务: {e}")


# --- 添加新函数: 封装主程序逻辑 ---
def run_main():
    """
    封装主程序逻辑，作为模块入口点
    """
    # 尝试启动 FastAPI 服务（后台）
    try:
        from backend.main import app as fastapi_app  # 仅在需要时导入
        fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
        fastapi_thread.start()
        print("✅ FastAPI服务已在后台启动")
    except ImportError as e:
        print(f"注意: FastAPI服务未启动 - {e}")

    # --- 参数解析 ---
    parser = argparse.ArgumentParser(
        description='A股投资助手 - 支持股票分析和金融知识查询')
    
    # 支持两种模式
    mode_group = parser.add_argument_group('运行模式 (二选一)')
    mode_group.add_argument('--ticker', type=str,
                        help='股票代码或名称 (股票分析模式)')
    mode_group.add_argument('--query', type=str,
                        help='用户查询文本 (会使用意图识别决定处理流程)')
    
    # 股票分析相关参数
    stock_group = parser.add_argument_group('股票分析选项')
    stock_group.add_argument('--start-date', type=str,
                        help='开始日期 (YYYY-MM-DD)，默认为结束日期前一年')
    stock_group.add_argument('--end-date', type=str,
                        help='结束日期 (YYYY-MM-DD)，默认为昨天')
    stock_group.add_argument('--num-of-news', type=int, default=5,
                        help='用于情感分析的新闻文章数量 (默认: 5)')
    stock_group.add_argument('--initial-capital', type=float, default=100000.0,
                        help='初始资金金额 (默认: 100,000)')
    stock_group.add_argument('--initial-position', type=int, default=0,
                        help='初始股票持仓数量 (默认: 0)')
    stock_group.add_argument('--non-interactive', action='store_true',
                        help='非交互模式: 自动选择股票名称的第一个匹配项')
    stock_group.add_argument('--no-report', action='store_true',
                        help='禁用自动生成中文分析报告')
    
    # 通用选项
    common_group = parser.add_argument_group('通用选项')
    common_group.add_argument('--show-reasoning', action='store_true',
                        help='显示每个Agent的推理过程')
    common_group.add_argument('--summary', action='store_true',
                        help='在结束时显示汇总报告')

    args = parser.parse_args()

    # 生成运行ID
    run_id = str(uuid.uuid4())
    print(f"\n=== 新会话开始 [ID: {run_id[:8]}] ===")
    
    # 判断运行模式
    if args.query:
        print(f"\n📝 处理用户查询: '{args.query}'")
        print(f"🔍 正在识别意图...")
        
        # 使用process_user_query处理查询
        final_state = process_user_query(
            run_id=run_id,
            query=args.query,
            show_reasoning=args.show_reasoning
        )
        
        # 提取意图和最终消息
        intent = final_state.get("data", {}).get("intent", "未知")
        print(f"✅ 识别意图: {intent}")
        
        # 打印最终消息
        print("\n" + "="*70)
        print("🤖 最终回复:")
        last_message = final_state["messages"][-1].content if final_state["messages"] else "无回复"
        print(last_message)
        print("="*70 + "\n")
        sys.exit(0)
    
    # 如果没有提供ticker和query，显示错误并退出
    if not args.ticker:
        print("❌ 错误: 必须提供 --ticker 或 --query 参数")
        parser.print_help()
        sys.exit(1)

    # --- 解析输入的股票代码或名称 ---
    print(f"\n🔍 正在处理股票代码/名称: '{args.ticker}'")
    ticker = resolve_stock_input(args.ticker, non_interactive=args.non_interactive)
    print(f"✅ 确认股票代码: {ticker}")

    # --- 日期处理 ---
    current_date = datetime.now()
    yesterday = current_date - timedelta(days=1)
    end_date = yesterday if not args.end_date else min(
        datetime.strptime(args.end_date, '%Y-%m-%d'), yesterday)

    if not args.start_date:
        # 默认为结束日期前一年
        start_date = end_date - timedelta(days=365)
    else:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    # 格式化日期
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    print(f"📅 分析时间范围: {start_date_str} 至 {end_date_str}")

    # --- 投资组合初始化 ---
    portfolio = {
        "cash": args.initial_capital,
        "stock": args.initial_position
    }
    print(f"💰 初始资金: {args.initial_capital}元，初始持仓: {args.initial_position}股")

    # 是否生成中文分析报告
    generate_report = not args.no_report
    if generate_report:
        print("📑 将生成中文分析报告")
    else:
        print("📑 已禁用中文分析报告")

    # --- 运行工作流 ---
    print(f"\n🚀 开始执行股票分析工作流...")
    
    final_state = run_hedge_fund(
        run_id=run_id,
        ticker=ticker,
        start_date=start_date_str,
        end_date=end_date_str,
        portfolio=portfolio,
        show_reasoning=args.show_reasoning,
        num_of_news=args.num_of_news,
        show_summary=args.summary,
        generate_report=generate_report
    )

    # 打印最终决策
    print("\n" + "="*70)
    print("🤖 最终决策:")
    last_message = final_state if isinstance(final_state, str) else \
                  final_state["messages"][-1].content if isinstance(final_state, dict) and final_state.get("messages") else "无决策"
    print(last_message)
    print("="*70)
    print(f"\n=== 会话结束 [ID: {run_id[:8]}] ===\n")

# --- Main Execution Block ---
if __name__ == "__main__":
    run_main()

# --- Historical Data Function (remains the same) ---


def get_historical_data(symbol: str) -> pd.DataFrame:
    # ... (keep existing function implementation) ...
    current_date = datetime.now()
    yesterday = current_date - timedelta(days=1)
    end_date = yesterday
    target_start_date = yesterday - timedelta(days=365)

    print(f"\n正在获取 {symbol} 的历史行情数据...")
    print(f"目标开始日期：{target_start_date.strftime('%Y-%m-%d')}")
    print(f"结束日期：{end_date.strftime('%Y-%m-%d')}")

    try:
        df = ak.stock_zh_a_hist(symbol=symbol,
                                period="daily",
                                start_date=target_start_date.strftime(
                                    "%Y%m%d"),
                                end_date=end_date.strftime("%Y%m%d"),
                                adjust="qfq")

        actual_days = len(df)
        target_days = 365

        if actual_days < target_days:
            print(f"提示：实际获取到的数据天数({actual_days}天)少于目标天数({target_days}天)")
            print(f"将使用可获取到的所有数据进行分析")

        print(f"成功获取历史行情数据，共 {actual_days} 条记录\n")
        return df

    except Exception as e:
        print(f"获取历史数据时发生错误: {str(e)}")
        print("将尝试获取最近可用的数据...")

        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily", adjust="qfq")
            print(f"成功获取历史行情数据，共 {len(df)} 条记录\n")
            return df
        except Exception as e:
            print(f"获取历史数据失败: {str(e)}")
            return pd.DataFrame()
