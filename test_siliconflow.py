import os
import sys
from dotenv import load_dotenv
from src.utils.llm_clients import SiliconFlowClient

# 加载环境变量
load_dotenv()

def test_standard_output():
    """测试标准输出模式"""
    print("\n===== 测试标准输出 =====")
    
    # 使用API密钥
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        print("❌ 错误: 未找到SILICONFLOW_API_KEY环境变量")
        return False
    
    # 使用免费模型
    model = "Qwen/Qwen2-7B-Instruct"  # 免费模型
    
    print(f"✓ 使用模型: {model}")
    
    # 简单的测试消息
    test_messages = [
        {"role": "system", "content": "你是一个专业的金融分析师。"},
        {"role": "user", "content": "列出中国股市的主要指数，并简要介绍。"}
    ]
    
    print("\n发送API请求中...")
    try:
        # 初始化客户端
        client = SiliconFlowClient(
            api_key=api_key,
            model=model
        )
        
        # 调用API
        content = client.get_completion(
            messages=test_messages,
            max_tokens=200,
            temperature=0.7,
            top_p=0.7,
            frequency_penalty=0.1
        )
        
        if content:
            print("\n✅ 标准输出测试成功!")
            print("=" * 50)
            print(content)
            print("=" * 50)
            return True
        else:
            print("\n❌ API调用失败: 未收到响应")
            return False
    except Exception as e:
        print(f"\n❌ API调用发生错误: {str(e)}")
        return False

def test_streaming_output():
    """测试流式输出模式"""
    print("\n===== 测试流式输出 =====")
    
    # 使用API密钥
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        print("❌ 错误: 未找到SILICONFLOW_API_KEY环境变量")
        return False
    
    # 使用免费模型
    model = "Qwen/Qwen2-7B-Instruct"  # 免费模型
    
    print(f"✓ 使用模型: {model}")
    
    # 简单的测试消息
    test_messages = [
        {"role": "system", "content": "你是一个专业的金融分析师。"},
        {"role": "user", "content": "分析一下当前中国股市的投资机会。"}
    ]
    
    print("\n发送流式API请求中...")
    try:
        # 初始化客户端
        client = SiliconFlowClient(
            api_key=api_key,
            model=model
        )
        
        print("\n✅ 开始接收流式响应:")
        print("=" * 50)
        
        # 方法1：直接使用流式响应功能
        for text_chunk in client.get_streaming_completion(
            messages=test_messages,
            max_tokens=300,
            temperature=0.7,
            top_p=0.7,
            frequency_penalty=0.1
        ):
            # 实时打印每个文本块
            print(text_chunk, end="", flush=True)
        
        print("\n" + "=" * 50)
        print("✅ 流式输出测试成功!")
        return True
    except Exception as e:
        print(f"\n❌ API调用发生错误: {str(e)}")
        return False

def test_with_api_sample():
    """使用API文档中的示例进行测试"""
    print("\n===== 测试API文档示例 =====")
    
    # 使用API密钥
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        print("❌ 错误: 未找到SILICONFLOW_API_KEY环境变量")
        return False
    
    # 使用DeepSeek-V3模型(如果可用，否则回退到免费模型)
    try:
        model = "deepseek-ai/DeepSeek-V3"
        
        print(f"✓ 尝试使用模型: {model}")
        
        # 测试消息
        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Write a haiku about recursion in programming."}
        ]
        
        # 初始化客户端
        client = SiliconFlowClient(
            api_key=api_key,
            model=model
        )
        
        print("\n✅ 开始接收流式响应:")
        print("=" * 50)
        
        # 直接使用方式与API文档中一致，但不使用top_k参数
        response = client.client.chat.completions.create(
            model=model,
            messages=test_messages,
            temperature=0.7,
            max_tokens=1024,
            stream=True,
            top_p=0.7,
            frequency_penalty=0.1
        )
        
        # 逐步接收并处理响应
        for chunk in response:
            if not chunk.choices:
                continue
            if chunk.choices[0].delta.content:
                print(chunk.choices[0].delta.content, end="", flush=True)
            if hasattr(chunk.choices[0].delta, 'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                print(chunk.choices[0].delta.reasoning_content, end="", flush=True)
        
        print("\n" + "=" * 50)
        print("✅ API文档示例测试成功!")
        return True
    except Exception as e:
        print(f"\n❌ 使用DeepSeek-V3模型测试失败: {str(e)}")
        print("尝试使用免费模型重新测试...")
        
        try:
            model = "Qwen/Qwen2-7B-Instruct"  # 免费模型
            print(f"✓ 切换到模型: {model}")
            
            # 测试消息
            test_messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Write a haiku about recursion in programming."}
            ]
            
            # 初始化客户端
            client = SiliconFlowClient(
                api_key=api_key,
                model=model
            )
            
            print("\n✅ 开始接收流式响应:")
            print("=" * 50)
            
            # 使用免费模型的调用方式
            response = client.client.chat.completions.create(
                model=model,
                messages=test_messages,
                temperature=0.7,
                max_tokens=1024,
                stream=True,
                top_p=0.7,
                frequency_penalty=0.1
                # 不使用top_k参数，因为Qwen2-7B可能不支持
            )
            
            # 逐步接收并处理响应
            for chunk in response:
                if not chunk.choices:
                    continue
                if chunk.choices[0].delta.content:
                    print(chunk.choices[0].delta.content, end="", flush=True)
            
            print("\n" + "=" * 50)
            print("✅ 使用免费模型的API文档示例测试成功!")
            return True
        except Exception as e2:
            print(f"\n❌ 使用免费模型测试也失败: {str(e2)}")
            return False

if __name__ == "__main__":
    print("开始测试硅基流动API...")
    success_standard = test_standard_output()
    if not success_standard:
        print("标准输出测试失败，终止测试")
        sys.exit(1)
    
    success_streaming = test_streaming_output()
    if not success_streaming:
        print("流式输出测试失败，终止测试")
        sys.exit(1)
    
    success_api_sample = test_with_api_sample()
    if not success_api_sample:
        print("API文档示例测试失败")
    
    print("\n所有测试完成!")
    sys.exit(0) 