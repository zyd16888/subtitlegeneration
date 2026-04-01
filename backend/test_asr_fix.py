#!/usr/bin/env python3
"""
测试 ASR 引擎修复

验证 sherpa-onnx 新版本 API 是否正常工作
"""
import logging
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_sherpa_onnx_import():
    """测试 sherpa-onnx 导入"""
    logger.info("=== 测试 sherpa-onnx 导入 ===")
    try:
        import sherpa_onnx
        from sherpa_onnx import online_recognizer, offline_recognizer
        
        logger.info(f"✓ sherpa_onnx 版本: {sherpa_onnx.__version__ if hasattr(sherpa_onnx, '__version__') else 'unknown'}")
        logger.info(f"✓ online_recognizer 模块导入成功")
        logger.info(f"✓ offline_recognizer 模块导入成功")
        
        # 检查关键类
        logger.info(f"✓ OfflineRecognizerConfig: {hasattr(offline_recognizer, 'OfflineRecognizerConfig')}")
        logger.info(f"✓ OnlineRecognizerConfig: {hasattr(online_recognizer, 'OnlineRecognizerConfig')}")
        
        return True
    except Exception as e:
        logger.error(f"✗ 导入失败: {e}", exc_info=True)
        return False


def test_whisper_model():
    """测试 Whisper 模型初始化"""
    logger.info("\n=== 测试 Whisper 模型初始化 ===")
    try:
        from services.asr_engine import SherpaOnnxOfflineEngine
        
        model_path = Path("backend/models_data/whisper-tiny")
        if not model_path.exists():
            model_path = Path("models_data/whisper-tiny")
        
        if not model_path.exists():
            logger.warning(f"✗ 模型路径不存在: {model_path}")
            return False
        
        logger.info(f"模型路径: {model_path}")
        
        file_map = {
            "decoder": "tiny-decoder.int8.onnx",
            "encoder": "tiny-encoder.int8.onnx",
            "tokens": "tiny-tokens.txt"
        }
        
        logger.info("创建 SherpaOnnxOfflineEngine...")
        engine = SherpaOnnxOfflineEngine(
            str(model_path),
            model_type="whisper",
            file_map=file_map
        )
        
        logger.info(f"✓ Whisper 引擎创建成功")
        logger.info(f"  引擎类型: {type(engine).__name__}")
        logger.info(f"  识别器: {type(engine.recognizer).__name__ if engine.recognizer else 'None'}")
        
        return True
    except Exception as e:
        logger.error(f"✗ Whisper 模型初始化失败: {e}", exc_info=True)
        return False


def test_online_model():
    """测试在线模型初始化"""
    logger.info("\n=== 测试在线模型初始化 ===")
    try:
        from services.asr_engine import SherpaOnnxOnlineEngine
        
        model_path = Path("backend/models_data/streaming-zipformer-bilingual-zh-en")
        if not model_path.exists():
            model_path = Path("models_data/streaming-zipformer-bilingual-zh-en")
        
        if not model_path.exists():
            logger.warning(f"✗ 模型路径不存在: {model_path}")
            return False
        
        logger.info(f"模型路径: {model_path}")
        
        logger.info("创建 SherpaOnnxOnlineEngine...")
        engine = SherpaOnnxOnlineEngine(str(model_path))
        
        logger.info(f"✓ 在线引擎创建成功")
        logger.info(f"  引擎类型: {type(engine).__name__}")
        logger.info(f"  识别器: {type(engine.recognizer).__name__ if engine.recognizer else 'None'}")
        
        return True
    except Exception as e:
        logger.error(f"✗ 在线模型初始化失败: {e}", exc_info=True)
        return False


def main():
    """运行所有测试"""
    logger.info("开始测试 ASR 引擎修复...")
    
    results = []
    
    # 测试 1: 导入
    results.append(("sherpa-onnx 导入", test_sherpa_onnx_import()))
    
    # 测试 2: Whisper 模型
    results.append(("Whisper 模型", test_whisper_model()))
    
    # 测试 3: 在线模型
    results.append(("在线模型", test_online_model()))
    
    # 总结
    logger.info("\n" + "="*50)
    logger.info("测试结果总结:")
    logger.info("="*50)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{name}: {status}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    logger.info(f"\n总计: {passed}/{total} 测试通过")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
