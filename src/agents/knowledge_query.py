"""
金融知识查询 Agent

此 Agent 负责回答用户关于金融领域的知识性问题，而不执行股票分析操作。
当意图识别系统将用户查询分类为 KNOWLEDGE_QUERY 时调用此 Agent。
"""

import os
import re
import logging
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage
from src.agents.state import AgentState
from src.tools.openrouter_config import get_chat_completion
from src.utils.api_utils import agent_endpoint

# 设置日志记录
logger = logging.getLogger("knowledge_query_agent")

@agent_endpoint("knowledge_query", "金融知识查询助手，负责解答金融领域的知识性问题")
def knowledge_query_agent(state: AgentState) -> AgentState:
    """
    回答金融领域的知识性问题
    
    Args:
        state: 当前Agent状态对象
        
    Returns:
        更新后的状态对象，包含对问题的回答
    """
    print("\n=== 知识查询Agent开始执行 ===")
    
    # 获取用户查询
    messages = state.get("messages", [])
    
    # 提取最后一条用户消息作为查询
    user_query = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_query = msg.content
            break
    
    if not user_query:
        # 如果没有找到用户查询，返回错误消息
        print("❌ 错误：没有找到有效的用户查询")
        response_message = HumanMessage(content="没有找到有效的用户查询，请提供一个金融相关的问题。")
        messages.append(response_message)
        return {
            "messages": messages,
            "data": state.get("data", {}),
            "metadata": state.get("metadata", {})
        }
    
    print(f"📝 用户查询: '{user_query}'")
    logger.info(f"处理金融知识查询: '{user_query}'")
    
    # 构建提示词
    system_prompt = """你是一位金融领域的专业知识助手，专注于帮助用户解答各种金融相关问题。
你的知识涵盖股票市场、债券、基金、衍生品、宏观经济、财务分析、投资策略、风险管理等多个金融领域。
请提供准确、清晰且有深度的回答，必要时引用相关金融理论、概念或研究。
回答应该简洁明了、重点突出，避免冗长或偏离主题。
对于不确定的信息，应明确表示不确定性。
对于超出金融领域的问题，礼貌地告知用户并建议他们咨询相关领域的专家。
"""

    print("🔄 正在调用LLM生成回答...")
    
    # 调用LLM进行回答
    try:
        print("🔍 使用模型: SiliconFlow")
        print("⏳ 正在处理请求，这可能需要一些时间...")
        
        response = get_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            max_tokens=2000,
            temperature=0.3,
            client_type="siliconflow"  # 显式指定使用硅基流动API
        )
        
        if response:
            print("✅ 成功获取知识查询回答")
            print(f"📊 回答长度: {len(response) if response else 0}字符")
            # 打印回答的前100个字符作为预览
            if response and len(response) > 100:
                print(f"💬 回答预览: {response[:100]}...")
            logger.info("✓ 成功获取知识查询回答")
        else:
            print("❌ 获取回答失败: API返回空值")
    except Exception as e:
        error_message = str(e)
        print(f"❌ 调用LLM出错: {error_message}")
        logger.error(f"调用LLM进行知识查询回答时出错: {e}")
        response = f"很抱歉，在处理您的查询时遇到了技术问题: {e}。请稍后再试或重新表述您的问题。"
    
    # 创建回复消息
    response_message = HumanMessage(content=response)
    messages.append(response_message)
    
    # 更新状态数据
    data = state.get("data", {})
    data["knowledge_query"] = user_query
    data["knowledge_response"] = response
    
    print("=== 知识查询Agent执行完成 ===\n")
    
    # 返回更新后的状态
    return {
        "messages": messages,
        "data": data,
        "metadata": state.get("metadata", {})
    } 