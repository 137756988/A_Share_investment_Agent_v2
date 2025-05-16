import os
import time
import backoff
from abc import ABC, abstractmethod
from dotenv import load_dotenv
from openai import OpenAI
# from google import genai
from src.utils.logging_config import setup_logger, SUCCESS_ICON, ERROR_ICON, WAIT_ICON

# 设置日志记录
logger = setup_logger('llm_clients')


class LLMClient(ABC):
    """LLM 客户端抽象基类"""

    @abstractmethod
    def get_completion(self, messages, **kwargs):
        """获取模型回答"""
        pass


class GeminiClient(LLMClient):
    """Google Gemini API 客户端"""

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        if not self.api_key:
            logger.error(f"{ERROR_ICON} 未找到 GEMINI_API_KEY 环境变量")
            raise ValueError(
                "GEMINI_API_KEY not found in environment variables")

        # 初始化 Gemini 客户端
        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"{SUCCESS_ICON} Gemini 客户端初始化成功")

    @backoff.on_exception(
        backoff.expo,
        (Exception),
        max_tries=5,
        max_time=300,
        giveup=lambda e: "AFC is enabled" not in str(e)
    )
    def generate_content_with_retry(self, contents, config=None):
        """带重试机制的内容生成函数"""
        try:
            logger.info(f"{WAIT_ICON} 正在调用 Gemini API...")
            logger.debug(f"请求内容: {contents}")
            logger.debug(f"请求配置: {config}")

            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )

            logger.info(f"{SUCCESS_ICON} API 调用成功")
            logger.debug(f"响应内容: {response.text[:500]}...")
            return response
        except Exception as e:
            error_msg = str(e)
            if "location" in error_msg.lower():
                logger.info(
                    f"\033[91m❗ Gemini API 地理位置限制错误: 请使用美国节点VPN后重试\033[0m")
                logger.error(f"详细错误: {error_msg}")
            elif "AFC is enabled" in error_msg:
                logger.warning(
                    f"{ERROR_ICON} 触发 API 限制，等待重试... 错误: {error_msg}")
                time.sleep(5)
            else:
                logger.error(f"{ERROR_ICON} API 调用失败: {error_msg}")
            raise e

    def get_completion(self, messages, max_retries=3, initial_retry_delay=1, **kwargs):
        """获取聊天完成结果，包含重试逻辑"""
        try:
            logger.info(f"{WAIT_ICON} 使用 Gemini 模型: {self.model}")
            logger.debug(f"消息内容: {messages}")

            for attempt in range(max_retries):
                try:
                    # 转换消息格式
                    prompt = ""
                    system_instruction = None

                    for message in messages:
                        role = message["role"]
                        content = message["content"]
                        if role == "system":
                            system_instruction = content
                        elif role == "user":
                            prompt += f"User: {content}\n"
                        elif role == "assistant":
                            prompt += f"Assistant: {content}\n"

                    # 准备配置
                    config = {}
                    if system_instruction:
                        config['system_instruction'] = system_instruction

                    # 调用 API
                    response = self.generate_content_with_retry(
                        contents=prompt.strip(),
                        config=config
                    )

                    if response is None:
                        logger.warning(
                            f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries}: API 返回空值")
                        if attempt < max_retries - 1:
                            retry_delay = initial_retry_delay * (2 ** attempt)
                            logger.info(
                                f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        return None

                    logger.debug(f"API 原始响应: {response.text}")
                    logger.info(f"{SUCCESS_ICON} 成功获取 Gemini 响应")

                    # 直接返回文本内容
                    return response.text

                except Exception as e:
                    logger.error(
                        f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries} 失败: {str(e)}")
                    if attempt < max_retries - 1:
                        retry_delay = initial_retry_delay * (2 ** attempt)
                        logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"{ERROR_ICON} 最终错误: {str(e)}")
                        return None

        except Exception as e:
            logger.error(f"{ERROR_ICON} get_completion 发生错误: {str(e)}")
            return None


