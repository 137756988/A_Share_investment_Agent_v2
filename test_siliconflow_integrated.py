import os
import sys
from dotenv import load_dotenv
from src.tools.openrouter_config import get_chat_completion

# 加载环境变量
load_dotenv()

def test_integrated_api():
    """测试通过项目的get_chat_completion函数使用硅基流动API"""
    print("\n===== 集成测试：使用项目框架调用硅基流动API =====")
    
    # 测试消息
    test_messages = [
        {"role": "system", "content": "你是一个专业的中国金融市场分析师。"},
        {"role": "user", "content": "分析当前A股市场风格特点和投资策略，简要回答。"}
    ]
    
    # 确保环境变量存在
    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        print("❌ 错误: 未找到SILICONFLOW_API_KEY环境变量")
        return False
    
    # 使用免费模型
    model = "Qwen/Qwen2-7B-Instruct"
    
    print(f"✓ 使用模型: {model}")
    print("开始调用API...")
    
    try:
        # 使用项目的get_chat_completion函数调用硅基流动API
        response = get_chat_completion(
            messages=test_messages,
            model=model,
            client_type="siliconflow",
            max_tokens=300,
            temperature=0.7,
            top_p=0.7,
            frequency_penalty=0.1
        )
        
        if response:
            print("\n✅ API调用成功!")
            print("=" * 50)
            print(response)
            print("=" * 50)
            return True
        else:
            print("\n❌ API调用失败: 未收到响应")
            return False
    except Exception as e:
        print(f"\n❌ API调用发生错误: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_integrated_api()
    sys.exit(0 if success else 1)