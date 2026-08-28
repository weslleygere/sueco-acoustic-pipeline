import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any


FrequencyRange = tuple[float, float]


def _load_config(params_json_path: str | Path) -> dict[str, Any]:
    """Load and validate the configuration JSON object."""

    params_path = Path(params_json_path).expanduser().resolve()

    try:
        with params_path.open("r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON configuration: {params_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError("Configuration root must be a JSON object")

    return payload


def _get_required_section(
    payload: dict[str, Any],
    name: str,
    parent: str | None = None,
) -> dict[str, Any]:
    """Return and validate a required configuration section."""

    qualified_name = f"{parent}.{name}" if parent else name
    section = payload.get(name)

    if section is None:
        raise ValueError(f"Missing required section: {qualified_name}")

    if not isinstance(section, dict):
        raise ValueError(f"{qualified_name} section must be an object")

    return section


def _get_required_value(
    section: dict[str, Any],
    section_name: str,
    name: str,
) -> Any:
    """Return a required configuration value."""

    try:
        return section[name]
    except KeyError as exc:
        raise ValueError(
            f"Missing required parameter: {section_name}.{name}"
        ) from exc


@dataclass(slots=True, init=False)
class PreprocessingConfig:
    """Configuration parameters for the preprocessing stage."""

    segment_duration_seconds: float | None
    segment_overlap_seconds: float
    clipping_amplitude_threshold: float
    remove_dc_offset: bool
    target_sample_rate_hz: int | None

    def __init__(self, params_json_path: str | Path) -> None:
        payload = _load_config(params_json_path)
        preprocessing = _get_required_section(payload, "preprocessing")
        segmentation = _get_required_section(
            preprocessing,
            "segmentation",
            "preprocessing",
        )
        quality_control = _get_required_section(
            preprocessing,
            "quality_control",
            "preprocessing",
        )
        signal_processing = _get_required_section(
            preprocessing,
            "signal_processing",
            "preprocessing",
        )

        self.segment_duration_seconds = _get_required_value(
            segmentation,
            "preprocessing.segmentation",
            "duration_seconds",
        )
        self.segment_overlap_seconds = _get_required_value(
            segmentation,
            "preprocessing.segmentation",
            "overlap_seconds",
        )
        self.clipping_amplitude_threshold = _get_required_value(
            quality_control,
            "preprocessing.quality_control",
            "clipping_amplitude_threshold",
        )
        self.remove_dc_offset = _get_required_value(
            signal_processing,
            "preprocessing.signal_processing",
            "remove_dc_offset",
        )
        self.target_sample_rate_hz = _get_required_value(
            signal_processing,
            "preprocessing.signal_processing",
            "target_sample_rate_hz",
        )

        self._validate_params()
        self._normalize_numeric_params()

    def _validate_params(self) -> None:
        """Validate preprocessing parameters."""

        if not isinstance(self.remove_dc_offset, bool):
            raise ValueError(
                "preprocessing.signal_processing.remove_dc_offset "
                "must be boolean"
            )

        threshold = self.clipping_amplitude_threshold
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not isfinite(threshold)
            or not 0 < threshold <= 1
        ):
            raise ValueError(
                "preprocessing.quality_control."
                "clipping_amplitude_threshold must be greater than 0 "
                "and at most 1"
            )

        sample_rate = self.target_sample_rate_hz
        if sample_rate is not None and (
            isinstance(sample_rate, bool)
            or not isinstance(sample_rate, int)
            or sample_rate <= 0
        ):
            raise ValueError(
                "preprocessing.signal_processing.target_sample_rate_hz "
                "must be null or an integer > 0"
            )

        self._validate_segmentation_params()

    def _validate_segmentation_params(self) -> None:
        """Validate segmentation parameters."""

        self._validate_optional_positive_number(
            "preprocessing.segmentation.duration_seconds",
            self.segment_duration_seconds,
        )

        overlap = self.segment_overlap_seconds
        if (
            isinstance(overlap, bool)
            or not isinstance(overlap, (int, float))
            or not isfinite(overlap)
            or overlap < 0
        ):
            raise ValueError(
                "preprocessing.segmentation.overlap_seconds "
                "must be a number >= 0"
            )

        duration = self.segment_duration_seconds
        if duration is None:
            if overlap != 0:
                raise ValueError(
                    "preprocessing.segmentation.overlap_seconds must be 0 "
                    "when segmentation is disabled"
                )
            return

        if overlap >= duration:
            raise ValueError(
                "preprocessing.segmentation.overlap_seconds must be lower "
                "than duration_seconds"
            )

    @staticmethod
    def _validate_optional_positive_number(
        name: str,
        value: Any,
    ) -> None:
        """Validate an optional positive number."""

        if value is None:
            return

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be null or a positive number")

    def _normalize_numeric_params(self) -> None:
        """Normalize preprocessing numeric parameters."""

        self.clipping_amplitude_threshold = float(
            self.clipping_amplitude_threshold
        )

        if self.segment_duration_seconds is not None:
            self.segment_duration_seconds = float(
                self.segment_duration_seconds
            )

        self.segment_overlap_seconds = float(
            self.segment_overlap_seconds
        )


