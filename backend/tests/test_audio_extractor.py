"""
测试 AudioExtractor 服务
"""

import pytest
import os
import tempfile
from pathlib import Path
from backend.services.audio_extractor import AudioExtractor


@pytest.fixture
def temp_dir():
    """创建临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def audio_extractor(temp_dir):
    """创建 AudioExtractor 实例"""
    return AudioExtractor(temp_dir)


class TestAudioExtractor:
    """AudioExtractor 测试类"""
    
    def test_init(self, temp_dir):
        """测试初始化"""
        extractor = AudioExtractor(temp_dir)
        assert extractor.temp_dir == Path(temp_dir)
        assert extractor.temp_dir.exists()
    
    def test_init_creates_temp_dir(self):
        """测试初始化时创建临时目录"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_temp_dir = os.path.join(tmpdir, "audio_temp")
            extractor = AudioExtractor(new_temp_dir)
            assert os.path.exists(new_temp_dir)
    
    @pytest.mark.asyncio
    async def test_extract_audio_file_not_found(self, audio_extractor):
        """测试视频文件不存在时抛出异常"""
        with pytest.raises(FileNotFoundError) as exc_info:
            await audio_extractor.extract_audio("/nonexistent/video.mp4")
        assert "Video file not found" in str(exc_info.value)
    
    def test_cleanup_existing_file(self, audio_extractor, temp_dir):
        """测试清理存在的文件"""
        # 创建一个临时文件
        test_file = os.path.join(temp_dir, "test_audio.wav")
        Path(test_file).touch()
        assert os.path.exists(test_file)
        
        # 清理文件
        audio_extractor.cleanup(test_file)
        assert not os.path.exists(test_file)
    
    def test_cleanup_nonexistent_file(self, audio_extractor):
        """测试清理不存在的文件不会抛出异常"""
        # 不应该抛出异常
        audio_extractor.cleanup("/nonexistent/audio.wav")
    
    def test_get_audio_stream_info_no_file(self, audio_extractor):
        """测试获取不存在文件的音频流信息"""
        with pytest.raises(RuntimeError):
            audio_extractor._get_audio_stream_info("/nonexistent/video.mp4")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
