"""
意图识别工具

此模块集成了BERT-intent-slot-detector项目，用于检测用户查询的意图。
"""

import os
import sys
import logging
import re
from typing import Dict, Any, Optional, Tuple

# 设置日志记录
logger = logging.getLogger("intent_detector")

# 项目路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))  # A_Share_investment_Agent目录

# 添加src目录到系统路径
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.append(src_path)
    logger.info(f"已添加 {src_path} 到系统路径")

# 导入意图识别组件
try:
    from intent_detection.infer import load_model, predict_intent
    
    # 设置模型路径
    model_dir = os.path.join(project_root, "src/intent_detection/output_model/FinQA_roberta_wwm_ext_large_20250518_v1")
    if not os.path.exists(model_dir):
        logger.warning(f"未找到默认模型目录: {model_dir}，将尝试使用最新模型")
        output_model_dir = os.path.join(project_root, "src/intent_detection/output_model")
        if os.path.exists(output_model_dir):
            # 获取最新的模型目录
            model_dirs = [d for d in os.listdir(output_model_dir) if os.path.isdir(os.path.join(output_model_dir, d))]
            if model_dirs:
                model_dir = os.path.join(output_model_dir, model_dirs[-1])
                logger.info(f"使用最新模型目录: {model_dir}")
            else:
                logger.error(f"未找到任何模型目录")
                raise ImportError("意图识别模型不存在")
    
    # 加载意图标签
    intent_label_file = os.path.join(project_root, "src/intent_detection/data/FinQA/intent_labels_FinQA.txt")
    if not os.path.exists(intent_label_file):
        logger.error(f"未找到意图标签文件: {intent_label_file}")
        raise ImportError("意图标签文件不存在")
    
    # 读取意图标签
    with open(intent_label_file, "r", encoding="utf-8") as f:
        INTENT_LABELS = [line.strip() for line in f.readlines()]
    
    logger.info(f"成功导入意图识别组件，意图标签: {INTENT_LABELS}")
    
    # 模型加载状态
    _detector = None
    
except ImportError as e:
    logger.error(f"导入意图识别组件失败: {e}")
    print(f"错误: 导入意图识别模块失败: {e}")
    raise


def get_detector(use_gpu: bool = False) -> Optional[Any]:
    """
    获取或加载意图识别检测器
    
    Args:
        use_gpu: 是否使用GPU进行推理
        
    Returns:
        检测器对象或None（如果加载失败）
    """
    global _detector
    
    # 如果检测器已加载，直接返回
    if _detector is not None:
        return _detector
    
    try:
        logger.info("正在加载意图识别模型...")
        _detector = load_model(model_dir, use_gpu)
        logger.info("✓ 意图识别模型加载成功")
        return _detector
    except Exception as e:
        logger.error(f"加载意图识别模型失败: {e}")
        raise


def detect_intent(text: str) -> Dict[str, Any]:
    """
    检测文本的意图
    
    Args:
        text: 输入文本
        
    Returns:
        包含意图识别结果的字典，格式为:
        {
            "text": 原始文本,
            "domain": 领域,
            "intent": 意图,
            "slots": 槽位信息（可选）
        }
    """
    # 如果文本为空，抛出异常
    if not text:
        logger.error("输入文本为空")
        raise ValueError("输入文本不能为空")
    
    # 获取检测器
    detector = get_detector()
    
    # 调用意图识别
    result = predict_intent(detector, text)
    logger.info(f"意图识别结果: {result['intent']}")
    return result


def extract_stock_info(result: Dict[str, Any]) -> Tuple[str, str, bool]:
    """
    从意图识别结果中提取股票代码或名称
    
    Args:
        result: 意图识别结果字典
        
    Returns:
        Tuple[str, str, bool]: (stock_code, stock_name, has_stock_info)
        - stock_code: 股票代码（如果有）
        - stock_name: 股票名称（如果有）
        - has_stock_info: 是否找到股票信息
    """
    stock_code = ""
    stock_name = ""
    has_stock_info = False
    
    # 只有当意图是股票分析时才提取股票信息
    if result.get("intent") != "STOCK_ANALYSIS":
        logger.info("非股票分析意图，不提取股票信息")
        return stock_code, stock_name, has_stock_info
    
    # 检查是否有槽位信息
    if "slots" not in result:
        logger.warning("意图为股票分析但未找到槽位信息")
        return stock_code, stock_name, has_stock_info
    
    slots = result["slots"]
    
    # 提取股票代码
    if "stock_code" in slots and slots["stock_code"]:
        # 清理股票代码（去除##等噪音）
        raw_code = slots["stock_code"][0] if isinstance(slots["stock_code"], list) else slots["stock_code"]
        stock_code = re.sub(r'[^0-9a-zA-Z]', '', raw_code)
        logger.info(f"从槽位中提取股票代码: {stock_code}")
        has_stock_info = True
    
    # 提取股票名称
    if "stock_name" in slots and slots["stock_name"]:
        stock_name = slots["stock_name"][0] if isinstance(slots["stock_name"], list) else slots["stock_name"]
        logger.info(f"从槽位中提取股票名称: {stock_name}")
        has_stock_info = True
    
    return stock_code, stock_name, has_stock_info