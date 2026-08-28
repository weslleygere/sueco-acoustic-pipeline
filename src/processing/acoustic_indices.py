from collections.abc import Iterator
from typing import Any

import numpy as np
from maad import features, sound
from numpy.typing import NDArray

from ..config.processing_config import AcousticIndexConfig
from ..domain.audio_types import LoadedAudio


AcousticIndexValues = dict[str, float | None]
AcousticIndexRow = dict[str, str | float | None]


class AcousticIndexProcessor:
    """Compute acoustic indices independently for each audio channel."""

    def __init__(self, config: AcousticIndexConfig) -> None:
        self.frequency_range_hz = config.frequency_range_hz
        self.compatibility_mode = config.compatibility_mode
        self.low_frequency_band_hz = config.low_frequency_band_hz
        self.mid_frequency_band_hz = config.mid_frequency_band_hz
        self.high_frequency_band_hz = config.high_frequency_band_hz

    def process_audio(self, audio: LoadedAudio) -> list[AcousticIndexRow]:
        """Compute acoustic indices for each audio channel."""

        self._validate_frequency_limits(audio.sample_rate)

        rows: list[AcousticIndexRow] = []

        for channel, wave in self._iter_channels(audio.wave):
            indices = self._compute_indices(wave, audio.sample_rate)
            self._validate_indices(indices)
            rows.append({"channel": channel, **indices})

        return rows

    def _compute_indices(
        self,
        wave: NDArray[np.float64],
        sample_rate: int,
    ) -> AcousticIndexValues:
        """Compute temporal and spectral acoustic indices."""

        indices = self._compute_temporal_indices(wave, sample_rate)
        indices.update(self._compute_spectral_indices(wave, sample_rate))

        return indices

    def _compute_temporal_indices(
        self,
        wave: NDArray[np.float64],
        sample_rate: int,
    ) -> AcousticIndexValues:
        """Compute temporal alpha indices."""

        frame = features.all_temporal_alpha_indices(
            wave,
            sample_rate,
            compatibility=self.compatibility_mode,
        )

        return self._frame_to_dict(frame, "t_")

    def _compute_spectral_indices(
        self,
        wave: NDArray[np.float64],
        sample_rate: int,
    ) -> AcousticIndexValues:
        """Compute spectral alpha indices."""

        sxx_power, tn, fn, _ = sound.spectrogram(
            wave,
            sample_rate,
            flims=self.frequency_range_hz,
            mode="psd",
        )

        frame, _ = features.all_spectral_alpha_indices(
            sxx_power,
            tn,
            fn,
            flim_low=self.low_frequency_band_hz,
            flim_mid=self.mid_frequency_band_hz,
            flim_hi=self.high_frequency_band_hz,
        )

        return self._frame_to_dict(frame, "s_")

    @staticmethod
    def _iter_channels(
        wave: NDArray[np.float64],
    ) -> Iterator[tuple[str, NDArray[np.float64]]]:
        """Yield mono or stereo channel waveforms."""

        if wave.ndim == 1:
            yield "mono", wave
            return

        if wave.ndim == 2 and wave.shape[1] == 1:
            yield "mono", wave[:, 0]
            return

        if wave.ndim == 2 and wave.shape[1] == 2:
            yield "left", wave[:, 0]
            yield "right", wave[:, 1]
            return

        raise ValueError(
            f"Only mono and stereo audio are supported: {wave.shape}"
        )

    def _validate_frequency_limits(self, sample_rate: int) -> None:
        """Validate acoustic-index frequencies against the audio sample rate."""

        if sample_rate <= 0:
            raise ValueError("Sample rate must be greater than 0")

        nyquist = sample_rate / 2

        frequency_ranges = {
            "frequency_bands_hz.low": self.low_frequency_band_hz,
            "frequency_bands_hz.mid": self.mid_frequency_band_hz,
            "frequency_bands_hz.high": self.high_frequency_band_hz,
            "frequency_range_hz": self.frequency_range_hz,
        }

        for name, frequency_range in frequency_ranges.items():
            if frequency_range[1] > nyquist:
                raise ValueError(
                    f"acoustic_indices.{name} upper frequency "
                    f"({frequency_range[1]} Hz) exceeds Nyquist "
                    f"({nyquist} Hz)"
                )

    @staticmethod
    def _frame_to_dict(
        frame: Any,
        prefix: str,
    ) -> AcousticIndexValues:
        """Convert the first DataFrame row into normalized index values."""

        if frame is None or frame.empty:
            return {}

        return {
            f"{prefix}{key}": AcousticIndexProcessor._normalize_value(value)
            for key, value in frame.iloc[0].items()
        }

    @staticmethod
    def _normalize_value(value: Any) -> float | None:
        """Convert an acoustic-index value to a finite Python float."""

        if isinstance(value, bool):
            return None

        try:
            value = float(value)
        except (TypeError, ValueError):
            return None

        return value if np.isfinite(value) else None

    @staticmethod
    def _validate_indices(indices: AcousticIndexValues) -> None:
        """Validate computed acoustic indices."""

        if not indices:
            raise ValueError("No acoustic indices were computed")

        invalid = [
            key
            for key, value in indices.items()
            if value is None
        ]

        if invalid:
            preview = ", ".join(invalid[:10])
            suffix = "..." if len(invalid) > 10 else ""

            raise ValueError(
                f"Invalid acoustic indices: {preview}{suffix}"
            )
