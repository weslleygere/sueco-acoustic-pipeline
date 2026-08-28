from math import gcd

import numpy as np
from numpy.typing import NDArray
from scipy.signal import detrend, resample_poly

from ..config.processing_config import PreprocessingConfig
from ..domain.audio_types import (
    FailedAudio,
    LoadedAudio,
    PreprocessedAudio,
    PreprocessingResult,
)


class PreProcessor:
    """Preprocess mono or stereo audio."""

    def __init__(self, config: PreprocessingConfig) -> None:
        self.should_remove_dc_offset = config.remove_dc_offset
        self.clipping_amplitude_threshold = (
            config.clipping_amplitude_threshold
        )
        self.target_sample_rate_hz = config.target_sample_rate_hz

    def process_audio(self, audio: LoadedAudio) -> PreprocessingResult:
        """Preprocess a single audio segment."""

        try:
            original_channels = self._channel_labels(audio.wave)
            clipped_indices = self._get_clipped_channel_indices(audio.wave)

            if len(clipped_indices) == len(original_channels):
                return FailedAudio(
                    file_name=audio.file_name,
                    error_type="ClippingError",
                    error_message="Clipped channel(s) detected",
                    clipped_channels=[
                        original_channels[index]
                        for index in clipped_indices
                    ],
                )

            saved_indices = [
                index
                for index in range(len(original_channels))
                if index not in clipped_indices
            ]
            saved_channels = [
                original_channels[index]
                for index in saved_indices
            ]

            wave = self._select_channels(audio.wave, saved_indices)
            sample_rate = audio.sample_rate

            if self.should_remove_dc_offset:
                wave = self._remove_dc_component(wave)

            wave, sample_rate = self._downsample_audio(wave, sample_rate)

            return PreprocessedAudio(
                audio=LoadedAudio(
                    file_name=audio.file_name,
                    wave=wave,
                    sample_rate=sample_rate,
                ),
                original_channels=original_channels,
                saved_channels=saved_channels,
            )

        except Exception as exc:
            return FailedAudio(
                file_name=audio.file_name,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    def _get_clipped_channel_indices(
        self,
        wave: NDArray[np.float64],
    ) -> list[int]:
        """Return indexes of channels that reach the clipping threshold."""

        if wave.ndim == 1:
            peak = np.max(np.abs(wave))
            return [0] if peak >= self.clipping_amplitude_threshold else []

        peaks = np.max(np.abs(wave), axis=0)

        return np.flatnonzero(
            peaks >= self.clipping_amplitude_threshold
        ).tolist()

    @staticmethod
    def _channel_labels(
        wave: NDArray[np.float64],
    ) -> list[str]:
        """Return channel labels for mono or stereo audio."""

        if wave.ndim == 1:
            return ["mono"]

        if wave.ndim == 2 and wave.shape[1] == 1:
            return ["mono"]

        if wave.ndim == 2 and wave.shape[1] == 2:
            return ["left", "right"]

        raise ValueError(
            f"Only mono and stereo audio are supported: {wave.shape}"
        )

    @staticmethod
    def _select_channels(
        wave: NDArray[np.float64],
        channel_indices: list[int],
    ) -> NDArray[np.float64]:
        """Return only the requested channels."""

        if wave.ndim == 1:
            return wave

        if len(channel_indices) == 1:
            return wave[:, channel_indices[0]]

        return wave[:, channel_indices]

    @staticmethod
    def _remove_dc_component(
        wave: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Remove the constant DC component."""

        return np.asarray(
            detrend(wave, axis=0, type="constant"),
            dtype=np.float64,
        )

    def _downsample_audio(
        self,
        wave: NDArray[np.float64],
        sample_rate: int,
    ) -> tuple[NDArray[np.float64], int]:
        """Downsample audio when configured."""

        target_sample_rate_hz = self.target_sample_rate_hz

        if (
            target_sample_rate_hz is None
            or target_sample_rate_hz == sample_rate
        ):
            return wave, sample_rate

        if target_sample_rate_hz > sample_rate:
            raise ValueError(
                f"target_sample_rate_hz ({target_sample_rate_hz}) must be less "
                f"than or equal to the original sample rate ({sample_rate})"
            )

        divisor = gcd(sample_rate, target_sample_rate_hz)

        wave = resample_poly(
            wave,
            up=target_sample_rate_hz // divisor,
            down=sample_rate // divisor,
            axis=0,
        )

        return np.asarray(wave, dtype=np.float64), target_sample_rate_hz