class OpenAICompatibleClient(LLMClient):
    """OpenAI 兼容 API 客户端"""

    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.getenv("OPENAI_COMPATIBLE_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_COMPATIBLE_BASE_URL")
        self.model = model or os.getenv("OPENAI_COMPATIBLE_MODEL")

        if not self.api_key:
            logger.error(f"{ERROR_ICON} 未找到 OPENAI_COMPATIBLE_API_KEY 环境变量")
            raise ValueError(
                "OPENAI_COMPATIBLE_API_KEY not found in environment variables")

        if not self.base_url:
            logger.error(f"{ERROR_ICON} 未找到 OPENAI_COMPATIBLE_BASE_URL 环境变量")
            raise ValueError(
                "OPENAI_COMPATIBLE_BASE_URL not found in environment variables")

        if not self.model:
            logger.error(f"{ERROR_ICON} 未找到 OPENAI_COMPATIBLE_MODEL 环境变量")
            raise ValueError(
                "OPENAI_COMPATIBLE_MODEL not found in environment variables")

        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        logger.info(f"{SUCCESS_ICON} OpenAI Compatible 客户端初始化成功")

    @backoff.on_exception(
        backoff.expo,
        (Exception),
        max_tries=5,
        max_time=300
    )
    def call_api_with_retry(self, messages, stream=False):
        """带重试机制的 API 调用函数"""
        try:
            logger.info(f"{WAIT_ICON} 正在调用 OpenAI Compatible API...")
            logger.debug(f"请求内容: {messages}")
            logger.debug(f"模型: {self.model}, 流式: {stream}")

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=stream
            )

            logger.info(f"{SUCCESS_ICON} API 调用成功")
            return response
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{ERROR_ICON} API 调用失败: {error_msg}")
            raise e

    def get_completion(self, messages, max_retries=3, initial_retry_delay=1, **kwargs):
        """获取聊天完成结果，包含重试逻辑"""
        try:
            logger.info(f"{WAIT_ICON} 使用 OpenAI Compatible 模型: {self.model}")
            logger.debug(f"消息内容: {messages}")

            for attempt in range(max_retries):
                try:
                    # 调用 API
                    response = self.call_api_with_retry(messages)

                    if response is None:
                        logger.warning(
                            f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries}: API 返回空值")
                        if attempt < max_retries - 1:
                            retry_delay = initial_retry_delay * (2 ** attempt)
                            logger.info(
                                f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        return None

                    # 打印调试信息
                    content = response.choices[0].message.content
                    logger.debug(f"API 原始响应: {content[:500]}...")
                    logger.info(f"{SUCCESS_ICON} 成功获取 OpenAI Compatible 响应")

                    # 直接返回文本内容
                    return content

                except Exception as e:
                    logger.error(
                        f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries} 失败: {str(e)}")
                    if attempt < max_retries - 1:
                        retry_delay = initial_retry_delay * (2 ** attempt)
                        logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"{ERROR_ICON} 最终错误: {str(e)}")
                        return None

        except Exception as e:
            logger.error(f"{ERROR_ICON} get_completion 发生错误: {str(e)}")
            return None


