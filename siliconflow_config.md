# 硅基流动API配置指南

## 1. 配置环境变量
请将以下配置添加到项目根目录的`.env`文件中：

```
# 硅基流动API配置 (必需)
SILICONFLOW_API_KEY=your_api_key_here

# 硅基流动模型选择 (可选，下面是几个常用模型)
SILICONFLOW_MODEL=Pro/deepseek-ai/DeepSeek-R1
# 或
# SILICONFLOW_MODEL=Qwen/Qwen2-7B-Instruct  # 推荐使用的免费模型
# SILICONFLOW_MODEL=Qwen/QwQ-32B
# SILICONFLOW_MODEL=deepseek-ai/deepseek-vl2

# 硅基流动API地址 (可选，默认为https://api.siliconflow.cn/v1)
# SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
```

## 2. 获取API Key
1. 打开硅基流动官网(https://cloud.siliconflow.cn/)并注册/登录
2. 完成注册后，打开API密钥页面(https://cloud.siliconflow.cn/account/ak)
3. 创建新的API Key，并复制到环境变量文件中

## 3. 使用硅基流动模型
在代码中调用硅基流动模型有多种方式：

### 方式一：直接指定客户端类型
```python
from src.tools.openrouter_config import get_chat_completion

response = get_chat_completion(
    messages=[
        {"role": "system", "content": "你是一个专业的金融分析师。"},
        {"role": "user", "content": "分析最近市场波动的原因"}
    ],
    client_type="siliconflow",  # 明确指定使用硅基流动
    
    # 可选参数
    max_tokens=512,       # 生成的最大token数
    temperature=0.7,      # 温度参数，控制随机性
    top_p=0.7,            # top-p采样
    top_k=50,             # top-k采样
    frequency_penalty=0.5,# 频率惩罚
    enable_thinking=False,# 是否启用思考过程
    thinking_budget=4096, # 思考过程的最大token数
    min_p=0.05            # 最小概率阈值
)
```

### 方式二：通过环境变量自动选择
只需确保设置了SILICONFLOW_API_KEY环境变量，系统将优先选择硅基流动API：

```python
from src.tools.openrouter_config import get_chat_completion

response = get_chat_completion(
    messages=[
        {"role": "system", "content": "你是一个专业的金融分析师。"},
        {"role": "user", "content": "分析最近市场波动的原因"}
    ]
    # 不需要指定client_type，将自动选择硅基流动
)
```

## 4. 硅基流动API参数说明

以下是常用API参数的说明：

| 参数名 | 类型 | 默认值 | 说明 | 兼容性 |
|--------|------|--------|------|-------|
| model | string | - | 要使用的模型名称 | 全部模型 |
| messages | array | - | 消息数组，包含角色和内容 | 全部模型 |
| stream | boolean | false | 是否流式输出 | 全部模型 |
| max_tokens | integer | 512 | 生成的最大token数 | 全部模型 |
| temperature | number | 0.7 | 温度参数，控制随机性，越高越随机 | 全部模型 |
| top_p | number | 0.7 | 控制Token的概率阈值 | 全部模型 |
| top_k | integer | 50 | 控制每一步仅考虑概率最高的K个Token | QwQ-32B等 |
| frequency_penalty | number | 0.5 | 频率惩罚，减少重复内容 | 全部模型 |
| enable_thinking | boolean | false | 是否启用模型思考过程 | 部分高级模型 |
| thinking_budget | integer | 4096 | 思考过程的最大Token数 | 部分高级模型 |
| min_p | number | 0.05 | 最小概率阈值 | 部分高级模型 |
| n | integer | 1 | 生成的回复数量 | 全部模型 |
| stop | array/string | null | 停止生成的标记 | 全部模型 |
| tools | array | null | 工具调用定义 | DeepSeek-R1, QwQ-32B等 |

> **注意**：不同模型支持的参数可能有所不同。例如，Qwen/Qwen2-7B-Instruct模型不支持top_k参数。在使用时请根据具体模型调整参数。

### 模型与参数兼容性

| 模型类别 | 基本参数 | 高级参数 | 工具功能 |
|---------|---------|---------|---------|
| 免费模型(Qwen2-7B) | ✓ | 部分支持 | ✗ |
| 标准模型(QwQ-32B等) | ✓ | ✓ | ✓ |
| 高级模型(DeepSeek-R1等) | ✓ | ✓ | ✓ |

基本参数：model, messages, max_tokens, temperature, top_p, frequency_penalty  
高级参数：top_k, min_p, enable_thinking, thinking_budget  
工具功能：tools参数支持

### 工具功能使用示例

```python
# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "description": "获取金融市场数据的函数",
            "name": "get_market_data",
            "parameters": {
                "type": "object",
                "properties": {
                    "market": {
                        "type": "string",
                        "description": "市场名称，如'上证'、'深证'等"
                    },
                    "date": {
                        "type": "string",
                        "description": "日期，如'2023-01-01'"
                    }
                },
                "required": ["market"]
            }
        }
    }
]

# 在API调用中使用
response = get_chat_completion(
    messages=[
        {"role": "user", "content": "分析上证指数最近的表现"}
    ],
    client_type="siliconflow",
    model="Qwen/QwQ-32B",  # 使用支持工具功能的模型
    tools=tools  # 传递工具定义
)
```

## 5. 支持的主要模型

硅基流动支持多种大语言模型，包括但不限于：

- **DeepSeek系列**：
  - Pro/deepseek-ai/DeepSeek-R1（**付费模型**，功能全面）
  - deepseek-ai/deepseek-coder-v2（代码生成专用）
  - deepseek-ai/deepseek-vl2（多模态模型）

- **Qwen系列**：
  - Qwen/Qwen2-7B-Instruct（**免费模型**，适合初步测试）
  - Qwen/QwQ-32B（支持工具调用）
  - Qwen/Qwen2-72B-Instruct（高级模型）

- **其他模型**：
  - 01-ai/Yi-VL-34B（多模态模型）
  - ZhipuAI/glm-4（功能全面）

每个模型都有其特点和适用场景，请根据需要选择合适的模型。

## 6. 故障排查

如果遇到连接问题，请检查：

1. API Key是否正确
2. 网络连接是否通畅
3. 模型名称是否正确
4. 检查日志中的详细错误信息
5. 确认所用参数与选择的模型兼容（例如某些模型不支持top_k等参数）
6. 对于工具功能，确保使用支持工具调用的模型，并且工具定义格式正确

详细日志会记录在logs目录下，可以帮助识别具体问题。

## 7. 常见错误及解决方案

| 错误信息 | 可能原因 | 解决方案 |
|---------|---------|---------|
| Completions.create() got an unexpected keyword argument 'top_k' | 所用模型不支持top_k参数 | 删除top_k参数或使用支持该参数的模型 |
| The selected model requires paid balance | 使用了付费模型但无余额 | 切换到免费模型如Qwen/Qwen2-7B-Instruct或充值 |
| Invalid API key | API密钥错误 | 检查API密钥是否正确设置 |
| Connection error | 网络连接问题 | 检查网络连接，确认API地址正确 |

详细日志会记录在logs目录下，可以帮助识别具体问题。 