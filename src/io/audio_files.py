from pathlib import Path

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
