"""
Unit tests for ASR Engine module
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from backend.services.asr_engine import ASREngine, SherpaOnnxEngine, CloudASREngine, Segment


class TestSegment:
    """Test Segment dataclass"""
    
    def test_segment_creation(self):
        """Test creating a Segment instance"""
        segment = Segment(start=0.0, end=2.5, text="こんにちは")
        
        assert segment.start == 0.0
        assert segment.end == 2.5
        assert segment.text == "こんにちは"


class TestASREngine:
    """Test ASREngine abstract base class"""
    
    def test_cannot_instantiate_abstract_class(self):
        """Test that ASREngine cannot be instantiated directly"""
        with pytest.raises(TypeError):
            ASREngine()


class TestCloudASREngine:
    """Test CloudASREngine implementation"""
    
    def test_initialization(self):
        """Test CloudASREngine initialization"""
        engine = CloudASREngine(
            api_url="https://api.example.com",
            api_key="test_key"
        )
        
        assert engine.api_url == "https://api.example.com"
        assert engine.api_key == "test_key"
    
    def test_initialization_empty_url(self):
        """Test CloudASREngine initialization with empty URL"""
        with pytest.raises(ValueError, match="API URL cannot be empty"):
            CloudASREngine(api_url="", api_key="test_key")
    
    def test_initialization_empty_key(self):
        """Test CloudASREngine initialization with empty API key"""
        with pytest.raises(ValueError, match="API key cannot be empty"):
            CloudASREngine(api_url="https://api.example.com", api_key="")
    
    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self):
        """Test transcribe with non-existent audio file"""
        engine = CloudASREngine(
            api_url="https://api.example.com",
            api_key="test_key"
        )
        
        with pytest.raises(FileNotFoundError):
            await engine.transcribe("/nonexistent/audio.wav")
    
    @pytest.mark.asyncio
    async def test_transcribe_success_with_segments(self, tmp_path):
        """Test successful transcription with segments"""
        # Create a temporary audio file
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")
        
        engine = CloudASREngine(
            api_url="https://api.example.com",
            api_key="test_key"
        )
        
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {
            "segments": [
                {"start": 0.0, "end": 2.5, "text": "こんにちは"},
                {"start": 2.5, "end": 5.0, "text": "世界"}
            ]
        }
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            segments = await engine.transcribe(str(audio_file))
            
            assert len(segments) == 2
            assert segments[0].start == 0.0
            assert segments[0].end == 2.5
            assert segments[0].text == "こんにちは"
            assert segments[1].start == 2.5
            assert segments[1].end == 5.0
            assert segments[1].text == "世界"
    
    @pytest.mark.asyncio
    async def test_transcribe_success_text_only(self, tmp_path):
        """Test successful transcription with text only (no segments)"""
        # Create a temporary audio file
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake audio data")
        
        engine = CloudASREngine(
            api_url="https://api.example.com",
            api_key="test_key"
        )
        
        # Mock httpx response
        mock_response = Mock()
        mock_response.json.return_value = {
            "text": "こんにちは世界"
        }
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            with patch.object(engine, '_get_audio_duration', return_value=5.0):
                segments = await engine.transcribe(str(audio_file))
                
                assert len(segments) == 1
                assert segments[0].start == 0.0
                assert segments[0].end == 5.0
                assert segments[0].text == "こんにちは世界"


class TestSherpaOnnxEngine:
    """Test SherpaOnnxEngine implementation"""
    
    def test_initialization_model_not_found(self):
        """Test SherpaOnnxEngine initialization with non-existent model path"""
        with pytest.raises(FileNotFoundError, match="Model path not found"):
            SherpaOnnxEngine(model_path="/nonexistent/model")
    
    def test_initialization_success(self, tmp_path):
        """Test SherpaOnnxEngine initialization with valid model path"""
        # Create a temporary model directory
        model_dir = tmp_path / "model"
        model_dir.mkdir()
        
        # Create dummy model files
        (model_dir / "tokens.txt").write_text("dummy")
        (model_dir / "encoder.onnx").write_bytes(b"dummy")
        (model_dir / "decoder.onnx").write_bytes(b"dummy")
        (model_dir / "joiner.onnx").write_bytes(b"dummy")
        
        # Mock sherpa_onnx to avoid actual model loading
        with patch('backend.services.asr_engine.sherpa_onnx'):
            engine = SherpaOnnxEngine(model_path=str(model_dir))
            assert engine.model_path == str(model_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
