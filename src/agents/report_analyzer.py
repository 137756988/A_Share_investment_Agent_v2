"""
财务报告分析助手模块

此模块负责解析生成的投资分析报告，将其翻译成中文并提供易于理解的解读
"""

import os
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

# 导入工具和客户端
from src.agents.state import AgentState
from src.tools.openrouter_config import get_chat_completion
from src.utils.api_utils import agent_endpoint

# 设置日志记录
logger = logging.getLogger("report_analyzer_agent")

class ReportSection:
    """报告章节类，用于存储和处理报告中的各个部分"""
    
    def __init__(self, name: str, content: str = "", confidence: Optional[float] = None):
        """
        初始化报告章节
        
        Args:
            name: 章节名称
            content: 章节内容
            confidence: 章节相关的置信度（如有）
        """
        self.name = name
        self.content = content
        self.confidence = confidence
    
    def __str__(self) -> str:
        """返回章节的字符串表示"""
        if self.confidence is not None:
            return f"{self.name} (置信度: {self.confidence:.0%}): {self.content}"
        return f"{self.name}: {self.content}"

def extract_sections(log_content: str) -> List[ReportSection]:
    """
    从结构化日志中提取各个章节
    
    Args:
        log_content: 日志内容文本
        
    Returns:
        提取的报告章节列表
    """
    sections = []
    
    # 定义可能的章节名称和模式
    section_patterns = [
        (r"技术分析.*信号:\s*(\w+).*置信度:\s*(\d+)%", "技术分析"),
        (r"基本面分析.*信号:\s*(\w+).*置信度:\s*(\d+)%", "基本面分析"),
        (r"情感分析.*信号:\s*(\w+).*置信度:\s*(\d+)%", "情感分析"),
        (r"估值分析.*信号:\s*(\w+).*置信度:\s*(\d+)%", "估值分析"),
        (r"多方研究.*置信度:\s*(\d+)%", "多方研究"),
        (r"空方研究.*置信度:\s*(\d+)%", "空方研究"),
        (r"辩论室分析.*信号:\s*(\w+).*置信度:\s*(\d+)%", "辩论室分析"),
        (r"风险管理分析.*最大仓位:\s*[\d\.]+.*风险评分:\s*\d+", "风险管理分析"),
        (r"宏观分析.*宏观环境:\s*(\w+).*对股票影响:\s*(\w+)", "宏观分析"),
        (r"投资组合管理分析.*交易行动:\s*(\w+).*决策信心:\s*(\d+)%", "投资组合管理分析")
    ]
    
    # 提取各个章节
    current_section = None
    current_content = []
    
    lines = log_content.split('\n')
    for line in lines:
        matched = False
        for pattern, section_name in section_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                # 如果已有章节，保存它
                if current_section:
                    sections.append(ReportSection(
                        current_section, 
                        '\n'.join(current_content).strip()
                    ))
                
                # 开始新章节
                current_section = section_name
                current_content = [line]
                matched = True
                break
        
        if not matched and current_section:
            current_content.append(line)
    
    # 添加最后一个章节
    if current_section:
        sections.append(ReportSection(
            current_section, 
            '\n'.join(current_content).strip()
        ))
    
    return sections

def parse_confidence(section_content: str) -> Optional[float]:
    """
    从章节内容中解析置信度
    
    Args:
        section_content: 章节内容文本
        
    Returns:
        解析出的置信度，范围0-1，如未找到则返回None
    """
    confidence_pattern = r"置信度:\s*(\d+)%"
    match = re.search(confidence_pattern, section_content)
    if match:
        confidence_str = match.group(1)
        try:
            return int(confidence_str) / 100.0
        except ValueError:
            return None
    return None

def extract_final_decision(log_content: str) -> Tuple[str, Optional[float]]:
    """
    从日志中提取最终投资决策
    
    Args:
        log_content: 日志内容文本
        
    Returns:
        元组: (决策行动, 置信度)
    """
    decision_pattern = r"交易行动:\s*(\w+).*决策信心:\s*(\d+)%"
    match = re.search(decision_pattern, log_content, re.IGNORECASE)
    if match:
        action = match.group(1)
        confidence = int(match.group(2)) / 100.0
        return action, confidence
    return "未知", None

