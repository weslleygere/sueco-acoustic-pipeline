from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class Settings:
    """Application settings loaded from environment variables."""

    config_params_path: Path
    input_dir: Path
    output_dir_base: Path
    audio_extensions: tuple[str, ...]
    preprocess_audio: bool = True
    extract_acoustic_indices: bool = False
    max_workers: int = -1
    output_dir: Path | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        """Normalize and validate settings."""

        self.config_params_path = self.config_params_path.expanduser().resolve()
        self.input_dir = self.input_dir.expanduser().resolve()
        self.output_dir_base = self.output_dir_base.expanduser().resolve()
        self.audio_extensions = self._normalize_audio_extensions(
            self.audio_extensions
        )
        self.max_workers = self._resolve_max_workers(self.max_workers)

        self._validate_processing_stages()
        self._validate_processing_config_file()
        self._validate_input_dir()
        self._ensure_output_base_dir()

    @classmethod
    def from_env(cls) -> Settings:
        """Create settings from environment variables."""

        load_dotenv()

        return cls(
            config_params_path=Path(
                os.getenv("CONFIG_PARAMS_PATH", "config_params.json")
            ),
            input_dir=Path(os.getenv("INPUT_DIR", "input")),
            output_dir_base=Path(os.getenv("OUTPUT_DIR", "output")),
            audio_extensions=cls._parse_audio_extensions(
                os.getenv("AUDIO_EXTENSIONS", ".wav,.flac,.aif,.aiff,.ogg")
            ),
            preprocess_audio=cls._parse_bool(
                os.getenv("PREPROCESS_AUDIO", "true"),
                "PREPROCESS_AUDIO",
            ),
            extract_acoustic_indices=cls._parse_bool(
                os.getenv("EXTRACT_ACOUSTIC_INDICES", "false"),
                "EXTRACT_ACOUSTIC_INDICES",
            ),
            max_workers=cls._parse_max_workers(
                os.getenv("MAX_WORKERS", "-1")
            ),
        )

    def _validate_processing_stages(self) -> None:
        """Validate enabled processing stages."""

        if not isinstance(self.preprocess_audio, bool):
            raise ValueError("PREPROCESS_AUDIO must be a boolean")

        if not isinstance(self.extract_acoustic_indices, bool):
            raise ValueError("EXTRACT_ACOUSTIC_INDICES must be a boolean")

        if not self.preprocess_audio and not self.extract_acoustic_indices:
            raise ValueError(
                "At least one processing stage must be enabled: "
                "PREPROCESS_AUDIO or EXTRACT_ACOUSTIC_INDICES"
            )

    def _validate_processing_config_file(self) -> None:
        """Validate the processing configuration file."""

        if not self.config_params_path.exists():
            raise FileNotFoundError(
                f"Processing configuration file not found: "
                f"{self.config_params_path}"
            )

        if not self.config_params_path.is_file():
            raise ValueError(
                f"Processing configuration path is not a file: "
                f"{self.config_params_path}"
            )

        if self.config_params_path.suffix.lower() != ".json":
            raise ValueError(
                f"CONFIG_PARAMS_PATH must point to a .json file: "
                f"{self.config_params_path}"
            )

    def _validate_input_dir(self) -> None:
        """Validate the input directory."""

        if not self.input_dir.exists():
            raise FileNotFoundError(
                f"Input directory not found: {self.input_dir}"
            )

        if not self.input_dir.is_dir():
            raise NotADirectoryError(
                f"INPUT_DIR is not a directory: {self.input_dir}"
            )

    def _ensure_output_base_dir(self) -> None:
        """Ensure the output base directory exists."""

        if self.output_dir_base.exists():
            if not self.output_dir_base.is_dir():
                raise NotADirectoryError(
                    f"OUTPUT_DIR is not a directory: {self.output_dir_base}"
                )
            return

        self.output_dir_base.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _parse_audio_extensions(
        raw_extensions: str,
    ) -> tuple[str, ...]:
        """Parse comma-separated audio extensions."""

        return tuple(
            extension.strip()
            for extension in raw_extensions.split(",")
            if extension.strip()
        )

    @staticmethod
    def _normalize_audio_extensions(
        extensions: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Normalize and validate audio extensions."""

        normalized: list[str] = []

        for extension in extensions:
            extension = extension.strip().lower()

            if not extension:
                continue

            if not extension.startswith("."):
                extension = f".{extension}"

            if extension == "." or "/" in extension or "\\" in extension:
                raise ValueError(
                    f"Invalid audio extension: {extension}"
                )

            if extension not in normalized:
                normalized.append(extension)

        if not normalized:
            raise ValueError(
                "AUDIO_EXTENSIONS must contain at least one extension"
            )

        return tuple(normalized)

    @staticmethod
    def _parse_bool(raw_value: str, variable_name: str) -> bool:
        """Parse a boolean environment variable."""

        value = raw_value.strip().lower()

        if value in {"true", "1", "yes", "on"}:
            return True

        if value in {"false", "0", "no", "off"}:
            return False

        raise ValueError(
            f"{variable_name} must be true or false"
        )

    @staticmethod
    def _parse_max_workers(raw_value: str) -> int:
        """Parse MAX_WORKERS from the environment."""

        try:
            return int(raw_value)
        except ValueError as exc:
            raise ValueError(
                "MAX_WORKERS must be -1 or an integer >= 1"
            ) from exc

    @staticmethod
    def _resolve_max_workers(max_workers: int) -> int:
        """Validate MAX_WORKERS and resolve automatic worker count."""

        if isinstance(max_workers, bool) or not isinstance(max_workers, int):
            raise ValueError(
                "MAX_WORKERS must be -1 or an integer >= 1"
            )

        if max_workers == -1:
            return max((os.cpu_count() or 1) - 1, 1)

        if max_workers < 1:
            raise ValueError(
                "MAX_WORKERS must be -1 or an integer >= 1"
            )

        return max_workers

    def create_output_dir(self) -> Path:
        """Create and return the output directory for the current run."""

        if self.output_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.output_dir = self.output_dir_base / timestamp
            self.output_dir.mkdir(parents=True, exist_ok=True)

        return self.output_dir
