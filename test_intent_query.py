#!/usr/bin/env python
"""
意图识别和查询处理测试脚本

此脚本用于测试项目的意图识别和查询处理功能。
可以用来验证知识查询和股票分析两种意图的处理流程。
"""

import argparse
from src.utils.intent_detector import detect_intent, get_detector
from src.main import process_user_query
import uuid

def test_intent_detection(query):
    """测试意图识别功能"""
    print("\n" + "="*70)
    print(f"测试意图识别: '{query}'")
    print("="*70)
    
    # 加载检测器
    detector = get_detector()
    if not detector:
        print("❌ 无法加载意图识别检测器")
        return False
    
    # 检测意图
    result = detect_intent(query)
    print(f"✓ 识别结果:")
    print(f"  - 文本: {result['text']}")
    print(f"  - 领域: {result['domain']}")
    print(f"  - 意图: {result['intent']}")
    
    # 如果有槽位信息，也打印出来
    if "slots" in result:
        print("  - 槽位信息:")
        for slot_name, slot_values in result["slots"].items():
            if isinstance(slot_values, list):
                slot_value = ", ".join(slot_values)
            else:
                slot_value = slot_values
            print(f"    + {slot_name}: {slot_value}")
    
    return True

def test_query_processing(query):
    """测试查询处理功能"""
    print("\n" + "="*70)
    print(f"测试查询处理: '{query}'")
    print("="*70)
    
    # 生成运行ID
    run_id = str(uuid.uuid4())
    print(f"运行ID: {run_id}")
    
    # 处理查询
    result = process_user_query(
        run_id=run_id,
        query=query,
        show_reasoning=True
    )
    
    # 提取结果
    intent = result.get("data", {}).get("intent", "未知")
    response = result["messages"][-1].content if result["messages"] else "没有响应"
    
    print(f"\n识别意图: {intent}")
    print("\n回答内容:")
    print("-"*70)
    print(response)
    print("-"*70)
    
    return intent, response

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="测试意图识别和查询处理功能")
    parser.add_argument("--query", type=str, required=True, help="用户查询文本")
    parser.add_argument("--intent-only", action="store_true", help="仅测试意图识别")
    
    args = parser.parse_args()
    
    # 测试意图识别
    if not test_intent_detection(args.query):
        print("❌ 意图识别测试失败")
        return
    
    # 如果不是仅测试意图，则测试完整的查询处理
    if not args.intent_only:
        intent, response = test_query_processing(args.query)
        print(f"\n🎯 测试完成: 查询 '{args.query}' 被识别为 '{intent}' 意图，已生成响应")
    else:
        print(f"\n🎯 测试完成: 仅测试了意图识别")

if __name__ == "__main__":
    main() 