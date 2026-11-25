"""Conferência opcional da legenda: transcreve o áudio final com faster-whisper (local) e compara com o roteiro.

A legenda entregue continua sendo o texto ESCRITO do roteiro; a transcrição serve só de indício (o Whisper
também erra siglas). O modelo vem do cache local; baixar do Hugging Face exige `--baixar` (decisão do usuário).
Instale o extra: `uv sync --extra whisper`.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vdia import midia


class _Segmento(Protocol):
    @property
    def start(self) -> float: ...
    @property
    def end(self) -> float: ...
    @property
    def text(self) -> str: ...


class _Transcritor(Protocol):
    """A parte do WhisperModel que usamos (tipo fechado na fronteira)."""

    def transcribe(self, audio: str, language: str | None = None) -> tuple[Iterable[_Segmento], object]: ...


class ErroLegenda(RuntimeError):
    """faster-whisper ausente ou modelo fora do cache."""


@dataclass
class Conferencia:
    srt: Path
    similaridade: float  # 0..1 entre o texto do roteiro e a transcrição (palavras normalizadas)
    transcrito: str


def _palavras(t: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ]+", t.lower())


def _carregar(modelo: str, baixar: bool) -> _Transcritor:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ErroLegenda("faster-whisper não instalado: `uv sync --extra whisper`") from e
    try:
        return WhisperModel(modelo, device="cpu", compute_type="int8", local_files_only=not baixar)
    except Exception as e:  # o pacote levanta tipos variados (OSError, huggingface_hub...): repassa com contexto
        raise ErroLegenda(
            f"modelo '{modelo}' indisponível no cache local ({e}). Para baixar do Hugging Face, "
            "peça a aprovação do usuário e rode com --baixar"
        ) from e


def transcrever(mp4: Path, texto_roteiro: str, modelo: str = "small", baixar: bool = False) -> Conferencia:
    m = _carregar(modelo, baixar)
    segmentos, _info = m.transcribe(str(mp4), language="pt")
    cues: list[tuple[float, float, str]] = [(s.start, s.end, s.text.strip()) for s in segmentos]
    srt = mp4.with_suffix(".whisper.srt")
    midia.escrever_srt(cues, srt)
    transcrito = " ".join(t for _, _, t in cues)
    sim = difflib.SequenceMatcher(None, _palavras(texto_roteiro), _palavras(transcrito)).ratio()
    return Conferencia(srt, round(sim, 3), transcrito)
