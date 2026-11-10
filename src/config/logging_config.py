from __future__ import annotations

import logging
import platform
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .env_config import Settings


LOG_FILE_NAME = "experiment.log"

CONSOLE_FORMAT = "%(asctime)s | %(levelname)s | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


class ConsoleLogFilter(logging.Filter):
    """Allow only application logs in the console."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name == "__main__" or record.name.startswith("src.")


class LogSetup:
    """Configure console and file logging."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.output_dir = settings.create_output_dir()
        self.log_path = self.output_dir / LOG_FILE_NAME

    @staticmethod
    def setup_bootstrap_logging() -> None:
        """Configure minimal console logging during application startup."""

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.addFilter(ConsoleLogFilter())
        console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))

        logging.basicConfig(
            level=logging.INFO,
            handlers=[console_handler],
            force=True,
        )

    def setup_logging(self) -> None:
        """Configure full file and console logging."""

        file_handler = logging.FileHandler(
            self.log_path,
            mode="a",
            encoding="utf-8",
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT))

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.addFilter(ConsoleLogFilter())
        console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))

        logging.basicConfig(
            level=logging.INFO,
            handlers=[file_handler, console_handler],
            force=True,
        )

        logging.captureWarnings(True)

    def write_log_metadata(self) -> None:
        """Write processing-run metadata to the log file."""

        settings = self.settings

        metadata = [
            "========== New Processing Run ==========",
            (
                "Timestamp                : "
                f"{datetime.now().astimezone().isoformat(timespec='seconds')}"
            ),
            f"Platform                 : {platform.system()} {platform.release()}",
            f"Python Version           : {platform.python_version()}",
            f"Processing Configuration : {settings.config_params_path}",
            f"Input Directory          : {settings.input_dir}",
            f"Output Directory         : {self.output_dir}",
            f"Audio Extensions         : {', '.join(settings.audio_extensions)}",
            f"Max Workers              : {settings.max_workers}",
        ]

        if settings.config_params_path.exists():
            metadata.append(
                f"\n# {settings.config_params_path.name} contents:"
            )

            with settings.config_params_path.open(
                "r",
                encoding="utf-8",
            ) as stream:
                metadata.extend(
                    f"  {line.rstrip()}"
                    for line in stream
                )

        metadata.append("")

        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write("\n".join(metadata) + "\n")

    @staticmethod
    def cleanup() -> None:
        """Close all logging handlers."""

        logging.shutdown()
