#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
简化版金融意图识别推理脚本
功能：接收用户输入，识别其意图和领域
"""

import os
import sys
import torch
import json
import argparse
from transformers import BertTokenizer, BertConfig

# 添加当前目录到系统路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# 标签路径
intent_label_file = os.path.join(SCRIPT_DIR, "data/FinQA/intent_labels_FinQA.txt")
slot_label_file = os.path.join(SCRIPT_DIR, "data/FinQA/slot_labels_FinQA.txt")

# 训练后的模型路径
model_dir = os.path.join(SCRIPT_DIR, "output_model/FinQA_roberta_wwm_ext_large_20250518_v1")

# 导入项目中的模型和数据处理类
from models import JointBert
from detector import JointIntentSlotDetector
from labeldict import LabelDict


# tokenizer 默认选择 hfl/chinese-roberta-wwm-ext-large的
def load_model(model_dir, use_gpu=False):
    """
    加载模型和相关资源
    
    参数:
        model_dir: 模型目录路径
        use_gpu: 是否使用GPU
    
    返回:
        detector: 加载好的检测器对象
    """    
    # 设置设备
    device = torch.device("cuda" if torch.cuda.is_available() and use_gpu else "cpu")
    
    # 加载分词器
    tokenizer_path = os.path.join(model_dir, "tokenizer")
    
    # 查找最新的模型epoch
    model_path = os.path.join(model_dir, "model")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"模型目录不存在: {model_path}")
        
    # 查找最新的epoch
    epoch_dirs = [d for d in os.listdir(model_path) if d.startswith("model_epoch")]
    if not epoch_dirs:
        raise FileNotFoundError(f"在 {model_path} 中未找到任何epoch模型")
        
    # 获取最大的epoch数
    latest_epoch = max([int(d.replace("model_epoch", "")) for d in epoch_dirs])
    latest_model_dir = os.path.join(model_path, f"model_epoch{latest_epoch}")
    
    # 使用JointIntentSlotDetector的from_pretrained方法加载模型
    detector = JointIntentSlotDetector.from_pretrained(
        model_path=latest_model_dir,
        tokenizer_path=tokenizer_path,
        intent_label_path=intent_label_file,
        slot_label_path=slot_label_file,
        use_cuda=use_gpu
    )
    
    print(f"模型已加载，使用设备: {device}")
    print(f"模型路径: {latest_model_dir}")
    print(f"意图标签数量: {len(detector.intent_dict)}")
    print(f"槽位标签数量: {len(detector.slot_dict)}")
    
    return detector

def predict_intent(detector, text):
    """
    预测文本的意图和领域
    
    参数:
        detector: 检测器对象
        text: 输入文本
    
    返回:
        dict: 包含预测结果的字典
    """
    # 使用detector的detect方法直接预测
    detection_result = detector.detect(text)
    
    # 构建简化版结果
    result = {
        "text": text,
        "domain": "finance",  # 固定为金融领域
        "intent": detection_result["intent"]
    }
    
    # 如果有槽位信息，也包含进来
    if detection_result["slots"]:
        result["slots"] = detection_result["slots"]
        
    return result

def interactive_mode(detector):
    """
    交互模式，持续接收用户输入并分析
    
    参数:
        detector: 检测器对象
    """
    print("=" * 50)
    print("金融意图识别系统")
    print("输入'exit'或'quit'退出程序")
    print("=" * 50)
    
    while True:
        try:
            text = input("\n请输入查询文本: ")
            if text.lower() in ["exit", "quit"]:
                break
                
            if not text.strip():
                continue
                
            # 预测意图
            result = predict_intent(detector, text)
            
            # 打印结果
            print("\n预测结果:")
            print(f"文本: {result['text']}")
            print(f"领域: {result['domain']}")
            print(f"意图: {result['intent']}")
            
            # 如果有槽位，也打印出来
            if "slots" in result:
                print("槽位信息:")
                for slot_name, slot_values in result["slots"].items():
                    if isinstance(slot_values, list):
                        slot_value = ", ".join(slot_values)
                    else:
                        slot_value = slot_values
                    print(f"  - {slot_name}: {slot_value}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"发生错误: {e}")
    
    print("\n感谢使用，再见！")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="简化版金融意图识别工具")
    parser.add_argument("--model_dir", type=str, 
                      default=model_dir,
                      help="模型目录路径")
    parser.add_argument("--use_gpu", action="store_true", help="使用GPU进行推理")
    parser.add_argument("--text", type=str, help="要分析的文本，如不提供则进入交互模式")
    
    args = parser.parse_args()
    
    try:
        # 加载模型
        print("正在加载模型...")
        detector = load_model(args.model_dir, args.use_gpu)
        print("模型加载完成!")
        
        if args.text:
            # 单次查询模式
            result = predict_intent(detector, args.text)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            # 交互模式
            interactive_mode(detector)
    except Exception as e:
        print(f"错误: {e}")
        print("无法加载模型或进行预测，请检查模型路径和配置。")

if __name__ == "__main__":
    main() 