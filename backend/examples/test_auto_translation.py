"""
自动语言检测功能测试示例

这个脚本演示如何使用翻译服务的 auto 模式
"""
import asyncio
from services.translation_service import OpenAITranslator, DeepSeekTranslator


async def test_openai_auto_detection():
    """测试 OpenAI 翻译器的自动语言检测"""
    print("=" * 60)
    print("测试 OpenAI 翻译器 - 自动语言检测")
    print("=" * 60)
    
    # 需要设置你的 API Key
    translator = OpenAITranslator(
        api_key="your-api-key-here",
        model="gpt-4"
    )
    
    test_cases = [
        ("Hello world", "zh", "英语 → 中文"),
        ("こんにちは世界", "zh", "日语 → 中文"),
        ("Bonjour le monde", "zh", "法语 → 中文"),
        ("안녕하세요 세계", "zh", "韩语 → 中文"),
    ]
    
    for text, target_lang, description in test_cases:
        print(f"\n{description}")
        print(f"原文: {text}")
        
        # 使用 auto 模式
        result = await translator.translate(
            text,
            source_lang="auto",  # 自动检测源语言
            target_lang=target_lang
        )
        print(f"译文: {result}")


async def test_fixed_vs_auto():
    """对比固定语言模式和自动检测模式"""
    print("\n" + "=" * 60)
    print("对比测试：固定语言 vs 自动检测")
    print("=" * 60)
    
    translator = OpenAITranslator(
        api_key="your-api-key-here",
        model="gpt-4"
    )
    
    # 测试文本是英语
    text = "Hello, how are you?"
    
    print(f"\n原文: {text} (实际是英语)")
    
    # 固定模式：错误地告诉它是日语
    print("\n1. 固定模式 (source_lang='ja'):")
    try:
        result = await translator.translate(text, source_lang="ja", target_lang="zh")
        print(f"   结果: {result}")
        print("   说明: 模型被告知这是日语，但实际是英语，可能影响翻译质量")
    except Exception as e:
        print(f"   错误: {e}")
    
    # 自动模式：让模型自己检测
    print("\n2. 自动模式 (source_lang='auto'):")
    try:
        result = await translator.translate(text, source_lang="auto", target_lang="zh")
        print(f"   结果: {result}")
        print("   说明: 模型自动检测到是英语，翻译更准确")
    except Exception as e:
        print(f"   错误: {e}")


async def test_mixed_language():
    """测试混合语言场景"""
    print("\n" + "=" * 60)
    print("测试混合语言场景")
    print("=" * 60)
    
    translator = OpenAITranslator(
        api_key="your-api-key-here",
        model="gpt-4"
    )
    
    # 模拟 ASR 输出的多语言文本
    segments = [
        "Hello everyone",           # 英语
        "こんにちは",               # 日语
        "Bonjour",                  # 法语
        "안녕하세요",               # 韩语
        "你好",                     # 中文
    ]
    
    print("\n模拟 ASR 输出的多语言片段:")
    for i, text in enumerate(segments, 1):
        print(f"{i}. {text}")
    
    print("\n使用 auto 模式翻译到中文:")
    for i, text in enumerate(segments, 1):
        try:
            result = await translator.translate(text, source_lang="auto", target_lang="zh")
            print(f"{i}. {text} → {result}")
        except Exception as e:
            print(f"{i}. {text} → 错误: {e}")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("自动语言检测功能测试")
    print("=" * 60)
    print("\n注意: 请先设置你的 API Key")
    print("修改代码中的 'your-api-key-here' 为实际的 API Key\n")
    
    # 取消注释以运行测试
    # await test_openai_auto_detection()
    # await test_fixed_vs_auto()
    # await test_mixed_language()
    
    print("\n提示: 取消注释 main() 函数中的测试函数来运行测试")


if __name__ == "__main__":
    asyncio.run(main())
