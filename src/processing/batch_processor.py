# SuEcO: lazy audio streaming, version 1
import sys
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import soundfile as sf
from time import monotonic

from ..domain.audio_types import (
    AudioChunk,
    FailedAudio,
    LoadedAudio,
    PreprocessedAudio,
)
from ..io.audio_files import AudioFileFinder
from ..io.audio_io import AudioLoader
from ..io.audio_io import AudioStreamError
from ..processing.acoustic_indices import (
    AcousticIndexProcessor,
    AcousticIndexRow,
)
from ..processing.chunker import AudioChunker
from ..processing.preprocessor import PreProcessor


ReportValue = str | int | float | None | list[str]
ReportRow = dict[str, ReportValue]


class _ConsoleProgressBar:
    """Minimal console progress bar for batch audio processing."""

    def __init__(
        self,
        total: int,
        label: str = "Processing audio files",
    ) -> None:
        self.total = total
        self.label = label
        self.current = 0
        self.started_at = monotonic()
        self.width = 30
        self.stream = sys.stderr
        self.enabled = total > 0 and self.stream.isatty()

    def __enter__(self) -> "_ConsoleProgressBar":
        self._render()
        return self

    def __exit__(self, *_) -> None:
        if self.enabled:
            self._render()
            self.stream.write("\n")
            self.stream.flush()

    def update(self) -> None:
        self.current += 1
        self._render()

    def _render(self) -> None:
        if not self.enabled:
            return

        progress = self.current / self.total
        filled = round(self.width * progress)
        bar = "#" * filled + "-" * (self.width - filled)
        elapsed_seconds = monotonic() - self.started_at

        self.stream.write(
            f"\r{self.label}: [{bar}] {self.current}/{self.total} "
            f"({progress:.0%}) | elapsed {elapsed_seconds:.0f}s"
        )
        self.stream.flush()


@dataclass(slots=True)
class BatchProcessingResult:
    """Container for processing report rows."""

    preprocessing_rows: list[ReportRow] = field(default_factory=list)
    preprocessing_issue_rows: list[ReportRow] = field(default_factory=list)
    acoustic_index_rows: list[ReportRow] = field(default_factory=list)
    acoustic_index_failure_rows: list[ReportRow] = field(default_factory=list)

    def extend(self, result: "BatchProcessingResult") -> None:
        """Append another processing result."""

        self.preprocessing_rows.extend(result.preprocessing_rows)
        self.preprocessing_issue_rows.extend(
            result.preprocessing_issue_rows
        )
        self.acoustic_index_rows.extend(result.acoustic_index_rows)
        self.acoustic_index_failure_rows.extend(
            result.acoustic_index_failure_rows
        )

    @classmethod
    def combine(
        cls,
        results: Iterable["BatchProcessingResult"],
    ) -> "BatchProcessingResult":
        """Combine multiple processing results."""

        combined = cls()

        for result in results:
            combined.extend(result)

        return combined


@dataclass(slots=True)
class PreprocessingStage:
    """Components required for audio preprocessing."""

    processor: PreProcessor
    chunker: AudioChunker


