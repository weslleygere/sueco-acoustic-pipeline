from pathlib import Path

from ..domain.audio_types import PreprocessedAudio


class AudioFileFinder:
    """Find audio files recursively under an input directory."""

    def __init__(
        self,
        input_dir: Path,
        audio_extensions: tuple[str, ...],
    ) -> None:
        self.input_dir = input_dir
        self.audio_extensions = self._normalize_extensions(audio_extensions)

    def find_files(self) -> list[Path]:
        """Return matching audio files in deterministic relative-path order."""

        return sorted(
            (
                path
                for path in self.input_dir.rglob("*")
                if path.is_file()
                and path.suffix.lower() in self.audio_extensions
            ),
            key=self.relative_path,
        )

    def relative_path(self, file_path: Path) -> Path:
        """Return a file path relative to the input directory."""

        return file_path.relative_to(self.input_dir)

    @staticmethod
    def _normalize_extensions(
        audio_extensions: tuple[str, ...],
    ) -> frozenset[str]:
        """Normalize audio extensions."""

        return frozenset(
            extension.lower()
            if extension.startswith(".")
            else f".{extension.lower()}"
            for extension in (
                extension.strip()
                for extension in audio_extensions
            )
            if extension
        )


class ProcessedAudioPathBuilder:
    """Build traceable FLAC output paths for preprocessed audio."""

    def __init__(self, input_dir: Path, output_dir: Path) -> None:
        self.input_dir = input_dir
        self.processed_audio_dir = output_dir / "processed_audio"

    def build_path(
        self,
        input_file_path: Path,
        audio: PreprocessedAudio,
        chunk_index: int | None = None,
    ) -> Path:
        """Return the processed FLAC output path."""

        relative_path = input_file_path.relative_to(self.input_dir)
        output_dir = self.processed_audio_dir / relative_path.parent

        original_extension = input_file_path.suffix.lower().lstrip(".")
        output_stem = f"{input_file_path.stem}_{original_extension}"

        if chunk_index is not None:
            output_stem = f"{output_stem}_chunk_{chunk_index:06d}"

        channel_suffix = self._channel_suffix(audio)

        return output_dir / f"{output_stem}_{channel_suffix}.flac"

    @staticmethod
    def _channel_suffix(audio: PreprocessedAudio) -> str:
        """Return a suffix describing the processed channel layout."""

        original = audio.original_channels
        saved = audio.saved_channels

        if original == ["mono"] and saved == ["mono"]:
            return "mono"

        if original == ["left", "right"] and saved == ["left", "right"]:
            return "stereo"

        if original == ["left", "right"] and saved == ["left"]:
            return "mono_left"

        if original == ["left", "right"] and saved == ["right"]:
            return "mono_right"

        raise ValueError(
            f"Unsupported channel configuration: original={original}, saved={saved}"
        )