class SiliconFlowClient(LLMClient):
    """硅基流动 API 客户端，支持调用硅基流动平台上的模型，如DeepSeek-V3和Qwen系列"""

    def __init__(self, api_key=None, model=None, base_url=None):
        """初始化硅基流动客户端
        
        Args:
            api_key: API密钥，如果为None，则从环境变量SILICONFLOW_API_KEY获取
            model: 模型名称，如果为None，则从环境变量SILICONFLOW_MODEL获取，默认为Qwen/Qwen2-7B-Instruct
            base_url: API基础URL，如果为None，则从环境变量SILICONFLOW_BASE_URL获取，默认为https://api.siliconflow.cn/v1
        """
        # 加载环境变量
        load_dotenv()
        
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        self.model = model or os.getenv("SILICONFLOW_MODEL", "Qwen/Qwen2-7B-Instruct")
        self.base_url = base_url or os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

        if not self.api_key:
            logger.error(f"{ERROR_ICON} 未找到 SILICONFLOW_API_KEY 环境变量")
            raise ValueError(
                "SILICONFLOW_API_KEY not found in environment variables")

        # 初始化 OpenAI 客户端（硅基流动兼容OpenAI接口格式）
        self.client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
        logger.info(f"{SUCCESS_ICON} SiliconFlow 客户端初始化成功")
        logger.info(f"{SUCCESS_ICON} 使用模型: {self.model}")
        logger.info(f"{SUCCESS_ICON} API地址: {self.base_url}")

    @backoff.on_exception(
        backoff.expo,
        (Exception),
        max_tries=5,
        max_time=300
    )
    def call_api_with_retry(self, messages, stream=False, **kwargs):
        """带重试机制的 API 调用函数
        
        Args:
            messages: 消息列表
            stream: 是否使用流式输出
            **kwargs: 其他参数
            
        Returns:
            API响应内容
        """
        try:
            logger.info(f"{WAIT_ICON} 正在调用 SiliconFlow API...")
            logger.debug(f"请求内容: {messages}")
            logger.debug(f"模型: {self.model}, 流式: {stream}")
            
            # 构建API参数
            params = {
                "model": self.model,
                "messages": messages,
                "stream": stream,
                "max_tokens": kwargs.get("max_tokens", 1024),
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 0.7),
                "frequency_penalty": kwargs.get("frequency_penalty", 0.1),
                "response_format": {"type": "text"}
            }
            
            # 添加可选参数
            if "top_k" in kwargs:
                params["top_k"] = kwargs["top_k"]
            if "presence_penalty" in kwargs:
                params["presence_penalty"] = kwargs["presence_penalty"]
            if "stop" in kwargs and kwargs["stop"] is not None:
                params["stop"] = kwargs["stop"]
            if "n" in kwargs:
                params["n"] = kwargs["n"]
            # 硅基流动特有参数
            if "enable_thinking" in kwargs:
                params["enable_thinking"] = kwargs["enable_thinking"]
            if "thinking_budget" in kwargs:
                params["thinking_budget"] = kwargs["thinking_budget"]
            if "min_p" in kwargs:
                params["min_p"] = kwargs["min_p"]
            if "tools" in kwargs and kwargs["tools"] is not None:
                params["tools"] = kwargs["tools"]
            
            # 调用API
            response = self.client.chat.completions.create(**params)
            
            logger.info(f"{SUCCESS_ICON} API 调用成功")
            return response
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{ERROR_ICON} API 调用失败: {error_msg}")
            
            # 详细错误日志
            if "Completions.create() got an unexpected keyword argument" in error_msg:
                logger.error(f"{ERROR_ICON} 参数不兼容：当前模型不支持某个参数，请检查模型文档")
            elif "The selected model requires paid balance" in error_msg:
                logger.error(f"{ERROR_ICON} 模型付费错误：当前模型需要付费，请切换到免费模型或充值")
            
            raise e

    def get_completion(self, messages, max_retries=3, initial_retry_delay=1, **kwargs):
        """获取聊天完成结果，包含重试逻辑
        
        Args:
            messages: 消息列表
            max_retries: 最大重试次数
            initial_retry_delay: 初始重试延迟（秒）
            **kwargs: 其他参数，直接传递给API
            
        Returns:
            模型回答内容或None（如果出错）
        """
        try:
            logger.info(f"{WAIT_ICON} 使用 SiliconFlow 模型: {self.model}")
            
            # 是否使用流式输出
            stream = kwargs.pop("stream", False)  # 使用pop而不是get，避免参数重复
            
            for attempt in range(max_retries):
                try:
                    # 调用 API，传递额外参数
                    response = self.call_api_with_retry(messages, stream=stream, **kwargs)
                    
                    if response is None:
                        logger.warning(f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries}: API 返回空值")
                        if attempt < max_retries - 1:
                            retry_delay = initial_retry_delay * (2 ** attempt)
                            logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                            time.sleep(retry_delay)
                            continue
                        return None
                    
                    # 处理流式响应
                    if stream:
                        logger.info(f"{SUCCESS_ICON} 收到流式响应，返回流对象")
                        return response  # 直接返回流对象，由调用者处理
                    
                    # 处理普通响应
                    content = response.choices[0].message.content
                    logger.debug(f"API 响应内容: {content[:500]}...")
                    logger.info(f"{SUCCESS_ICON} 成功获取 SiliconFlow 响应")
                    
                    return content
                    
                except Exception as e:
                    logger.error(f"{ERROR_ICON} 尝试 {attempt + 1}/{max_retries} 失败: {str(e)}")
                    if attempt < max_retries - 1:
                        retry_delay = initial_retry_delay * (2 ** attempt)
                        logger.info(f"{WAIT_ICON} 等待 {retry_delay} 秒后重试...")
                        time.sleep(retry_delay)
                    else:
                        logger.error(f"{ERROR_ICON} 达到最大重试次数，最终错误: {str(e)}")
                        return None
                        
        except Exception as e:
            logger.error(f"{ERROR_ICON} get_completion 发生错误: {str(e)}")
            return None
            
    def get_streaming_completion(self, messages, **kwargs):
        """获取流式响应，提供更直观的接口处理流式输出
        
        Args:
            messages: 消息列表
            **kwargs: 其他参数
            
        Returns:
            生成器，每次产生响应的一部分
        """
        # 设置流式标志但不直接放入kwargs，而是在get_completion中处理
        kwargs["stream"] = True
        response = self.get_completion(messages, **kwargs)
        
        if response is None:
            logger.error(f"{ERROR_ICON} 获取流式响应失败")
            return None
            
        try:
            for chunk in response:
                if not chunk.choices:
                    continue
                # 返回内容部分
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
                # 返回思考过程部分（如果有）
                if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                    yield chunk.choices[0].delta.reasoning_content
        except Exception as e:
            logger.error(f"{ERROR_ICON} 处理流式响应时发生错误: {str(e)}")
            return None