class AudioFileProcessor:
    """Coordinate enabled processing stages for one audio file."""

    def __init__(
        self,
        audio_loader: AudioLoader,
        input_dir: Path,
        preprocessing: PreprocessingStage,
        acoustic_index_processor: AcousticIndexProcessor,
    ) -> None:
        self.audio_loader = audio_loader
        self.input_dir = input_dir.expanduser().resolve()
        self.preprocessing = preprocessing
        self.acoustic_index_processor = acoustic_index_processor

    def process_file(self, file_path: Path) -> BatchProcessingResult:
        """Stream original-file segments through the unchanged scientific stages."""
        try:
            with self.audio_loader.open_audio(file_path) as source:
                return self._process_preprocessing(file_path, source)
        except Exception as exc:
            return self._loading_failure_result(
                file_path,
                FailedAudio(
                    file_name=file_path.name,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                ),
            )

    def _loading_failure_result(
        self,
        file_path: Path,
        failure: FailedAudio,
    ) -> BatchProcessingResult:
        """Route a loading failure to the active processing stage."""

        return BatchProcessingResult(
            preprocessing_issue_rows=[
                self._preprocessing_issue_row(
                    file_path=file_path,
                    stage="loading",
                    error_type=failure.error_type,
                    error_message=failure.error_message,
                )
            ]
        )

    def _process_preprocessing(
        self,
        file_path: Path,
        source: sf.SoundFile,
    ) -> BatchProcessingResult:
        """Process each streamed segment immediately; retain only report rows."""
        try:
            return BatchProcessingResult.combine(
                self._process_chunk(file_path, chunk)
                for chunk in self.preprocessing.chunker.split_stream(source, file_path.name)
            )
        except AudioStreamError as exc:
            # Equivalent to a full-file load error: discard partial results.
            original = exc.original
            return self._loading_failure_result(
                file_path,
                FailedAudio(
                    file_name=file_path.name,
                    error_type=type(original).__name__,
                    error_message=str(original),
                ),
            )
        except Exception as exc:
            return BatchProcessingResult(
                preprocessing_issue_rows=[
                    self._preprocessing_issue_row(
                        file_path=file_path,
                        stage="chunking",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        channels=source.channels,
                    )
                ]
            )

    def _process_chunk(
        self,
        file_path: Path,
        chunk: AudioChunk,
    ) -> BatchProcessingResult:
        """Preprocess and analyze one audio chunk entirely in memory."""

        result = BatchProcessingResult()
        input_channels = self._channel_count(chunk.audio)

        try:
            preprocessed = self.preprocessing.processor.process_audio(
                chunk.audio
            )

        except Exception as exc:
            result.preprocessing_issue_rows.append(
                self._preprocessing_issue_row(
                    file_path=file_path,
                    stage="preprocessing",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    chunk=chunk,
                    channels=input_channels,
                )
            )
            return result

        if isinstance(preprocessed, FailedAudio):
            result.preprocessing_issue_rows.append(
                self._preprocessing_issue_row(
                    file_path=file_path,
                    stage="preprocessing",
                    error_type=preprocessed.error_type,
                    error_message=preprocessed.error_message,
                    chunk=chunk,
                    channels=input_channels,
                    clipped_channels=preprocessed.clipped_channels,
                )
            )
            return result

        clipped_channels = self._removed_channels(preprocessed)

        if clipped_channels:
            result.preprocessing_issue_rows.append(
                self._preprocessing_issue_row(
                    file_path=file_path,
                    stage="preprocessing",
                    error_type="ClippingError",
                    error_message="Clipped channel(s) detected",
                    chunk=chunk,
                    channels=input_channels,
                    clipped_channels=clipped_channels,
                )
            )

        result.preprocessing_rows.append(
            self._preprocessing_row(
                file_path=file_path,
                chunk=chunk,
                audio=preprocessed,
            )
        )

        if self.acoustic_index_processor is not None:
            result.extend(
                self._extract_acoustic_indices(
                    audio=preprocessed.audio,
                    audio_path=file_path,
                    chunk=chunk,
                )
            )

        return result

    def _extract_acoustic_indices(
        self,
        audio: LoadedAudio,
        audio_path: Path,
        chunk: AudioChunk | None = None,
    ) -> BatchProcessingResult:
        """Extract acoustic indices from one audio segment."""

        result = BatchProcessingResult()

        if self.acoustic_index_processor is None:
            return result

        try:
            index_rows = self.acoustic_index_processor.process_audio(audio)

        except Exception as exc:
            result.acoustic_index_failure_rows.append(
                self._acoustic_index_failure_row(
                    audio_path=audio_path,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    audio=audio,
                    chunk=chunk,
                )
            )
            return result

        for index_row in index_rows:
            result.acoustic_index_rows.append(
                self._acoustic_index_row(
                    audio=audio,
                    audio_path=audio_path,
                    indices=index_row,
                    chunk=chunk,
                )
            )

        return result

    def _preprocessing_row(
        self,
        file_path: Path,
        chunk: AudioChunk,
        audio: PreprocessedAudio,
    ) -> ReportRow:
        """Build a preprocessing success row."""

        return {
            "file_name": audio.audio.file_name,
            "input_path": self._input_relative_path(file_path),
            "chunk_index": chunk.index,
            "chunk_start_seconds": chunk.start_seconds,
            "chunk_end_seconds": chunk.end_seconds,
            "input_sample_rate": chunk.audio.sample_rate,
            "output_sample_rate": audio.audio.sample_rate,
            "duration_seconds": (
                audio.audio.wave.shape[0]
                / audio.audio.sample_rate
            ),
            "channels": len(audio.original_channels),
            "saved_channels": audio.saved_channels,
        }

    def _preprocessing_issue_row(
        self,
        file_path: Path,
        stage: str,
        error_type: str,
        error_message: str,
        chunk: AudioChunk | None = None,
        channels: int | None = None,
        clipped_channels: list[str] | None = None,
    ) -> ReportRow:
        """Build a preprocessing issue row."""

        return {
            "file_name": file_path.name,
            "input_path": self._input_relative_path(file_path),
            "stage": stage,
            "chunk_index": (
                chunk.index
                if chunk is not None
                else None
            ),
            "chunk_start_seconds": (
                chunk.start_seconds
                if chunk is not None
                else None
            ),
            "chunk_end_seconds": (
                chunk.end_seconds
                if chunk is not None
                else None
            ),
            "error_type": error_type,
            "error_message": error_message,
            "channels": channels,
            "clipped_channels": clipped_channels or [],
        }

    def _acoustic_index_row(
        self,
        audio: LoadedAudio,
        audio_path: Path,
        indices: AcousticIndexRow,
        chunk: AudioChunk | None = None,
    ) -> ReportRow:
        """Build an acoustic-index result row."""

        duration_seconds = (
            audio.wave.shape[0] / audio.sample_rate
        )

        return {
            "file_name": audio_path.name,
            "audio_path": self._audio_relative_path(audio_path),
            "chunk_index": (
                chunk.index
                if chunk is not None
                else None
            ),
            "chunk_start_seconds": (
                chunk.start_seconds
                if chunk is not None
                else 0.0
            ),
            "chunk_end_seconds": (
                chunk.end_seconds
                if chunk is not None
                else duration_seconds
            ),
            "sample_rate": audio.sample_rate,
            "duration_seconds": duration_seconds,
            **indices,
        }

    def _acoustic_index_failure_row(
        self,
        audio_path: Path,
        error_type: str,
        error_message: str,
        audio: LoadedAudio | None = None,
        chunk: AudioChunk | None = None,
    ) -> ReportRow:
        """Build an acoustic-index failure row."""

        if audio is None:
            duration_seconds = None
            sample_rate = None
            channels = None
        else:
            duration_seconds = (
                audio.wave.shape[0] / audio.sample_rate
            )
            sample_rate = audio.sample_rate
            channels = self._channel_count(audio)

        if chunk is not None:
            chunk_index = chunk.index
            start_seconds = chunk.start_seconds
            end_seconds = chunk.end_seconds

        elif audio is not None:
            chunk_index = None
            start_seconds = 0.0
            end_seconds = duration_seconds

        else:
            chunk_index = None
            start_seconds = None
            end_seconds = None

        return {
            "file_name": audio_path.name,
            "audio_path": self._audio_relative_path(audio_path),
            "chunk_index": chunk_index,
            "chunk_start_seconds": start_seconds,
            "chunk_end_seconds": end_seconds,
            "sample_rate": sample_rate,
            "duration_seconds": duration_seconds,
            "channels": channels,
            "error_type": error_type,
            "error_message": error_message,
        }

    @staticmethod
    def _removed_channels(
        audio: PreprocessedAudio,
    ) -> list[str]:
        """Return channels removed during preprocessing."""

        return [
            channel
            for channel in audio.original_channels
            if channel not in audio.saved_channels
        ]

    @staticmethod
    def _channel_count(
        audio: LoadedAudio,
    ) -> int:
        """Return the physical number of audio channels."""

        return (
            1
            if audio.wave.ndim == 1
            else audio.wave.shape[1]
        )

    def _input_relative_path(
        self,
        file_path: Path,
    ) -> str:
        """Return a path relative to the configured input directory."""

        return (
            file_path
            .expanduser()
            .resolve()
            .relative_to(self.input_dir)
            .as_posix()
        )

    def _audio_relative_path(self, audio_path: Path) -> str:
        """Path of the original recording, relative to INPUT_DIR."""
        return self._input_relative_path(audio_path)


