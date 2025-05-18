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

# --- Logging and Backend Imports ---
from src.utils.output_logger import OutputLogger
# 导入原始函数，但不再进行猴子补丁
from src.tools.openrouter_config import get_chat_completion
from src.utils.llm_interaction_logger import (
    log_agent_execution,
    set_global_log_storage
)
from backend.dependencies import get_log_storage
from backend.main import app as fastapi_app  # Import the FastAPI app

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


# --- Define the Workflow Graph ---
workflow = StateGraph(AgentState)

# Add nodes - Remove explicit log_agent_execution calls
# The @agent_endpoint decorator now handles logging to BaseLogStorage
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
workflow.add_node("report_analyzer_agent", report_analyzer_agent)  # 添加财务报告分析助手节点

# Define the workflow edges (remain unchanged)
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
    # 检查元数据中是否设置了generate_report标志
    if state.get('metadata', {}).get('generate_report', True):
        return "report_analyzer_agent"
    else:
        return END

workflow.add_conditional_edges(
    "portfolio_management_agent",
    router
)

# 报告分析器到结束
workflow.add_edge("report_analyzer_agent", END)

# Compile the workflow graph
app = workflow.compile()


# --- FastAPI Background Task ---
def run_fastapi():
    print("--- Starting FastAPI server in background (port 8000) ---")
    # Note: Change host/port/log_level as needed
    # Disable Uvicorn's own logging config to avoid conflicts with app's logging
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_config=None)


# --- Main Execution Block ---
if __name__ == "__main__":
    # Start FastAPI server in a background thread
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()

    # --- Argument Parsing (remains the same) ---
    parser = argparse.ArgumentParser(
        description='Run the hedge fund trading system')
    # ... (keep existing parser arguments) ...
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol or stock name')
    parser.add_argument('--start-date', type=str,
                        help='Start date (YYYY-MM-DD). Defaults to 1 year before end date')
    parser.add_argument('--end-date', type=str,
                        help='End date (YYYY-MM-DD). Defaults to yesterday')
    parser.add_argument('--show-reasoning', action='store_true',
                        help='Show reasoning from each agent')
    parser.add_argument('--num-of-news', type=int, default=5,
                        help='Number of news articles to analyze for sentiment (default: 5)')
    parser.add_argument('--initial-capital', type=float, default=100000.0,
                        help='Initial cash amount (default: 100,000)')
    parser.add_argument('--initial-position', type=int, default=0,
                        help='Initial stock position (default: 0)')
    parser.add_argument('--summary', action='store_true',
                        help='Show beautiful summary report at the end')
    parser.add_argument('--no-report', action='store_true',
                        help='Disable automatic generation of Chinese analysis report')
    parser.add_argument('--non-interactive', action='store_true',
                        help='Non-interactive mode: automatically select the first match for stock names')

    args = parser.parse_args()

    # --- 解析输入的股票代码或名称 ---
    ticker = resolve_stock_input(args.ticker, non_interactive=args.non_interactive)

    # --- Date Handling (remains the same) ---
    current_date = datetime.now()
    yesterday = current_date - timedelta(days=1)
    end_date = yesterday if not args.end_date else min(
        datetime.strptime(args.end_date, '%Y-%m-%d'), yesterday)

    if not args.start_date:
        # Default to 1 year before end date
        start_date = end_date - timedelta(days=365)
    else:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    # Format dates
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')

    # --- Portfolio Initialization (remains the same) ---
    portfolio = {
        "cash": args.initial_capital,
        "stock": args.initial_position
    }

    # 是否生成中文分析报告
    generate_report = not args.no_report

    # --- Run the Workflow (with run_id) ---
    run_id = str(uuid.uuid4())  # Generate a UUID
    messages = run_hedge_fund(
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

    # Print final message
    print("\n" + "="*70)
    print("FINAL DECISION:")
    print(messages)
    print("="*70)

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
