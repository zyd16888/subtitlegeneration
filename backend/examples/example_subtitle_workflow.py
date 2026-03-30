"""
Example workflow demonstrating the complete subtitle generation process.

This script shows how to integrate ASR, Translation, and Subtitle Generation services.
"""
import asyncio
from backend.services.subtitle_generator import SubtitleGenerator, SubtitleSegment


async def example_workflow():
    """
    Example workflow for generating subtitles.
    
    This demonstrates the integration of:
    1. ASR Engine (transcription)
    2. Translation Service
    3. Subtitle Generator
    """
    
    # Example: Simulated ASR output
    # In real usage, this would come from ASREngine.transcribe()
    asr_segments = [
        {"start": 0.0, "end": 2.5, "text": "こんにちは"},
        {"start": 2.5, "end": 5.0, "text": "世界"},
        {"start": 5.0, "end": 8.0, "text": "今日はいい天気ですね"}
    ]
    
    # Example: Simulated translation output
    # In real usage, this would come from TranslationService.translate()
    translations = {
        "こんにちは": "你好",
        "世界": "世界",
        "今日はいい天気ですね": "今天天气真好"
    }
    
    # Create SubtitleSegment objects
    subtitle_segments = []
    for seg in asr_segments:
        original_text = seg["text"]
        translated_text = translations.get(original_text, "")
        is_translated = bool(translated_text)
        
        subtitle_segments.append(SubtitleSegment(
            start=seg["start"],
            end=seg["end"],
            original_text=original_text,
            translated_text=translated_text if is_translated else original_text,
            is_translated=is_translated
        ))
    
    # Generate subtitle file
    generator = SubtitleGenerator()
    video_path = "/path/to/video.mp4"  # Replace with actual video path
    
    try:
        subtitle_path = generator.generate_srt(subtitle_segments, video_path)
        print(f"✓ Subtitle file generated: {subtitle_path}")
        
        # Validate the generated file
        if generator.validate_srt(subtitle_path):
            print("✓ Subtitle file validation passed")
        else:
            print("✗ Subtitle file validation failed")
            
    except Exception as e:
        print(f"✗ Error generating subtitle: {e}")


async def complete_integration_example():
    """
    Complete integration example with actual services.
    
    Note: This requires proper configuration of ASR and Translation services.
    """
    # Uncomment and configure these imports when services are available
    # from backend.services.asr_engine import SherpaOnnxEngine
    # from backend.services.translation_service import OpenAITranslator
    
    # Initialize services
    # asr_engine = SherpaOnnxEngine(model_path="/path/to/model")
    # translator = OpenAITranslator(api_key="your-api-key")
    generator = SubtitleGenerator()
    
    # Process workflow
    audio_path = "/path/to/audio.wav"
    video_path = "/path/to/video.mp4"
    
    # Step 1: Transcribe audio
    # asr_segments = await asr_engine.transcribe(audio_path, language="ja")
    
    # Step 2: Translate segments
    # subtitle_segments = []
    # for seg in asr_segments:
    #     translated = await translator.translate(seg.text, source_lang="ja", target_lang="zh")
    #     subtitle_segments.append(SubtitleSegment(
    #         start=seg.start,
    #         end=seg.end,
    #         original_text=seg.text,
    #         translated_text=translated,
    #         is_translated=True
    #     ))
    
    # Step 3: Generate subtitle file
    # subtitle_path = generator.generate_srt(subtitle_segments, video_path)
    # print(f"Subtitle generated: {subtitle_path}")
    
    print("Complete integration example (requires service configuration)")


if __name__ == "__main__":
    print("=== Subtitle Generation Workflow Example ===\n")
    asyncio.run(example_workflow())
    print("\n=== Complete Integration Example ===\n")
    asyncio.run(complete_integration_example())
