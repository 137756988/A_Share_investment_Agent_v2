# 意图识别与知识查询功能

本文档介绍了A_Share_investment_Agent项目中新增的意图识别与知识查询功能。

## 功能概述

我们为项目添加了两个主要功能：

1. **意图识别**：集成了bert-intent-slot-detector项目，可以识别用户查询的意图，分为两类：
   - `KNOWLEDGE_QUERY`：金融知识查询
   - `STOCK_ANALYSIS`：股票分析查询

2. **知识查询Agent**：添加了专门处理金融知识查询的Agent，不执行股票分析流程，而是直接回答用户的金融知识问题。

## 使用方法

### 命令行方式

1. **使用查询参数**：

```bash
# 金融知识查询
python run_with_backend.py --query "什么是P/E比率？它对投资决策有什么影响？"

# 股票分析查询
python run_with_backend.py --query "分析平安银行的投资价值"
```

2. **意图识别测试**：

```bash
# 测试意图识别
python test_intent_query.py --query "什么是量化投资？" --intent-only

# 测试完整处理流程
python test_intent_query.py --query "分析中国平安的股票"
```

### API方式

项目后端API提供了处理用户查询的端点：

```
POST /query/process
```

请求体示例：
```json
{
  "query": "什么是P/E比率？",
  "show_reasoning": false
}
```

响应示例：
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "query": "什么是P/E比率？",
  "intent": "KNOWLEDGE_QUERY",
  "response": "处理已开始，请通过轮询 /logs/{run_id} 端点查看进度和结果",
  "success": true,
  "message": "意图识别为: KNOWLEDGE_QUERY，处理已在后台启动 (运行ID: 550e8400-e29b-41d4-a716-446655440000)"
}
```

## 项目结构

新增的主要文件：

1. `src/agents/knowledge_query.py` - 金融知识查询Agent
2. `src/utils/intent_detector.py` - 意图识别工具
3. `backend/routers/user_queries.py` - 用户查询API路由
4. `test_intent_query.py` - 测试脚本

修改的文件：

1. `src/main.py` - 添加了知识查询Agent和意图识别逻辑
2. `run_with_backend.py` - 添加了查询参数处理
3. `backend/main.py` - 包含了用户查询路由

## 工作原理

1. 用户提供查询文本
2. 系统使用bert-intent-slot-detector项目进行意图识别
3. 如果识别为`KNOWLEDGE_QUERY`，调用知识查询Agent直接回答问题
4. 如果识别为`STOCK_ANALYSIS`，尝试从查询中提取股票代码或名称，然后执行完整的股票分析流程

## 依赖项

本功能依赖于以下项目：

1. `bert-intent-slot-detector` - 意图识别模型
2. 所有现有的A_Share_investment_Agent依赖项

## 注意事项

1. 意图识别模型需要预先训练好，默认查找路径为：`bert-intent-slot-detector/output_model/FinQA_roberta_wwm_ext_large_20250518_v1`
2. 如果模型不存在，系统将尝试查找最新的模型目录
3. 如果意图识别组件不可用，系统将默认所有查询为股票分析类型 