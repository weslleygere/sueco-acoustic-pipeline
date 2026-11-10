# SuEcO: lazy audio streaming, version 1
from pathlib import Path

import numpy as np
import soundfile as sf
from numpy.typing import NDArray

from ..domain.audio_types import AudioLoadResult, FailedAudio, LoadedAudio


class AudioStreamError(Exception):
    """Carry the original error encountered while streaming soundfile data."""

    def __init__(self, original: Exception) -> None:
        self.original = original
        super().__init__(str(original))


class AudioLoader:
    """Load and validate mono or stereo audio files."""

    def load_audio(self, file_path: Path | str) -> AudioLoadResult:
        """Load a single audio file."""

        path = Path(file_path).expanduser()

        try:
            path = path.resolve()
            wave, sample_rate = sf.read(str(path), dtype="float64")
            wave = np.asarray(wave, dtype=np.float64)

            _validate_audio(wave, sample_rate)

            return LoadedAudio(
                file_name=path.name,
                wave=wave,
                sample_rate=sample_rate,
            )

        except Exception as exc:
            return FailedAudio(
                file_name=path.name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    def open_audio(self, file_path: Path | str) -> sf.SoundFile:
        """Open an audio stream. Caller owns the context manager."""
        path = Path(file_path).expanduser().resolve()
        return sf.SoundFile(str(path))


def _validate_audio(
    wave: NDArray[np.float64],
    sample_rate: int,
) -> None:
    """Validate mono or stereo audio data."""

    if wave.size == 0:
        raise ValueError("Audio contains no samples")

    if wave.ndim not in {1, 2}:
        raise ValueError(f"Unsupported audio shape: {wave.shape}")

    if wave.ndim == 2 and wave.shape[1] not in {1, 2}:
        raise ValueError(
            f"Only mono and stereo audio are supported, "
            f"found {wave.shape[1]} channels"
        )

    if sample_rate <= 0:
        raise ValueError("Audio sample rate must be greater than 0")

    if not np.all(np.isfinite(wave)):
        raise ValueError("Audio contains non-finite samples")
