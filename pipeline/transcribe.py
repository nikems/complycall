"""Stage 1 — transcription with speaker separation (ElevenLabs Scribe).

Produces a Transcript of Agent/Customer turns from a .mp3/.wav file.

Speaker labelling:
  * If detect_speaker_roles is enabled (scribe_v2), ElevenLabs returns
    speaker_id values of 'agent' / 'customer' directly.
  * Otherwise diarization returns 'speaker_0', 'speaker_1', ... and we map the
    first speaker to talk to "Agent" (configurable), the rest to "Customer".
"""
from __future__ import annotations

from typing import List, Optional

from .config import TranscriptionConfig
from .schema import Transcript, TranscriptTurn


def _client(api_key: Optional[str]):
    from elevenlabs.client import ElevenLabs

    if not api_key:
        raise RuntimeError(
            "ELEVENLABS_API_KEY is not set. Add it to your environment or .env file."
        )
    return ElevenLabs(api_key=api_key)


def _role_from_speaker(speaker_id: str, first_speaker: str, cfg: TranscriptionConfig) -> str:
    sid = (speaker_id or "").lower()
    if sid in ("agent", "customer"):
        return sid.capitalize()
    # diarization labels like speaker_0 / speaker_1
    is_first = sid == first_speaker
    if cfg.agent_is_first_speaker:
        return "Agent" if is_first else "Customer"
    return "Customer" if is_first else "Agent"


def _group_words_into_turns(words, cfg: TranscriptionConfig) -> List[TranscriptTurn]:
    """Collapse consecutive word tokens from the same speaker into turns."""
    spoken = [w for w in words if getattr(w, "type", "word") in ("word", "spacing", None)]
    real = [w for w in spoken if getattr(w, "type", "word") == "word"]
    first_speaker = (getattr(real[0], "speaker_id", "") or "").lower() if real else ""

    turns: List[TranscriptTurn] = []
    cur_role: Optional[str] = None
    buf: List[str] = []
    start = end = 0.0

    for w in spoken:
        wtype = getattr(w, "type", "word")
        text = getattr(w, "text", "") or ""
        if wtype != "word":
            if buf:
                buf.append(text)
            continue
        role = _role_from_speaker(getattr(w, "speaker_id", ""), first_speaker, cfg)
        if role != cur_role:
            if buf and cur_role is not None:
                turns.append(TranscriptTurn(cur_role, "".join(buf).strip(), start, end))
            cur_role = role
            buf = [text]
            start = float(getattr(w, "start", 0.0) or 0.0)
        else:
            buf.append(text)
        end = float(getattr(w, "end", end) or end)

    if buf and cur_role is not None:
        turns.append(TranscriptTurn(cur_role, "".join(buf).strip(), start, end))
    # normalise double spaces
    for t in turns:
        t.text = " ".join(t.text.split())
    return turns


def transcribe(audio_path: str, cfg: TranscriptionConfig, api_key: Optional[str]) -> Transcript:
    client = _client(api_key)
    kwargs = dict(model_id=cfg.model_id, diarize=cfg.diarize, tag_audio_events=cfg.tag_audio_events)
    if cfg.language_code:
        kwargs["language_code"] = cfg.language_code
    if cfg.detect_speaker_roles:
        kwargs["detect_speaker_roles"] = True

    with open(audio_path, "rb") as fh:
        result = client.speech_to_text.convert(file=fh, **kwargs)

    words = getattr(result, "words", None) or []
    turns = _group_words_into_turns(words, cfg)
    duration = max((t.end for t in turns), default=0.0)
    language = getattr(result, "language_code", "") or getattr(result, "language", "") or ""

    return Transcript(
        audio_file=audio_path,
        language=language,
        duration_sec=round(duration, 2),
        turns=turns,
    )


def transcript_from_words(audio_file: str, words, cfg: TranscriptionConfig,
                          language: str = "", duration: float = 0.0) -> Transcript:
    """Build a Transcript from an already-fetched ElevenLabs word list.

    Useful for testing the turn-grouping logic without a live API call.
    """
    turns = _group_words_into_turns(words, cfg)
    if not duration:
        duration = max((t.end for t in turns), default=0.0)
    return Transcript(audio_file=audio_file, language=language,
                      duration_sec=round(duration, 2), turns=turns)