class LLMClientFactory:
    """LLM 客户端工厂类"""

    @staticmethod
    def create_client(client_type="auto", **kwargs):
        """
        创建 LLM 客户端

        Args:
            client_type: 客户端类型 ("auto", "gemini", "openai_compatible", "siliconflow")
            **kwargs: 特定客户端的配置参数

        Returns:
            LLMClient: 实例化的 LLM 客户端
        """
        # 如果设置为 auto，自动检测可用的客户端
        if client_type == "auto":
            # 优先检查是否提供了 SiliconFlow API 相关配置
            if os.getenv("SILICONFLOW_API_KEY"):
                client_type = "siliconflow"
                logger.info(f"{WAIT_ICON} 自动选择 SiliconFlow API")
            # 其次检查是否提供了 OpenAI Compatible API 相关配置
            elif (kwargs.get("api_key") and kwargs.get("base_url") and kwargs.get("model")) or \
               (os.getenv("OPENAI_COMPATIBLE_API_KEY") and os.getenv("OPENAI_COMPATIBLE_BASE_URL") and os.getenv("OPENAI_COMPATIBLE_MODEL")):
                client_type = "openai_compatible"
                logger.info(f"{WAIT_ICON} 自动选择 OpenAI Compatible API")
            else:
                client_type = "gemini"
                logger.info(f"{WAIT_ICON} 自动选择 Gemini API")

        if client_type == "gemini":
            return GeminiClient(
                api_key=kwargs.get("api_key"),
                model=kwargs.get("model")
            )
        elif client_type == "openai_compatible":
            return OpenAICompatibleClient(
                api_key=kwargs.get("api_key"),
                base_url=kwargs.get("base_url"),
                model=kwargs.get("model")
            )
        elif client_type == "siliconflow":
            return SiliconFlowClient(
                api_key=kwargs.get("api_key"),
                model=kwargs.get("model"),
                base_url=kwargs.get("base_url")
            )
        else:
            raise ValueError(f"不支持的客户端类型: {client_type}")
