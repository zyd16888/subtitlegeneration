# Translation Service Usage Guide

## Overview

The Translation Service module provides a unified interface for translating text using multiple translation engines:
- **OpenAI**: High-quality translation using GPT models
- **DeepSeek**: Cost-effective translation using DeepSeek API
- **Local LLM**: Privacy-focused translation using locally hosted LLMs (Ollama, LM Studio, etc.)

All translators implement automatic retry mechanism with exponential backoff (max 3 retries) and preserve original text if translation fails.

## Installation

The required dependencies are already included in `requirements.txt`:
```
openai==1.10.0
httpx==0.26.0
```

## Basic Usage

### OpenAI Translator

```python
from backend.services.translation_service import OpenAITranslator

# Initialize translator
translator = OpenAITranslator(
    api_key="your-openai-api-key",
    model="gpt-4"  # or "gpt-3.5-turbo" for faster/cheaper translation
)

# Translate single text
translated = await translator.translate(
    text="こんにちは世界",
    source_lang="ja",
    target_lang="zh"
)
print(translated)  # Output: 你好世界

# Translate batch
texts = ["こんにちは", "ありがとう", "さようなら"]
translations = await translator.translate_batch(texts, source_lang="ja", target_lang="zh")
print(translations)  # Output: ['你好', '谢谢', '再见']
```

### DeepSeek Translator

```python
from backend.services.translation_service import DeepSeekTranslator

# Initialize translator
translator = DeepSeekTranslator(
    api_key="your-deepseek-api-key",
    api_url="https://api.deepseek.com/v1"  # Optional, uses default if not specified
)

# Translate text
translated = await translator.translate(
    text="こんにちは世界",
    source_lang="ja",
    target_lang="zh"
)
print(translated)  # Output: 你好世界
```

### Local LLM Translator

```python
from backend.services.translation_service import LocalLLMTranslator

# Initialize translator (for Ollama)
translator = LocalLLMTranslator(
    api_url="http://localhost:11434/api",
    model="llama2"  # or any other model you have installed
)

# Translate text
translated = await translator.translate(
    text="こんにちは世界",
    source_lang="ja",
    target_lang="zh"
)
print(translated)  # Output: 你好世界
```

## Advanced Features

### Retry Mechanism

All translators automatically retry failed translations up to 3 times with exponential backoff:
- 1st retry: wait 1 second
- 2nd retry: wait 2 seconds
- 3rd retry: wait 4 seconds

If all retries fail, the original text is returned.

```python
# This is handled automatically
translated = await translator.translate("こんにちは")
# If translation fails after 3 retries, returns "こんにちは"
```

### Batch Translation

Batch translation processes multiple texts sequentially:

```python
texts = [
    "こんにちは",
    "ありがとうございます",
    "さようなら"
]

translations = await translator.translate_batch(
    texts=texts,
    source_lang="ja",
    target_lang="zh"
)

# translations = ['你好', '非常感谢', '再见']
```

### Error Handling

```python
try:
    translated = await translator.translate("こんにちは")
except RuntimeError as e:
    print(f"Translation failed: {e}")
```

## Integration with Subtitle Generation

Example of using translation service in subtitle generation workflow:

```python
from backend.services.translation_service import OpenAITranslator
from backend.services.asr_engine import Segment

# Initialize translator
translator = OpenAITranslator(api_key="your-api-key")

# ASR segments from speech recognition
asr_segments = [
    Segment(start=0.0, end=2.5, text="こんにちは"),
    Segment(start=2.5, end=5.0, text="世界"),
]

# Translate each segment
translated_segments = []
for segment in asr_segments:
    translated_text = await translator.translate(
        text=segment.text,
        source_lang="ja",
        target_lang="zh"
    )
    translated_segments.append({
        "start": segment.start,
        "end": segment.end,
        "original": segment.text,
        "translated": translated_text
    })

# Result:
# [
#     {"start": 0.0, "end": 2.5, "original": "こんにちは", "translated": "你好"},
#     {"start": 2.5, "end": 5.0, "original": "世界", "translated": "世界"}
# ]
```

## Configuration

### Environment Variables

You can store API keys in environment variables:

```bash
# .env file
OPENAI_API_KEY=your-openai-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key
LOCAL_LLM_URL=http://localhost:11434/api
```

```python
import os
from dotenv import load_dotenv

load_dotenv()

translator = OpenAITranslator(api_key=os.getenv("OPENAI_API_KEY"))
```

### Supported Languages

The translators support various language codes:
- `ja`: Japanese
- `zh`: Chinese
- `en`: English

You can extend this by modifying the `lang_names` dictionary in each translator class.

## Performance Considerations

### OpenAI
- **Speed**: Fast (1-3 seconds per text)
- **Quality**: Excellent
- **Cost**: ~$0.03 per 1K tokens (GPT-4)

### DeepSeek
- **Speed**: Fast (1-3 seconds per text)
- **Quality**: Good
- **Cost**: Lower than OpenAI

### Local LLM
- **Speed**: Depends on hardware (2-10 seconds per text)
- **Quality**: Varies by model
- **Cost**: Free (runs locally)

## Testing

Run the unit tests:

```bash
python -m pytest backend/test_translation_service.py -v
```

## Requirements Mapping

This implementation satisfies the following requirements:

- **需求 4.1**: Supports pluggable configuration for OpenAI, DeepSeek, and Local LLM ✓
- **需求 4.2**: Translates Japanese text to Chinese while preserving timestamps ✓
- **需求 4.4**: Retries up to 3 times on failure ✓
- **需求 4.5**: Preserves original Japanese text if translation fails after 3 retries ✓
- **需求 4.6**: Configures translation engine type in settings ✓

## Next Steps

The translation service is now ready to be integrated into:
1. Celery tasks for async subtitle generation
2. API endpoints for configuration management
3. Frontend settings page for user configuration
