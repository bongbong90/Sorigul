import sys
import pytest
from pathlib import Path
from src.services.audio_metadata import AudioMetadataService

def test_missing_file(tmp_path):
    service = AudioMetadataService()
    assert service.duration_seconds(tmp_path / 'missing.mp3') is None

def test_corrupt_invalid_metadata(tmp_path):
    service = AudioMetadataService()
    path = tmp_path / 'corrupt.mp3'
    path.write_bytes(b'not an audio file at all')
    assert service.duration_seconds(path) is None

def test_mocked_mutagen_valid_and_invalid(tmp_path, monkeypatch):
    import mutagen.mp3
    path = tmp_path / 'mock.mp3'
    path.write_bytes(b'dummy')
    class FakeInfo:
        def __init__(self, length):
            self.length = length
    class FakeMP3:
        def __init__(self, p):
            pass
    def fake_init(self, p):
        self.info = FakeInfo(120.5)
    monkeypatch.setattr(mutagen.mp3, 'MP3', FakeMP3)
    monkeypatch.setattr(FakeMP3, '__init__', fake_init)
    service = AudioMetadataService()
    assert service.duration_seconds(path) == 120.5
    def fake_init_zero(self, p): self.info = FakeInfo(0.0)
    monkeypatch.setattr(FakeMP3, '__init__', fake_init_zero)
    assert service.duration_seconds(path) is None
    def fake_init_neg(self, p): self.info = FakeInfo(-5.0)
    monkeypatch.setattr(FakeMP3, '__init__', fake_init_neg)
    assert service.duration_seconds(path) is None
    def fake_init_nan(self, p): self.info = FakeInfo(float('nan'))
    monkeypatch.setattr(FakeMP3, '__init__', fake_init_nan)
    assert service.duration_seconds(path) is None
    def fake_init_inf(self, p): self.info = FakeInfo(float('inf'))
    monkeypatch.setattr(FakeMP3, '__init__', fake_init_inf)
    assert service.duration_seconds(path) is None
