# AudioExtractor 使用说明

## 概述

AudioExtractor 服务使用 ffmpeg 从视频文件中提取音频，并转换为 WAV 格式（16kHz 采样率，单声道），用于后续的语音识别处理。

## 功能特性

- ✅ 从视频文件提取音频流
- ✅ 转换为 WAV 格式（16kHz, 单声道）
- ✅ 自动选择第一个音频轨道
- ✅ 临时文件管理和清理
- ✅ 详细的错误处理和日志记录

## 依赖要求

### 系统依赖
- ffmpeg (需要安装在系统中)

### Python 依赖
- ffmpeg-python==0.2.0

## 使用示例

### 基本使用

```python
import asyncio
from backend.services import AudioExtractor

async def main():
    # 初始化音频提取器
    extractor = AudioExtractor(temp_dir="/tmp/audio")
    
    # 提取音频
    try:
        audio_path = await extractor.extract_audio(
            video_path="/path/to/video.mp4"
        )
        print(f"音频提取成功: {audio_path}")
        
        # 使用音频文件进行后续处理...
        
        # 清理临时文件
        extractor.cleanup(audio_path)
        
    except FileNotFoundError as e:
        print(f"视频文件不存在: {e}")
    except RuntimeError as e:
        print(f"音频提取失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 指定输出路径

```python
# 指定输出路径
audio_path = await extractor.extract_audio(
    video_path="/path/to/video.mp4",
    output_path="/custom/path/audio.wav"
)
```

### 获取音频流信息

```python
# 获取视频的音频流信息
audio_info = extractor._get_audio_stream_info("/path/to/video.mp4")
print(f"编码: {audio_info['codec_name']}")
print(f"采样率: {audio_info['sample_rate']}")
print(f"声道数: {audio_info['channels']}")
print(f"时长: {audio_info['duration']}")
```

## API 参考

### AudioExtractor

#### `__init__(temp_dir: str)`

初始化音频提取器。

**参数:**
- `temp_dir`: 临时文件存储目录

**示例:**
```python
extractor = AudioExtractor(temp_dir="/tmp/audio")
```

#### `async extract_audio(video_path: str, output_path: Optional[str] = None) -> str`

从视频中提取音频。

**参数:**
- `video_path`: 视频文件路径
- `output_path`: 输出音频文件路径（可选）

**返回:**
- `str`: 提取的音频文件路径

**异常:**
- `FileNotFoundError`: 视频文件不存在
- `RuntimeError`: 音频提取失败

**示例:**
```python
audio_path = await extractor.extract_audio("/path/to/video.mp4")
```

#### `cleanup(audio_path: str)`

清理临时音频文件。

**参数:**
- `audio_path`: 要删除的音频文件路径

**示例:**
```python
extractor.cleanup("/tmp/audio/video_audio.wav")
```

## 技术细节

### 音频转换参数

AudioExtractor 使用以下 ffmpeg 参数进行音频转换：

- **采样率 (ar)**: 16000 Hz (16kHz)
- **声道数 (ac)**: 1 (单声道)
- **音频编码 (acodec)**: pcm_s16le (16-bit PCM)
- **音频流选择 (map)**: 0:a:0 (第一个音频流)

这些参数确保输出的音频格式适合语音识别引擎处理。

### 错误处理

AudioExtractor 提供详细的错误处理：

1. **文件不存在**: 抛出 `FileNotFoundError`
2. **FFmpeg 错误**: 抛出 `RuntimeError` 并包含详细错误信息
3. **无音频流**: 抛出 `RuntimeError` 提示视频中没有音频流

### 日志记录

AudioExtractor 使用 Python logging 模块记录操作日志：

- **INFO**: 初始化、提取成功、清理操作
- **DEBUG**: 音频流信息
- **ERROR**: 错误信息和堆栈跟踪
- **WARNING**: 清理不存在的文件

## 测试

运行单元测试：

```bash
cd backend
python -m pytest test_audio_extractor.py -v
```

## 需求映射

AudioExtractor 实现了以下需求：

- **需求 2.1**: 使用 ffmpeg 提取音频流
- **需求 2.2**: 转换为 WAV 格式（16kHz, 单声道）
- **需求 2.3**: 提取第一个音频轨道
- **需求 2.5**: 存储在临时目录中

## 注意事项

1. **ffmpeg 依赖**: 确保系统中已安装 ffmpeg
2. **临时目录**: 确保临时目录有足够的磁盘空间
3. **文件清理**: 使用完音频文件后及时调用 `cleanup()` 方法
4. **异步操作**: `extract_audio()` 是异步方法，需要使用 `await` 调用

## 下一步

AudioExtractor 服务将在 Celery 任务中使用，作为字幕生成流程的第一步：

1. AudioExtractor 提取音频
2. ASR Engine 进行语音识别
3. Translation Service 翻译文本
4. Subtitle Generator 生成字幕文件
5. Emby Connector 回写到媒体库
