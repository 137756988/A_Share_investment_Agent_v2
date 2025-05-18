#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
股票名称搜索工具

此脚本用于通过股票名称搜索对应的股票代码，然后可以直接运行分析流程
"""

import os
import sys
import argparse
import subprocess
import pandas as pd
import akshare as ak

def search_stock_by_name(stock_name):
    """
    通过股票名称搜索股票代码
    
    Args:
        stock_name: 股票名称或部分名称
        
    Returns:
        匹配的股票信息列表 (代码, 名称)
    """
    try:
        # 获取所有A股股票代码和名称对照表
        df = ak.stock_info_a_code_name()
        
        # 根据名称模糊查询
        result = df[df['name'].str.contains(stock_name)]
        
        if result.empty:
            print(f"未找到包含 '{stock_name}' 的股票，尝试更宽泛的搜索...")
            # 尝试更宽泛的搜索（拆分关键词）
            keywords = stock_name.split()
            for keyword in keywords:
                if len(keyword) >= 2:  # 只搜索长度大于等于2的关键词
                    result = df[df['name'].str.contains(keyword)]
                    if not result.empty:
                        print(f"通过关键词 '{keyword}' 找到以下股票:")
                        break
        
        return result
    except Exception as e:
        print(f"搜索股票时出错: {e}")
        return pd.DataFrame()

def run_analysis(ticker, analysis_type="test", **kwargs):
    """
    根据股票代码运行分析
    
    Args:
        ticker: 股票代码
        analysis_type: 分析类型（"test", "report", "main"）
        **kwargs: 传递给分析脚本的额外参数
    """
    try:
        if analysis_type == "test":
            # 运行测试脚本
            cmd = ["python", "test_report_analyzer.py"]
            # 修改环境变量，传递股票代码
            env = os.environ.copy()
            env["STOCK_TICKER"] = ticker
            subprocess.run(cmd, env=env)
            
        elif analysis_type == "report":
            # 运行报告生成脚本
            cmd = ["python", "run_report_analyzer.py", "--ticker", ticker]
            subprocess.run(cmd)
            
        elif analysis_type == "main":
            # 运行主分析流程
            cmd = ["python", "src/main.py", "--ticker", ticker]
            
            # 添加额外参数
            if kwargs.get("show_reasoning"):
                cmd.append("--show-reasoning")
            if kwargs.get("summary"):
                cmd.append("--summary")
            if kwargs.get("no_report"):
                cmd.append("--no-report")
                
            subprocess.run(cmd)
            
        else:
            print(f"未知的分析类型: {analysis_type}")
            
    except Exception as e:
        print(f"运行分析时出错: {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='通过股票名称搜索并分析')
    parser.add_argument('stock_name', type=str, help='股票名称或关键词')
    parser.add_argument('--type', '-t', choices=['test', 'report', 'main'], 
                        default='report', help='分析类型 (默认: report)')
    parser.add_argument('--show-reasoning', action='store_true',
                        help='显示分析推理过程 (仅用于main类型)')
    parser.add_argument('--summary', action='store_true',
                        help='显示分析摘要 (仅用于main类型)')
    parser.add_argument('--no-report', action='store_true',
                        help='不生成报告 (仅用于main类型)')
    
    args = parser.parse_args()
    
    # 搜索股票
    result = search_stock_by_name(args.stock_name)
    
    if result.empty:
        print(f"未找到与 '{args.stock_name}' 匹配的股票")
        return 1
    
    # 显示匹配的股票
    print("\n找到以下匹配的股票:")
    for i, (_, row) in enumerate(result.iterrows()):
        print(f"{i+1}. {row['code']} - {row['name']}")
    
    # 如果只有一个匹配项，自动选择
    if len(result) == 1:
        selected_index = 0
        print(f"\n自动选择唯一匹配项: {result.iloc[0]['code']} - {result.iloc[0]['name']}")
    else:
        # 用户选择
        try:
            selected_index = int(input("\n请选择要分析的股票编号: ")) - 1
            if selected_index < 0 or selected_index >= len(result):
                print("无效的选择")
                return 1
        except ValueError:
            print("请输入有效的数字")
            return 1
    
    # 获取选中的股票代码
    selected_ticker = result.iloc[selected_index]['code']
    selected_name = result.iloc[selected_index]['name']
    
    print(f"\n开始分析股票: {selected_ticker} - {selected_name}")
    
    # 运行分析
    run_analysis(
        selected_ticker, 
        args.type,
        show_reasoning=args.show_reasoning,
        summary=args.summary,
        no_report=args.no_report
    )
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 