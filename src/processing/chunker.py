from ..config.processing_config import PreprocessingConfig
from ..domain.audio_types import AudioChunk, LoadedAudio


class AudioChunker:
    """Split loaded audio into optional fixed-duration chunks."""

    def __init__(self, config: PreprocessingConfig) -> None:
        self.segment_duration_seconds = config.segment_duration_seconds
        self.segment_overlap_seconds = config.segment_overlap_seconds

    def split(self, audio: LoadedAudio) -> list[AudioChunk]:
        """Return one full-recording chunk or multiple configured chunks."""

        if self.segment_duration_seconds is None:
            return [
                AudioChunk(
                    audio=audio,
                    index=None,
                    start_seconds=0.0,
                    end_seconds=self._duration_seconds(audio),
                )
            ]

        chunk_samples = self._seconds_to_samples(
            self.segment_duration_seconds,
            audio.sample_rate,
            "preprocessing.segmentation.duration_seconds",
        )
        overlap_samples = self._seconds_to_samples(
            self.segment_overlap_seconds,
            audio.sample_rate,
            "preprocessing.segmentation.overlap_seconds",
            allow_zero=True,
        )

        if overlap_samples >= chunk_samples:
            raise ValueError(
                "preprocessing.segmentation.overlap_seconds must be lower "
                "than duration_seconds"
            )

        step_samples = chunk_samples - overlap_samples
        return self._split_audio(audio, chunk_samples, step_samples)

    def _split_audio(
        self,
        audio: LoadedAudio,
        chunk_samples: int,
        step_samples: int,
    ) -> list[AudioChunk]:
        """Split audio and keep the final partial chunk."""

        total_samples = audio.wave.shape[0]
        chunks: list[AudioChunk] = []

        for index, start_sample in enumerate(range(0, total_samples, step_samples)):
            end_sample = min(start_sample + chunk_samples, total_samples)

            chunks.append(
                self._build_chunk(
                    audio=audio,
                    index=index,
                    start_sample=start_sample,
                    end_sample=end_sample,
                )
            )

            if end_sample == total_samples:
                break

        return chunks

    @staticmethod
    def _build_chunk(
        audio: LoadedAudio,
        index: int,
        start_sample: int,
        end_sample: int,
    ) -> AudioChunk:
        """Build one audio chunk from sample bounds."""

        chunk_audio = LoadedAudio(
            file_name=audio.file_name,
            wave=audio.wave[start_sample:end_sample].copy(),
            sample_rate=audio.sample_rate,
        )

        return AudioChunk(
            audio=chunk_audio,
            index=index,
            start_seconds=start_sample / audio.sample_rate,
            end_seconds=end_sample / audio.sample_rate,
        )

    @staticmethod
    def _duration_seconds(audio: LoadedAudio) -> float:
        """Return audio duration in seconds."""

        return audio.wave.shape[0] / audio.sample_rate

    @staticmethod
    def _seconds_to_samples(
        seconds: float,
        sample_rate: int,
        name: str,
        allow_zero: bool = False,
    ) -> int:
        """Convert seconds to samples."""

        samples = round(seconds * sample_rate)

        if allow_zero and samples == 0:
            return 0

        if samples < 1:
            raise ValueError(
                f"{name} is too short for the audio sample rate"
            )

        return samples
