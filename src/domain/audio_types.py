from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray


@dataclass(slots=True)
class LoadedAudio:
    """Successfully loaded audio."""

    file_name: str
    wave: NDArray[np.float64]
    sample_rate: int


@dataclass(slots=True)
class PreprocessedAudio:
    """Successfully preprocessed audio with channel provenance."""

    audio: LoadedAudio
    original_channels: list[str]
    saved_channels: list[str]


@dataclass(slots=True)
class FailedAudio:
    """Failed audio loading or processing result."""

    file_name: str
    error_type: str
    error_message: str
    clipped_channels: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AudioChunk:
    """Audio segment and its position in the source recording."""

    audio: LoadedAudio
    index: int | None
    start_seconds: float
    end_seconds: float


AudioLoadResult = LoadedAudio | FailedAudio
PreprocessingResult = PreprocessedAudio | FailedAudio