@dataclass(slots=True, init=False)
class AcousticIndexConfig:
    """Configuration parameters for acoustic-index extraction."""

    frequency_range_hz: FrequencyRange
    compatibility_mode: str
    low_frequency_band_hz: FrequencyRange
    mid_frequency_band_hz: FrequencyRange
    high_frequency_band_hz: FrequencyRange

    def __init__(self, params_json_path: str | Path) -> None:
        payload = _load_config(params_json_path)
        acoustic_indices = _get_required_section(
            payload,
            "acoustic_indices",
        )
        frequency_bands = _get_required_section(
            acoustic_indices,
            "frequency_bands_hz",
            "acoustic_indices",
        )

        self.compatibility_mode = _get_required_value(
            acoustic_indices,
            "acoustic_indices",
            "compatibility_mode",
        )
        self.low_frequency_band_hz = self._parse_frequency_range(
            "acoustic_indices.frequency_bands_hz.low",
            _get_required_value(
                frequency_bands,
                "acoustic_indices.frequency_bands_hz",
                "low",
            ),
        )
        self.mid_frequency_band_hz = self._parse_frequency_range(
            "acoustic_indices.frequency_bands_hz.mid",
            _get_required_value(
                frequency_bands,
                "acoustic_indices.frequency_bands_hz",
                "mid",
            ),
        )
        self.high_frequency_band_hz = self._parse_frequency_range(
            "acoustic_indices.frequency_bands_hz.high",
            _get_required_value(
                frequency_bands,
                "acoustic_indices.frequency_bands_hz",
                "high",
            ),
        )
        self.frequency_range_hz = (
            self.low_frequency_band_hz[0],
            self.high_frequency_band_hz[1],
        )

        self._normalize_compatibility_mode()
        self._validate_frequency_bands()

    def _normalize_compatibility_mode(self) -> None:
        """Normalize the MAAD compatibility mode."""

        if not isinstance(self.compatibility_mode, str):
            raise ValueError(
                "acoustic_indices.compatibility_mode must be a string"
            )

        compatibility_mode = self.compatibility_mode.strip().lower()

        if compatibility_mode == "qut":
            self.compatibility_mode = "QUT"
        elif compatibility_mode == "seewave":
            self.compatibility_mode = "seewave"
        else:
            raise ValueError(
                "acoustic_indices.compatibility_mode must be QUT or seewave"
            )

    def _validate_frequency_bands(self) -> None:
        """Validate the order of acoustic-index frequency bands."""

        if self.low_frequency_band_hz[1] > self.mid_frequency_band_hz[0]:
            raise ValueError(
                "acoustic_indices.frequency_bands_hz.low must not overlap mid"
            )

        if self.mid_frequency_band_hz[1] > self.high_frequency_band_hz[0]:
            raise ValueError(
                "acoustic_indices.frequency_bands_hz.mid must not overlap high"
            )

    @staticmethod
    def _parse_frequency_range(
        name: str,
        value: Any,
    ) -> FrequencyRange:
        """Validate and normalize a frequency range."""

        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(
                f"{name} must contain exactly two frequency values"
            )

        low, high = value

        for frequency in (low, high):
            if (
                isinstance(frequency, bool)
                or not isinstance(frequency, (int, float))
                or not isfinite(frequency)
                or frequency < 0
            ):
                raise ValueError(
                    f"{name} must contain finite frequencies >= 0"
                )

        if low >= high:
            raise ValueError(
                f"{name} lower frequency must be lower than upper frequency"
            )

        return float(low), float(high)
