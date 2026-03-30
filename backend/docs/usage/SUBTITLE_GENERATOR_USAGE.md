# SubtitleGenerator Service Usage Guide

## Overview

The `SubtitleGenerator` service generates SRT format subtitle files from transcribed and translated text segments. It handles timestamp formatting, file naming, and validation according to SRT standards.

## Features

- Generate SRT format subtitle files
- Automatic timestamp formatting (HH:MM:SS,mmm)
- Intelligent file naming ({video_filename}.zh.srt)
- Save subtitles to video directory
- SRT format validation
- Support for untranslated segments (fallback to original text)

## Basic Usage

```python
from backend.services.subtitle_generator import SubtitleGenerator, SubtitleSegment

# Initialize the generator
generator = SubtitleGenerator()

# Create subtitle segments
segments = [
    SubtitleSegment(
        start=0.0,
        end=2.5,
        original_text="こんにちは",
        translated_text="你好",
        is_translated=True
    ),
    SubtitleSegment(
        start=2.5,
        end=5.0,
        original_text="世界",
        translated_text="世界",
        is_translated=True
    )
]

# Generate SRT file
video_path = "/path/to/video.mp4"
subtitle_path = generator.generate_srt(segments, video_path)
print(f"Subtitle file created: {subtitle_path}")
# Output: /path/to/video.zh.srt
```

## Data Structures

### SubtitleSegment

```python
@dataclass
class SubtitleSegment:
    start: float              # Start time in seconds
    end: float                # End time in seconds
    original_text: str        # Original Japanese text
    translated_text: str      # Translated Chinese text
    is_translated: bool = True # Whether translation succeeded
```

## Methods

### generate_srt()

Generate SRT format subtitle file.

**Parameters:**
- `segments` (List[SubtitleSegment]): List of subtitle segments
- `video_path` (str): Path to the video file

**Returns:**
- `str`: Path to the generated subtitle file

**Raises:**
- `ValueError`: If segments list is empty or video_path is invalid
- `IOError`: If unable to write subtitle file

**Example:**
```python
output_path = generator.generate_srt(segments, "/path/to/video.mp4")
```

### validate_srt()

Validate SRT file format.

**Parameters:**
- `file_path` (str): Path to the SRT file

**Returns:**
- `bool`: True if file format is valid, False otherwise

**Example:**
```python
is_valid = generator.validate_srt("/path/to/subtitle.srt")
if is_valid:
    print("SRT file is valid")
else:
    print("SRT file is invalid")
```

## SRT Format

The generated SRT files follow the standard format:

```
1
00:00:00,000 --> 00:00:02,500
你好

2
00:00:02,500 --> 00:00:05,000
世界

```

Each subtitle block contains:
1. Sequence number
2. Timestamp range (start --> end)
3. Subtitle text
4. Blank line separator

## Handling Translation Failures

When translation fails for a segment, the service automatically falls back to the original text:

```python
segments = [
    SubtitleSegment(
        start=0.0,
        end=2.5,
        original_text="こんにちは",
        translated_text="",
        is_translated=False  # Translation failed
    )
]

# The generated SRT will contain the original Japanese text
output_path = generator.generate_srt(segments, video_path)
```

## File Naming Convention

Subtitle files are automatically named according to the pattern:
- Input: `/path/to/my_video.mp4`
- Output: `/path/to/my_video.zh.srt`

The `.zh` suffix indicates Chinese language subtitles.

## Integration with ASR and Translation Services

```python
from backend.services.asr_engine import SherpaOnnxEngine
from backend.services.translation_service import OpenAITranslator
from backend.services.subtitle_generator import SubtitleGenerator, SubtitleSegment

# Initialize services
asr_engine = SherpaOnnxEngine(model_path="/path/to/model")
translator = OpenAITranslator(api_key="your-api-key")
generator = SubtitleGenerator()

# Process audio
audio_path = "/path/to/audio.wav"
asr_segments = await asr_engine.transcribe(audio_path, language="ja")

# Translate and create subtitle segments
subtitle_segments = []
for seg in asr_segments:
    translated = await translator.translate(seg.text, source_lang="ja", target_lang="zh")
    subtitle_segments.append(SubtitleSegment(
        start=seg.start,
        end=seg.end,
        original_text=seg.text,
        translated_text=translated,
        is_translated=True
    ))

# Generate subtitle file
video_path = "/path/to/video.mp4"
subtitle_path = generator.generate_srt(subtitle_segments, video_path)
```

## Testing

Run the test suite:

```bash
cd backend
python -m pytest test_subtitle_generator.py -v
```

## Requirements

- Python 3.10+
- No external dependencies (uses only standard library)

## Notes

- Subtitle files are saved in UTF-8 encoding
- Timestamps are formatted according to SRT standard (HH:MM:SS,mmm)
- The service validates video path existence before generating subtitles
- Empty segment lists are rejected with a ValueError
