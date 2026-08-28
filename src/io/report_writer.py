from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from ..processing.batch_processor import BatchProcessingResult, ReportRow


PREPROCESSING_SCHEMA = pa.schema(
    [
        ("file_name", pa.string()),
        ("input_path", pa.string()),
        ("processed_path", pa.string()),
        ("chunk_index", pa.int64()),
        ("chunk_start_seconds", pa.float64()),
        ("chunk_end_seconds", pa.float64()),
        ("input_sample_rate", pa.int64()),
        ("output_sample_rate", pa.int64()),
        ("duration_seconds", pa.float64()),
        ("channels", pa.int64()),
        ("saved_channels", pa.list_(pa.string())),
    ]
)

PREPROCESSING_ISSUE_SCHEMA = pa.schema(
    [
        ("file_name", pa.string()),
        ("input_path", pa.string()),
        ("stage", pa.string()),
        ("chunk_index", pa.int64()),
        ("chunk_start_seconds", pa.float64()),
        ("chunk_end_seconds", pa.float64()),
        ("error_type", pa.string()),
        ("error_message", pa.string()),
        ("channels", pa.int64()),
        ("clipped_channels", pa.list_(pa.string())),
    ]
)

ACOUSTIC_INDEX_METADATA_SCHEMA = pa.schema(
    [
        ("file_name", pa.string()),
        ("audio_path", pa.string()),
        ("chunk_index", pa.int64()),
        ("chunk_start_seconds", pa.float64()),
        ("chunk_end_seconds", pa.float64()),
        ("sample_rate", pa.int64()),
        ("duration_seconds", pa.float64()),
        ("channel", pa.string()),
    ]
)

ACOUSTIC_INDEX_FAILURE_SCHEMA = pa.schema(
    [
        ("file_name", pa.string()),
        ("audio_path", pa.string()),
        ("chunk_index", pa.int64()),
        ("chunk_start_seconds", pa.float64()),
        ("chunk_end_seconds", pa.float64()),
        ("sample_rate", pa.int64()),
        ("duration_seconds", pa.float64()),
        ("channels", pa.int64()),
        ("error_type", pa.string()),
        ("error_message", pa.string()),
    ]
)


class ParquetReportWriter:
    """Write audio processing results to Parquet files."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def write_reports(
        self,
        result: BatchProcessingResult,
    ) -> dict[str, Path]:
        """Write available processing reports and return their paths."""

        self.output_dir.mkdir(parents=True, exist_ok=True)

        report_paths: dict[str, Path] = {}

        if result.preprocessing_rows:
            path = self.output_dir / "preprocessing_success.parquet"
            self._write_parquet(
                path,
                PREPROCESSING_SCHEMA,
                result.preprocessing_rows,
            )
            report_paths["preprocessing"] = path

        if result.preprocessing_issue_rows:
            path = self.output_dir / "preprocessing_issues.parquet"
            self._write_parquet(
                path,
                PREPROCESSING_ISSUE_SCHEMA,
                result.preprocessing_issue_rows,
            )
            report_paths["preprocessing_issues"] = path

        if result.acoustic_index_rows:
            path = self.output_dir / "acoustic_indices.parquet"
            schema = self._acoustic_index_schema(
                result.acoustic_index_rows
            )
            self._write_parquet(
                path,
                schema,
                result.acoustic_index_rows,
            )
            report_paths["acoustic_indices"] = path

        if result.acoustic_index_failure_rows:
            path = self.output_dir / "acoustic_index_failures.parquet"
            self._write_parquet(
                path,
                ACOUSTIC_INDEX_FAILURE_SCHEMA,
                result.acoustic_index_failure_rows,
            )
            report_paths["acoustic_index_failures"] = path

        return report_paths

    @staticmethod
    def _acoustic_index_schema(
        rows: list[ReportRow],
    ) -> pa.Schema:
        """Build the acoustic-index schema from MAAD output columns."""

        metadata_fields = list(ACOUSTIC_INDEX_METADATA_SCHEMA)
        metadata_names = set(ACOUSTIC_INDEX_METADATA_SCHEMA.names)

        index_names: list[str] = []
        seen: set[str] = set()

        for row in rows:
            for name in row:
                if name not in metadata_names and name not in seen:
                    index_names.append(name)
                    seen.add(name)

        index_fields = [
            pa.field(name, pa.float64())
            for name in index_names
        ]

        return pa.schema(metadata_fields + index_fields)

    @staticmethod
    def _write_parquet(
        file_path: Path,
        schema: pa.Schema,
        rows: list[ReportRow],
    ) -> None:
        """Write report rows to Parquet using the supplied schema."""

        table = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(table, file_path)
