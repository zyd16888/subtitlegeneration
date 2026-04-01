"""
音频提取服务

使用 ffmpeg 从视频文件中提取音频，转换为 WAV 格式（16kHz, 单声道）
"""

import os
import logging
import ffmpeg
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AudioExtractor:
    """音频提取器，使用 ffmpeg 从视频中提取音频"""
    
    def __init__(self, temp_dir: str):
        """
        初始化音频提取器
        
        Args:
            temp_dir: 临时文件存储目录
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"AudioExtractor initialized with temp_dir: {self.temp_dir}")
    
    async def extract_audio(
        self, 
        video_path: str,
        output_path: Optional[str] = None
    ) -> str:
        """
        从视频中提取音频（支持本地文件和 HTTP/HTTPS URL）
        
        Args:
            video_path: 视频文件路径或 HTTP/HTTPS URL
            output_path: 输出音频文件路径（可选，默认在临时目录生成）
        
        Returns:
            str: 提取的音频文件路径
        
        Raises:
            FileNotFoundError: 本地视频文件不存在
            RuntimeError: 音频提取失败
        """
        logger.info(f"=== Starting audio extraction ===")
        logger.info(f"Input video_path: {video_path}")
        logger.info(f"Output path: {output_path}")
        
        # 判断是 URL 还是本地文件
        is_url = video_path.startswith(('http://', 'https://'))
        logger.info(f"Is URL: {is_url}")
        
        # 如果是本地文件，验证文件存在
        if not is_url and not os.path.exists(video_path):
            error_msg = f"Video file not found: {video_path}"
            logger.error(error_msg)
            raise FileNotFoundError(error_msg)
        
        # 生成输出路径
        if output_path is None:
            if is_url:
                # 从 URL 中提取文件名或使用时间戳
                import hashlib
                import time
                url_hash = hashlib.md5(video_path.encode()).hexdigest()[:8]
                output_path = str(self.temp_dir / f"audio_{url_hash}_{int(time.time())}.wav")
            else:
                video_name = Path(video_path).stem
                output_path = str(self.temp_dir / f"{video_name}_audio.wav")
        
        logger.info(f"Extracting audio from {'URL' if is_url else 'file'}: {video_path}")
        logger.info(f"Output path: {output_path}")
        
        try:
            # 使用 ffmpeg 提取音频并转换格式
            # ffmpeg 原生支持 HTTP/HTTPS 输入
            # 参数说明:
            # - ar: 采样率 16kHz
            # - ac: 声道数 1 (单声道)
            # - acodec: 音频编码器 pcm_s16le (16-bit PCM)
            # - map 0:a:0: 选择第一个音频流
            logger.info("Building ffmpeg command...")
            stream = ffmpeg.input(video_path)
            stream = ffmpeg.output(
                stream,
                output_path,
                acodec='pcm_s16le',
                ar=16000,
                ac=1,
                map='0:a:0'
            )
            
            # 执行 ffmpeg 命令，覆盖已存在的文件
            logger.info(f"Running ffmpeg command: input={video_path}, output={output_path}")
            logger.info(f"FFmpeg parameters: acodec=pcm_s16le, ar=16000, ac=1, map=0:a:0")
            
            stdout, stderr = ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
            
            logger.info(f"FFmpeg completed successfully")
            if stderr:
                logger.debug(f"FFmpeg stderr: {stderr.decode()[:500]}")  # 只记录前500字符
            
            # 验证输出文件
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                logger.info(f"Audio extracted successfully: {output_path} (size: {file_size} bytes)")
            else:
                logger.error(f"Output file not created: {output_path}")
                raise RuntimeError(f"Output file not created: {output_path}")
            
            return output_path
            
        except ffmpeg.Error as e:
            stderr_msg = e.stderr.decode() if e.stderr else str(e)
            error_msg = f"FFmpeg error while extracting audio: {stderr_msg}"
            logger.error(error_msg)
            logger.error(f"FFmpeg command failed for input: {video_path}")
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error while extracting audio: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
    
    def _get_audio_stream_info(self, video_path: str) -> dict:
        """
        获取视频的音频流信息
        
        Args:
            video_path: 视频文件路径
        
        Returns:
            dict: 音频流信息
        
        Raises:
            RuntimeError: 无法获取音频流信息
        """
        try:
            probe = ffmpeg.probe(video_path)
            
            # 查找第一个音频流
            audio_streams = [
                stream for stream in probe['streams']
                if stream['codec_type'] == 'audio'
            ]
            
            if not audio_streams:
                raise RuntimeError(f"No audio stream found in video: {video_path}")
            
            # 返回第一个音频流的信息
            audio_stream = audio_streams[0]
            return {
                'codec_name': audio_stream.get('codec_name'),
                'sample_rate': audio_stream.get('sample_rate'),
                'channels': audio_stream.get('channels'),
                'duration': audio_stream.get('duration'),
            }
            
        except ffmpeg.Error as e:
            error_msg = f"FFmpeg error while probing video: {e.stderr.decode() if e.stderr else str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error while probing video: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def cleanup(self, audio_path: str):
        """
        清理临时音频文件
        
        Args:
            audio_path: 要删除的音频文件路径
        """
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                logger.info(f"Cleaned up temporary audio file: {audio_path}")
            else:
                logger.warning(f"Audio file not found for cleanup: {audio_path}")
        except Exception as e:
            logger.error(f"Error cleaning up audio file {audio_path}: {str(e)}")
