import logging
import sys

from src.audio_pipeline import AudioProcessingPipeline
from src.config.env_config import Settings
from src.config.logging_config import LogSetup
from src.config.processing_config import AcousticIndexConfig, PreprocessingConfig


REQUIRED_PYTHON = (3, 14)


def _validate_python_version() -> None:
    """Require the standardized Python minor version."""

    if sys.version_info[:2] != REQUIRED_PYTHON:
        raise RuntimeError(
            "This project requires Python 3.14.x; "
            f"found {sys.version_info.major}.{sys.version_info.minor}."
        )


def main() -> None:
    """Run the configured audio processing pipeline."""

    _validate_python_version()
    LogSetup.setup_bootstrap_logging()
    logger = logging.getLogger(__name__)

    log_setup: LogSetup | None = None

    try:
        settings = Settings.from_env()

        log_setup = LogSetup(settings)
        log_setup.setup_logging()
        log_setup.write_log_metadata()

        logger.info(
            "Starting audio processing pipeline. "
            "Preprocessing: %s | Acoustic indices: %s",
            settings.preprocess_audio,
            settings.extract_acoustic_indices,
        )

        preprocessing_config = (
            PreprocessingConfig(settings.config_params_path)
            if settings.preprocess_audio
            else None
        )

        acoustic_index_config = (
            AcousticIndexConfig(settings.config_params_path)
            if settings.extract_acoustic_indices
            else None
        )

        result = AudioProcessingPipeline(
            settings=settings,
            preprocessing_config=preprocessing_config,
            acoustic_index_config=acoustic_index_config,
        ).run()

        logger.info(
            "Audio processing pipeline completed. "
            "Preprocessed outputs: %s | Preprocessing issues: %s | "
            "Acoustic index rows: %s | Acoustic index failures: %s | "
            "Output directory: %s",
            len(result.preprocessing_rows),
            len(result.preprocessing_issue_rows),
            len(result.acoustic_index_rows),
            len(result.acoustic_index_failure_rows),
            settings.output_dir,
        )

    except Exception:
        logger.exception(
            "An unexpected error occurred during audio processing."
        )
        raise

    finally:
        if log_setup is not None:
            log_setup.cleanup()


if __name__ == "__main__":
    main()