@agent_endpoint("report_analyzer", "财务报告分析助手，负责翻译解读投资分析报告")
def report_analyzer_agent(state: AgentState) -> AgentState:
    """
    解析投资分析报告，将英文内容翻译成中文并提供解读
    
    Args:
        state: 当前Agent状态对象
        
    Returns:
        更新后的状态对象，包含中文报告内容
    """
    # 获取股票代码
    ticker = state.get("data", {}).get("ticker", "未知股票")
    
    # 读取结构化日志文件（带有股票代码后缀）
    ticker_suffix = f"_{ticker}" if ticker else ""
    log_file_path = f"logs/structured_terminal{ticker_suffix}.log"
    
    log_content = ""
    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()
        logger.info(f"✓ 成功读取日志文件: {log_file_path}")
    except Exception as e:
        # 如果带后缀的文件不存在，尝试读取不带后缀的默认文件
        default_log_path = "logs/structured_terminal.log"
        logger.warning(f"读取带有股票代码后缀的日志文件失败: {e}，尝试读取默认日志文件")
        try:
            with open(default_log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            logger.info(f"✓ 成功读取默认日志文件: {default_log_path}")
        except Exception as e2:
            logger.error(f"读取默认日志文件失败: {e2}")
            # 返回错误消息
            from langchain_core.messages import HumanMessage
            messages = state.get("messages", [])
            messages.append(HumanMessage(content=f"无法读取分析报告日志，请确保先运行股票分析流程: {e2}"))
            return {
                "messages": messages,
                "data": state.get("data", {}),
                "metadata": state.get("metadata", {})
            }
    
    # 提取报告各章节
    try:
        sections = extract_sections(log_content)
        logger.info(f"✓ 已从日志中提取 {len(sections)} 个章节")
        
        # 提取最终决策
        final_action, confidence = extract_final_decision(log_content)
        logger.info(f"✓ 最终决策: {final_action}, 置信度: {confidence}")
    except Exception as e:
        logger.error(f"解析报告章节时出错: {e}")
        sections = []
        final_action, confidence = "未知", None
    
    # 根据股票代码查询股票名称
    stock_name = "未知公司"
    try:
        # 通过API或本地数据获取股票名称
        import akshare as ak
        stock_info = ak.stock_individual_info_em(symbol=ticker)
        if not stock_info.empty:
            stock_name = stock_info.iloc[0, 1] if stock_info.shape[1] > 1 else "未知公司"
        logger.info(f"✓ 获取到股票名称: {stock_name}")
    except Exception as e:
        logger.warning(f"获取股票名称失败: {e}，将使用默认名称")
    
    # 准备提示词
    prompt = f"""
    你是一位专业的金融分析师助手，负责解读A股投资分析报告。
    请将以下投资分析报告翻译成简洁明了的中文，解释各项指标的含义、计算方法和投资建议。
    
    特别要求:
    1. 使用通俗易懂的语言，面向普通投资者
    2. 保留所有关键数据和指标，但用中文解释其含义
    3. 按照原始报告的结构组织内容
    4. 指出各个部分的分析结论之间的关联性
    5. 解释每个指标是如何计算得出的，由哪个模块或代码生成
    6. 以markdown格式输出结果
    7. 对于技术分析部分，需要解释ADX、RSI、布林带等技术指标的含义
    8. 对于估值分析部分，需要解释DCF和所有者收益分析方法的区别
    9. 标题应该包含股票代码和名称
    10. 在报告结尾总结关键投资要点和风险提示
    
    分析目标股票: {ticker} {stock_name}
    最终投资决策: {final_action} {'，置信度 ' + str(int(confidence * 100)) + '%' if confidence is not None else ''}
    
    报告内容:
    {log_content}
    """
    
    # 调用LLM进行翻译和解读
    try:
        report_analysis = get_chat_completion(
            messages=[
                {"role": "system", "content": "你是一位专业的金融分析师助手，擅长翻译和解读投资分析报告。你的任务是将英文分析报告翻译成中文，并解释指标来源和计算方法。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,
            temperature=0.3,
            client_type="siliconflow"  # 显式指定使用硅基流动API
        )
    except Exception as e:
        logger.error(f"调用LLM进行报告分析失败: {e}")
        # 返回错误消息
        from langchain_core.messages import HumanMessage
        messages = state.get("messages", [])
        messages.append(HumanMessage(content=f"调用LLM进行报告分析失败: {e}"))
        return {
            "messages": messages,
            "data": state.get("data", {}),
            "metadata": state.get("metadata", {})
        }
    
    # 保存结果到文件
    output_dir = "result"
    os.makedirs(output_dir, exist_ok=True)
    
    # 文件名包含股票代码、名称和日期
    date_str = datetime.now().strftime('%Y%m%d')
    output_file = os.path.join(output_dir, f"股票{ticker}_{stock_name}_分析报告_{date_str}.md")
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report_analysis)
        logger.info(f"✓ 分析报告已保存至 {output_file}")
    except Exception as e:
        logger.error(f"保存报告失败: {e}")
    
    # 更新数据
    data = state.get("data", {})
    data["report_analysis"] = report_analysis
    data["report_file_path"] = output_file
    data["final_action"] = final_action
    if confidence is not None:
        data["action_confidence"] = confidence
    
    # 添加总结消息
    summary_message = f"已完成股票 {ticker} ({stock_name}) 投资报告的中文翻译和解读，最终投资建议为 {final_action}，结果保存在: {output_file}"
    from langchain_core.messages import HumanMessage
    messages = state.get("messages", [])
    messages.append(HumanMessage(content=summary_message))
    
    # 返回更新后的状态
    return {
        "messages": messages,
        "data": data,
        "metadata": state.get("metadata", {})
    } 