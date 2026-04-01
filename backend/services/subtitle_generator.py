"""
Subtitle Generator Module

This module provides functionality to generate SRT format subtitle files
from transcribed and translated text segments.
"""

import os
from dataclasses import dataclass
from typing import List


@dataclass
class SubtitleSegment:
    """
    Represents a subtitle segment with timestamps and text.
    
    Attributes:
        start: Start time in seconds
        end: End time in seconds
        original_text: Original Japanese text
        translated_text: Translated Chinese text
        is_translated: Whether translation succeeded
    """
    start: float
    end: float
    original_text: str
    translated_text: str
    is_translated: bool = True


class SubtitleGenerator:
    """
    Generates SRT format subtitle files.
    
    Supports creating subtitle files with proper formatting and timestamps
    according to the SRT standard.
    """
    
    def generate_srt(
        self,
        segments: List[SubtitleSegment],
        video_path: str,
        target_language: str = "zh",
        output_dir: str = None,
    ) -> str:
        """
        Generate SRT format subtitle file.

        Args:
            segments: List of SubtitleSegment objects containing text and timestamps
            video_path: Path to the video file or URL (used to determine filename)
            target_language: Target language code for the subtitle filename
            output_dir: Output directory (required when video_path is a URL)

        Returns:
            Path to the generated subtitle file

        Raises:
            ValueError: If segments list is empty
            IOError: If unable to write subtitle file
        """
        if not segments:
            raise ValueError("Segments list cannot be empty")

        if not video_path:
            raise ValueError("video_path cannot be empty")

        # 从 video_path 提取文件名（支持本地路径和 URL）
        is_url = video_path.startswith(('http://', 'https://'))
        if is_url:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(video_path)
            # 尝试从 URL 路径提取有意义的名称
            path_parts = parsed.path.strip('/').split('/')
            video_filename = '_'.join(path_parts) if path_parts else 'subtitle'
        else:
            video_filename = os.path.splitext(os.path.basename(video_path))[0]

        # 确定输出目录
        if output_dir:
            save_dir = output_dir
        elif not is_url:
            save_dir = os.path.dirname(video_path)
        else:
            save_dir = '.'

        os.makedirs(save_dir, exist_ok=True)
        output_path = os.path.join(save_dir, f"{video_filename}.{target_language}.srt")
        
        # Generate SRT content
        srt_content = self._generate_srt_content(segments)
        
        # Write to file
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
        except Exception as e:
            raise IOError(f"Failed to write subtitle file: {e}")
        
        return output_path
    
    def _generate_srt_content(self, segments: List[SubtitleSegment]) -> str:
        """
        Generate SRT format content from segments.
        
        Args:
            segments: List of SubtitleSegment objects
            
        Returns:
            SRT formatted string
        """
        srt_lines = []
        
        for index, segment in enumerate(segments, start=1):
            # Sequence number
            srt_lines.append(str(index))
            
            # Timestamps
            start_time = self._format_timestamp(segment.start)
            end_time = self._format_timestamp(segment.end)
            srt_lines.append(f"{start_time} --> {end_time}")
            
            # Text content (use translated text if available, otherwise original)
            text = segment.translated_text if segment.is_translated else segment.original_text
            srt_lines.append(text)
            
            # Blank line separator
            srt_lines.append("")
        
        return "\n".join(srt_lines)
    
    def _format_timestamp(self, seconds: float) -> str:
        """
        Convert seconds to SRT timestamp format (HH:MM:SS,mmm).
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted timestamp string (e.g., "00:01:23,456")
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def validate_srt(self, file_path: str) -> bool:
        """
        Validate SRT file format.
        
        Args:
            file_path: Path to the SRT file
            
        Returns:
            True if file format is valid, False otherwise
        """
        if not os.path.exists(file_path):
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Basic validation: check for sequence numbers and timestamp format
            lines = content.strip().split('\n')
            
            if not lines:
                return False
            
            # Check first subtitle block
            if len(lines) < 3:
                return False
            
            # First line should be a number (sequence)
            try:
                int(lines[0])
            except ValueError:
                return False
            
            # Second line should contain timestamp with -->
            if '-->' not in lines[1]:
                return False
            
            # Check timestamp format (HH:MM:SS,mmm)
            timestamp_parts = lines[1].split('-->')
            if len(timestamp_parts) != 2:
                return False
            
            for timestamp in timestamp_parts:
                timestamp = timestamp.strip()
                if ',' not in timestamp:
                    return False
                
                time_part, ms_part = timestamp.split(',')
                time_components = time_part.split(':')
                
                if len(time_components) != 3:
                    return False
                
                # Validate each component is numeric
                try:
                    int(time_components[0])  # hours
                    int(time_components[1])  # minutes
                    int(time_components[2])  # seconds
                    int(ms_part)  # milliseconds
                except ValueError:
                    return False
            
            return True
            
        except Exception:
            return False
