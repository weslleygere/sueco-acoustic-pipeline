from .config.env_config import Settings
from .config.processing_config import AcousticIndexConfig, PreprocessingConfig
from .io.audio_files import AudioFileFinder
from .io.audio_io import AudioLoader
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
        if preprocessing_config is None or acoustic_index_config is None:
            raise ValueError(
                "PreprocessingConfig and AcousticIndexConfig are required"
            )
        self.preprocessing_config = preprocessing_config
        self.acoustic_index_config = acoustic_index_config

    def run(self) -> BatchProcessingResult:
        """Run the configured audio processing stages."""

        output_dir = self.settings.create_output_dir()

        audio_file_processor = AudioFileProcessor(
            audio_loader=AudioLoader(),
            input_dir=self.settings.input_dir,
            preprocessing=PreprocessingStage(
                processor=PreProcessor(self.preprocessing_config),
                chunker=AudioChunker(self.preprocessing_config),
            ),
            acoustic_index_processor=AcousticIndexProcessor(
                self.acoustic_index_config
            ),
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
