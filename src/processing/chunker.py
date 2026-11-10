# SuEcO: lazy audio streaming, version 1
from collections.abc import Iterator

import soundfile as sf

from ..config.processing_config import PreprocessingConfig
from ..io.audio_io import AudioStreamError, _validate_audio
from ..domain.audio_types import AudioChunk, LoadedAudio


class AudioChunker:
    """Split loaded audio into optional fixed-duration chunks."""

    def __init__(self, config: PreprocessingConfig) -> None:
        self.segment_duration_seconds = config.segment_duration_seconds
        self.segment_overlap_seconds = config.segment_overlap_seconds

    def split(self, audio: LoadedAudio) -> Iterator[AudioChunk]:
        """Yield chunks of an already loaded audio without accumulating copies."""

        if self.segment_duration_seconds is None:
            yield AudioChunk(
                audio=audio,
                index=None,
                start_seconds=0.0,
                end_seconds=self._duration_seconds(audio),
            )
            return

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
        yield from self._split_audio(audio, chunk_samples, chunk_samples - overlap_samples)

    def _split_audio(
        self,
        audio: LoadedAudio,
        chunk_samples: int,
        step_samples: int,
    ) -> Iterator[AudioChunk]:
        """Yield existing-array chunks one at a time, preserving sample bounds."""

        total_samples = audio.wave.shape[0]
        for index, start_sample in enumerate(range(0, total_samples, step_samples)):
            end_sample = min(start_sample + chunk_samples, total_samples)
            yield self._build_chunk(audio, index, start_sample, end_sample)
            if end_sample == total_samples:
                break

    def split_stream(
        self,
        source: sf.SoundFile,
        file_name: str,
    ) -> Iterator[AudioChunk]:
        """Read exactly one original-file chunk at a time as float64.

        The bounds, overlap, last partial chunk and channel layout match split().
        With segmentation disabled, the complete recording must be read once
        because the scientific index functions operate on a full segment.
        """
        frames = source.frames
        sample_rate = source.samplerate

        if frames <= 0:
            raise AudioStreamError(ValueError("Audio contains no samples"))
        if sample_rate <= 0:
            raise AudioStreamError(ValueError("Audio sample rate must be greater than 0"))
        if source.channels not in (1, 2):
            raise AudioStreamError(ValueError(
                f"Only mono and stereo audio are supported, found {source.channels} channels"
            ))

        if self.segment_duration_seconds is None:
            bounds = ((None, 0, frames),)
        else:
            chunk_samples = self._seconds_to_samples(
                self.segment_duration_seconds,
                sample_rate,
                "preprocessing.segmentation.duration_seconds",
            )
            overlap_samples = self._seconds_to_samples(
                self.segment_overlap_seconds,
                sample_rate,
                "preprocessing.segmentation.overlap_seconds",
                allow_zero=True,
            )
            if overlap_samples >= chunk_samples:
                raise ValueError(
                    "preprocessing.segmentation.overlap_seconds must be lower "
                    "than duration_seconds"
                )
            step = chunk_samples - overlap_samples
            bounds = (
                (index, start, min(start + chunk_samples, frames))
                for index, start in enumerate(range(0, frames, step))
            )

        for index, start, end in bounds:
            try:
                source.seek(start)
                wave = source.read(frames=end - start, dtype="float64", always_2d=False)
                if wave.shape[0] != end - start:
                    raise ValueError("Audio ended unexpectedly while reading a segment")
                _validate_audio(wave, sample_rate)
            except Exception as exc:
                raise AudioStreamError(exc) from exc

            yield AudioChunk(
                audio=LoadedAudio(file_name=file_name, wave=wave, sample_rate=sample_rate),
                index=index,
                start_seconds=start / sample_rate,
                end_seconds=end / sample_rate,
            )
            if end == frames:
                break

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
