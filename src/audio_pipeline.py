from pathlib import Path

from .config.env_config import Settings
from .config.processing_config import AcousticIndexConfig, PreprocessingConfig
from .io.audio_files import AudioFileFinder, ProcessedAudioPathBuilder
from .io.audio_io import AudioLoader, ProcessedAudioWriter
from .io.report_writer import ParquetReportWriter
from .processing.acoustic_indices import AcousticIndexProcessor
from .processing.batch_processor import (
    AudioFileProcessor,
    BatchProcessingResult,
    ParallelBatchProcessor,
    PreprocessingStage,
    SequentialBatchProcessor,
)
from .processing.chunker import AudioChunker
from .processing.preprocessor import PreProcessor


class AudioProcessingPipeline:
    """Coordinate the configured audio processing workflow."""

    def __init__(
        self,
        settings: Settings,
        preprocessing_config: PreprocessingConfig | None = None,
        acoustic_index_config: AcousticIndexConfig | None = None,
    ) -> None:
        self.settings = settings
        self.preprocessing_config = preprocessing_config
        self.acoustic_index_config = acoustic_index_config

        self._validate_configuration()

    def run(self) -> BatchProcessingResult:
        """Run the configured audio processing stages."""

        output_dir = self.settings.create_output_dir()

        audio_file_processor = AudioFileProcessor(
            audio_loader=AudioLoader(),
            input_dir=self.settings.input_dir,
            output_dir=output_dir,
            preprocessing=self._build_preprocessing_stage(output_dir),
            acoustic_index_processor=self._build_acoustic_index_processor(),
        )

        audio_file_finder = AudioFileFinder(
            input_dir=self.settings.input_dir,
            audio_extensions=self.settings.audio_extensions,
        )

        if self.settings.max_workers == 1:
            batch_processor = SequentialBatchProcessor(
                audio_file_finder=audio_file_finder,
                audio_file_processor=audio_file_processor,
            )
        else:
            batch_processor = ParallelBatchProcessor(
                audio_file_finder=audio_file_finder,
                audio_file_processor=audio_file_processor,
                max_workers=self.settings.max_workers,
            )

        result = batch_processor.process_all()
        ParquetReportWriter(output_dir).write_reports(result)

        return result

    def _build_preprocessing_stage(
        self,
        output_dir: Path,
    ) -> PreprocessingStage | None:
        """Build the preprocessing stage when enabled."""

        if not self.settings.preprocess_audio:
            return None

        assert self.preprocessing_config is not None

        return PreprocessingStage(
            processor=PreProcessor(self.preprocessing_config),
            chunker=AudioChunker(self.preprocessing_config),
            path_builder=ProcessedAudioPathBuilder(
                input_dir=self.settings.input_dir,
                output_dir=output_dir,
            ),
            writer=ProcessedAudioWriter(),
        )

    def _build_acoustic_index_processor(
        self,
    ) -> AcousticIndexProcessor | None:
        """Build the acoustic-index processor when enabled."""

        if not self.settings.extract_acoustic_indices:
            return None

        assert self.acoustic_index_config is not None
        return AcousticIndexProcessor(self.acoustic_index_config)

    def _validate_configuration(self) -> None:
        """Validate enabled stage configuration."""

        if self.settings.preprocess_audio and self.preprocessing_config is None:
            raise ValueError(
                "PreprocessingConfig is required when PREPROCESS_AUDIO is enabled"
            )

        if (
            self.settings.extract_acoustic_indices
            and self.acoustic_index_config is None
        ):
            raise ValueError(
                "AcousticIndexConfig is required when "
                "EXTRACT_ACOUSTIC_INDICES is enabled"
            )
