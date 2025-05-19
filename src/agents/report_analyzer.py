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
    
    # 定义可能的章节名称和模式（修改为匹配中文模式）
    section_patterns = [
        (r"技术分析.*信号:.*(\w+).*置信度:.*(\d+)%", "技术分析"),
        (r"基本面分析.*信号:.*(\w+).*置信度:.*(\d+)%", "基本面分析"),
        (r"情感分析.*信号:.*(\w+).*置信度:.*(\d+)%", "情感分析"),
        (r"估值分析.*信号:.*(\w+).*置信度:.*(\d+)%", "估值分析"),
        (r"多方研究.*置信度:.*(\d+)%", "多方研究"),
        (r"空方研究.*置信度:.*(\d+)%", "空方研究"),
        (r"辩论室分析.*信号:.*(\w+).*置信度:.*(\d+)%", "辩论室分析"),
        (r"风险管理分析.*最大仓位:.*[\d\.]+.*风险评分:.*\d+", "风险管理分析"),
        (r"宏观分析.*宏观环境:.*(\w+).*影响:.*(\w+)", "宏观分析"),
        (r"投资组合管理分析.*交易行动:.*(\w+).*决策信心:.*(\d+)%", "投资组合管理分析")
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
    
    # 如果未提取到任何章节，尝试提取基于分隔符的章节
    if not sections:
        logger.warning("未使用正则模式提取到任何章节，尝试使用分隔符提取...")
        
        section_markers = [
            "╔═══════════════════════════════════ 📈 技术分析分析 ═══════════════════════════════════╗",
            "╔══════════════════════════════════ 📝 基本面分析分析 ══════════════════════════════════╗",
            "╔═══════════════════════════════════ 🔍 情感分析分析 ═══════════════════════════════════╗",
            "╔═══════════════════════════════════ 💰 估值分析分析 ═══════════════════════════════════╗",
            "╔═══════════════════════════════════ 🐂 多方研究分析 ═══════════════════════════════════╗",
            "╔═══════════════════════════════════ 🐻 空方研究分析 ═══════════════════════════════════╗",
            "╔══════════════════════════════════ 🗣️ 辩论室分析分析 ══════════════════════════════════╗",
            "╔══════════════════════════════════ ⚠️ 风险管理分析 ══════════════════════════════════╗",
            "╔═══════════════════════════════════ 🌍 宏观分析分析 ═══════════════════════════════════╗",
            "╔══════════════════════════════════ 📂 投资组合管理分析 ══════════════════════════════════╗"
        ]
        
        section_names = [
            "技术分析", "基本面分析", "情感分析", "估值分析", 
            "多方研究", "空方研究", "辩论室分析", 
            "风险管理分析", "宏观分析", "投资组合管理分析"
        ]
        
        # 为每个章节查找开始位置和结束位置
        for i, marker in enumerate(section_markers):
            try:
                start_idx = log_content.index(marker)
                end_marker = "╚══════════════════════════════════════════════════════════════════════════════╝"
                end_idx = log_content.find(end_marker, start_idx)
                
                if end_idx > start_idx:
                    section_content = log_content[start_idx:end_idx + len(end_marker)]
                    sections.append(ReportSection(section_names[i], section_content))
                    logger.info(f"找到章节: {section_names[i]}")
            except ValueError:
                continue
    
    return sections

def parse_confidence(section_content: str) -> Optional[float]:
    """
    从章节内容中解析置信度
    
    Args:
        section_content: 章节内容文本
        
    Returns:
        解析出的置信度，范围0-1，如未找到则返回None
    """
    confidence_pattern = r"置信度:.*?(\d+)%"
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
    # 尝试多种模式来匹配决策
    decision_patterns = [
        r"交易行动:.*?(\w+).*?决策信心:.*?(\d+)%",
        r"action\"\s*:\s*\"(\w+)\".*?confidence\"\s*:\s*(\d+)",
        r"action\"\s*:\s*\"(\w+)",
    ]
    
    for pattern in decision_patterns:
        match = re.search(pattern, log_content, re.IGNORECASE)
        if match:
            action = match.group(1)
            try:
                confidence = int(match.group(2)) / 100.0
            except (IndexError, ValueError):
                confidence = None
            return action, confidence
    
    # 如果未找到决策，检查是否有风险管理部分的交易行动
    risk_pattern = r"trading_action\"\s*:\s*\"(\w+)"
    match = re.search(risk_pattern, log_content)
    if match:
        return match.group(1), None
    
    return "观望", None

def ensure_correct_report_title(report_content: str, ticker: str, stock_name: str) -> str:
    """
    确保报告标题包含正确的股票代码和名称
    
    Args:
        report_content: 报告内容
        ticker: 股票代码
        stock_name: 股票名称
        
    Returns:
        修正后的报告内容
    """
    # 确保股票代码和名称是字符串
    ticker = str(ticker)
    stock_name = str(stock_name)
    
    # 防止股票名称为空
    if not stock_name:
        stock_name = "股票"
    
    # 检查报告的第一行是否包含正确的标题
    lines = report_content.split('\n')
    if not lines:
        return report_content
    
    # 预期的标题格式
    expected_title = f"# {ticker} {stock_name}投资分析报告"
    
    # 检查第一个非空行是否是标题行
    title_line_index = -1
    for i, line in enumerate(lines):
        stripped_line = line.strip()
        if stripped_line and stripped_line.startswith('#'):
            title_line_index = i
            break
    
    # 如果找到标题行但不包含正确的股票信息，则替换它
    if title_line_index >= 0:
        current_title = lines[title_line_index]
        # 检查标题中是否包含错误的股票代码或名称
        wrong_stock_info = False
        
        # 使用正则表达式提取标题中的股票代码和名称
        title_match = re.search(r'#\s*(\d{6})\s+([^\s]+)', current_title)
        if title_match:
            title_code = title_match.group(1)
            title_name = title_match.group(2)
            
            # 如果标题中的股票代码不是当前股票代码，或者名称与当前不符（且当前名称不为"股票"）
            if title_code != ticker or (title_name != stock_name and stock_name != "股票"):
                wrong_stock_info = True
                logger.warning(f"检测到标题中的股票信息错误: 标题={current_title}, 应为={expected_title}")
        
        # 如果标题本身不包含足够信息或信息错误，则替换整个标题
        if wrong_stock_info or ticker not in current_title or (stock_name not in current_title and stock_name != "股票"):
            lines[title_line_index] = expected_title
            logger.info(f"已修正报告标题为: {expected_title}")
    else:
        # 如果没有找到标题行，在报告开头添加标题
        lines.insert(0, expected_title)
        lines.insert(1, "")  # 添加空行
        logger.info(f"已添加报告标题: {expected_title}")
    
    # 检查内容中是否有平安银行等特定错误
    corrected_content = '\n'.join(lines)
    
    # 检查并替换平安银行等特定错误
    bank_names = ["平安银行", "工商银行", "中国银行", "浦发银行"]
    for bank_name in bank_names:
        if bank_name != stock_name and bank_name in corrected_content:
            # 仅替换非引用文本中的错误（如替换"平安银行投资分析报告"，但不替换引号内的内容）
            # 注意：替换前检查，确保不会误替换引用内容
            corrected_content = re.sub(
                r'([^"""\'\'\'「」『』\(（]\s*)' + bank_name + r'(\s*[^"""\'\'\'「」『』\)）]|$)', 
                r'\1' + stock_name + r'\2', 
                corrected_content
            )
            logger.info(f"已修正报告中的公司名称: {bank_name} -> {stock_name}")
    
    return corrected_content

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
    
    # 直接从state中获取股票名称(如果有)
    stock_name = state.get("data", {}).get("stock_name", "")
    logger.info(f"从state中获取的股票名称: {stock_name}")
    
    # 读取结构化日志文件（带有股票代码后缀）
    ticker_suffix = f"_{ticker}" if ticker else ""
    log_file_path = f"logs/structured_terminal{ticker_suffix}.log"
    
    log_content = ""
    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()
        logger.info(f"✓ 成功读取日志文件: {log_file_path}")
        
        # 检查日志内容中是否包含该股票的信息
        # 如果日志中包含其他股票代码但不包含当前股票代码，可能使用了错误的日志文件
        if ticker not in log_content and re.search(r'股票代码\s+\d{6}', log_content):
            # 尝试提取日志中的股票代码
            log_ticker_match = re.search(r'股票代码\s+(\d{6})', log_content)
            if log_ticker_match:
                log_ticker = log_ticker_match.group(1)
                if log_ticker != ticker:
                    logger.warning(f"⚠️ 警告: 日志文件中的股票代码 {log_ticker} 与当前分析的股票代码 {ticker} 不匹配")
                    raise ValueError(f"日志文件内容与当前股票不匹配，日志中为 {log_ticker}，当前为 {ticker}")
    except Exception as e:
        # 如果带后缀的文件不存在或内容不匹配，尝试创建一个简化的日志内容
        logger.warning(f"读取带有股票代码后缀的日志文件失败或内容不匹配: {e}")
        
        # 创建一个简单的日志内容模板，包含必要的字段但标记为"数据有限"
        try:
            logger.info(f"尝试创建简化的分析报告内容...")
            
            # 获取股票基本信息
            import akshare as ak
            stock_info = ""
            try:
                # 获取股票实时行情
                realtime_data = ak.stock_zh_a_spot_em()
                stock_row = realtime_data[realtime_data['代码'] == ticker]
                if not stock_row.empty:
                    price = stock_row.iloc[0]['最新价']
                    change_pct = stock_row.iloc[0]['涨跌幅']
                    volume = stock_row.iloc[0]['成交量']
                    stock_info = f"当前价格: {price}, 涨跌幅: {change_pct}%, 成交量: {volume}"
            except Exception as e_info:
                logger.warning(f"获取股票实时行情失败: {e_info}")
                stock_info = "无法获取实时行情"
            
            # 创建简化的日志内容
            log_content = f"""
════════════════════════════════════════════════════════════════════════════════
                               股票代码 {ticker} 投资分析报告                               
════════════════════════════════════════════════════════════════════════════════
                         分析区间: {datetime.now().strftime('%Y-%m-%d')}                          

请注意: 由于无法获取完整的分析日志，此报告仅包含有限的信息。
股票基本信息: {stock_info}

投资决策: 由于数据有限，无法给出明确的投资建议。请获取更多数据后再做决策。
            """
            logger.info(f"✓ 成功创建简化的分析报告内容")
        except Exception as e2:
            logger.error(f"创建简化分析报告内容失败: {e2}")
            # 返回错误消息
            from langchain_core.messages import HumanMessage
            messages = state.get("messages", [])
            messages.append(HumanMessage(content=f"无法读取或创建分析报告内容，请确保先运行股票分析流程: {e}，{e2}"))
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
        final_action, confidence = "观望", None
    
    # 获取股票名称的优先级: 1.state传递 2.API获取 3.映射表 4.默认值
    if not stock_name:
        # 如果状态中没有股票名称，尝试从API获取
        default_stock_name = "未知公司"  # 更改默认名称避免误导
        try:
            # 通过API或本地数据获取股票名称
            import akshare as ak
            try:
                stock_info = ak.stock_individual_info_em(symbol=ticker)
                if not stock_info.empty and stock_info.shape[1] > 1:
                    # 确保获取到的是字符串而不是浮点数
                    name_value = stock_info.iloc[0, 1]
                    if isinstance(name_value, (int, float)):
                        # 如果获取到的是数值，可能是价格，尝试其他方法
                        logger.warning(f"获取到的股票名称似乎是数值: {name_value}，尝试其他方法")
                    else:
                        stock_name = str(name_value)
                        logger.info(f"✓ 从API获取到股票名称: {stock_name}")
            except Exception as e_info:
                logger.warning(f"通过API获取股票信息失败: {e_info}，尝试使用映射表")
                
                # 尝试从常见股票代码映射中获取
                stock_code_map = {
                    "000001": "平安银行",
                    "600000": "浦发银行",
                    "601398": "工商银行",
                    "601988": "中国银行",
                    "600519": "贵州茅台",  # 添加贵州茅台
                    "000858": "五粮液",     # 添加五粮液
                    "601318": "中国平安",   # 添加中国平安
                    "000333": "美的集团",   # 添加美的集团
                    "600036": "招商银行",   # 添加招商银行
                    "601166": "兴业银行",   # 添加兴业银行
                    "600016": "民生银行",   # 添加民生银行
                    "301155": "海力风电",   # 添加海力风电
                    # 可以添加更多映射
                }
                if ticker in stock_code_map:
                    stock_name = stock_code_map[ticker]
                    logger.info(f"✓ 从预定义映射获取股票名称: {stock_name}")
                else:
                    # 尝试获取所有A股股票信息
                    try:
                        all_stocks = ak.stock_info_a_code_name()
                        stock_match = all_stocks[all_stocks['code'] == ticker]
                        if not stock_match.empty:
                            stock_name = stock_match.iloc[0]['name']
                            logger.info(f"✓ 从A股列表获取股票名称: {stock_name}")
                        else:
                            stock_name = default_stock_name
                            logger.warning(f"未找到股票代码 {ticker} 对应的名称，使用默认名称")
                    except Exception as e_all:
                        logger.warning(f"获取A股列表失败: {e_all}，使用默认名称")
                        stock_name = default_stock_name
        except Exception as e:
            logger.warning(f"所有获取股票名称的方法均失败: {e}，使用默认名称: {default_stock_name}")
            stock_name = default_stock_name
    
    logger.info(f"最终使用的股票名称: {stock_name}")
    
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
    9. 标题必须是"# {ticker} {stock_name}投资分析报告"，不要使用其他标题
    10. 在报告结尾总结关键投资要点和风险提示
    11. 最终投资决策必须在"买入"、"观望"、"抛售"三者中选择其一，并在报告结尾明确给出。
    
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
    
    # 确保报告标题正确
    report_analysis = ensure_correct_report_title(report_analysis, ticker, stock_name)
    
    # 保存结果到文件
    output_dir = "result"
    os.makedirs(output_dir, exist_ok=True)
    
    # 文件名包含股票代码和日期，但不含名称以避免路径过长
    date_str = datetime.now().strftime('%Y%m%d')
    price_suffix = ""
    try:
        # 尝试获取当前价格作为文件名后缀
        price_text = ""
        price_pattern = r"当前价格.*?(\d+\.\d+)"
        price_match = re.search(price_pattern, log_content, re.IGNORECASE)
        if price_match:
            price_text = price_match.group(1)
            price_suffix = f"_{price_text}"
    except:
        pass
    
    output_file = os.path.join(output_dir, f"股票{ticker}{price_suffix}_分析报告_{date_str}.md")
    
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