class SequentialBatchProcessor:
    """Process all discovered audio files sequentially."""

    def __init__(
        self,
        audio_file_finder: AudioFileFinder,
        audio_file_processor: AudioFileProcessor,
    ) -> None:
        self.audio_file_finder = audio_file_finder
        self.audio_file_processor = audio_file_processor

    def process_all(self) -> BatchProcessingResult:
        """Process every discovered audio file and collect results."""

        files = self.audio_file_finder.find_files()
        results: list[BatchProcessingResult] = []

        with _ConsoleProgressBar(
            total=len(files)
        ) as progress_bar:
            for file_path in files:
                results.append(
                    self.audio_file_processor.process_file(
                        file_path
                    )
                )
                progress_bar.update()

        return BatchProcessingResult.combine(results)


class ParallelBatchProcessor:
    """Process all discovered audio files concurrently."""

    def __init__(
        self,
        audio_file_finder: AudioFileFinder,
        audio_file_processor: AudioFileProcessor,
        max_workers: int,
    ) -> None:
        self.audio_file_finder = audio_file_finder
        self.audio_file_processor = audio_file_processor
        self.max_workers = max_workers

    def process_all(self) -> BatchProcessingResult:
        """Process every discovered audio file and collect results."""

        files = self.audio_file_finder.find_files()
        results: list[BatchProcessingResult | None] = [
            None
        ] * len(files)

        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_index = {
                executor.submit(
                    self.audio_file_processor.process_file,
                    file_path,
                ): index
                for index, file_path in enumerate(files)
            }

            with _ConsoleProgressBar(
                total=len(files)
            ) as progress_bar:
                for future in as_completed(future_to_index):
                    index = future_to_index[future]
                    results[index] = future.result()
                    progress_bar.update()

        return BatchProcessingResult.combine(
            result
            for result in results
            if result is not None
        )
