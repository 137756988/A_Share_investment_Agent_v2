#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
财务报告分析助手测试脚本

此脚本用于测试财务报告分析助手功能
"""

import logging
from src.agents.state import AgentState
from src.agents.report_analyzer import report_analyzer_agent
from langchain_core.messages import HumanMessage

# 设置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_report_analyzer")

def test_report_analyzer():
    """测试财务报告分析助手功能"""
    print("=" * 50)
    print("开始测试财务报告分析助手...")
    print("=" * 50)
    
    # 创建测试状态 - 使用TypedDict的正确方式
    state = {
        "messages": [HumanMessage(content="测试报告分析")],
        "data": {"ticker": "301155"},
        "metadata": {"show_reasoning": True}
    }
    
    try:
        # 调用报告分析器
        result = report_analyzer_agent(state)
        
        # 打印结果
        print("=" * 50)
        print("测试结果:")
        print(f"报告保存路径: {result.get('report_file_path', '未找到路径')}")
        print("最后消息:")
        # 如果result是一个包含messages键的字典
        if "messages" in result and result["messages"]:
            last_message = result["messages"][-1]
            # 如果message是一个对象并且有content属性
            if hasattr(last_message, "content"):
                print(last_message.content)
            else:
                print(last_message)
        else:
            print("没有找到消息")
        print("=" * 50)
        
        return True
    except Exception as e:
        logger.error(f"测试失败: {str(e)}")
        print(f"测试失败: {str(e)}")
        return False

if __name__ == "__main__":
    if test_report_analyzer():
        print("✓ 测试通过!")
    else:
        print("✗ 测试失败!") 