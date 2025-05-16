#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
财务报告分析助手独立脚本

此脚本用于独立运行财务报告分析，将投资分析报告翻译成中文并提供解读
"""

import os
import logging
import argparse
from datetime import datetime
from src.agents.state import AgentState
from src.agents.report_analyzer import report_analyzer_agent
from langchain_core.messages import HumanMessage

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("run_report_analyzer")

def main():
    """主函数：解析参数并执行分析流程"""
    parser = argparse.ArgumentParser(description='分析投资报告并生成中文解读')
    parser.add_argument('--ticker', type=str, required=True,
                        help='股票代码')
    parser.add_argument('--output-dir', type=str, default="result",
                        help='输出目录 (默认: result)')
    
    args = parser.parse_args()
    
    # 创建状态 - 使用TypedDict的正确方式
    state = {
        "messages": [HumanMessage(content="生成投资报告解读")],
        "data": {"ticker": args.ticker},
        "metadata": {"show_reasoning": True}
    }
    
    # 确保输出目录存在
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 执行报告分析
    print(f"开始分析股票 {args.ticker} 的投资报告...")
    result = report_analyzer_agent(state)
    
    # 打印结果
    if "data" in result and "report_file_path" in result["data"]:
        print(f"✓ 分析完成，报告已保存至: {result['data']['report_file_path']}")
    else:
        print("✗ 分析未完成，未生成报告文件")
    
    return 0

if __name__ == "__main__":
    try:
        exit(main())
    except Exception as e:
        logger.error(f"执行失败: {str(e)}")
        exit(1) 