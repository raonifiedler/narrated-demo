"""Chamadas ao ffmpeg/ffprobe com erro tipado, mais utilidades de áudio e legenda."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ValidationError


class ErroMidia(RuntimeError):
    """ffmpeg/ffprobe ausente ou com falha."""


def exigir(programa: str) -> str:
    caminho = shutil.which(programa)
    if caminho is None:
        raise ErroMidia(f"'{programa}' não está no PATH (instale o ffmpeg; veja o README)")
    return caminho


def rodar(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    exigir(cmd[0])
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=cwd, check=False)
    if r.returncode != 0:
        raise ErroMidia(f"falhou ({r.returncode}): {' '.join(cmd[:8])} ...\n{r.stderr[-3000:]}")
    return r


def duracao(p: Path) -> float:
    r = rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)])
    try:
        return float(r.stdout.strip())
    except ValueError as e:
        raise ErroMidia(f"{p}: duração ilegível ({r.stdout!r})") from e


class Fluxo(BaseModel):
    codec_type: str
    codec_name: str | None = None
    width: int | None = None
    height: int | None = None
    r_frame_rate: str | None = None
    sample_rate: str | None = None
    nb_read_packets: str | None = None


class _Probe(BaseModel):
    streams: list[Fluxo]


def fluxos(p: Path, contar_quadros: bool = False) -> list[Fluxo]:
    cmd = ["ffprobe", "-v", "error"]
    if contar_quadros:
        cmd += ["-count_packets"]
    cmd += [
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,nb_read_packets",
        "-of",
        "json",
        str(p),
    ]
    try:
        return _Probe.model_validate_json(rodar(cmd).stdout).streams
    except ValidationError as e:
        raise ErroMidia(f"{p}: saída do ffprobe inesperada\n{e}") from e


def quadros(p: Path) -> int:
    v = next((f for f in fluxos(p, contar_quadros=True) if f.codec_type == "video"), None)
    if v is None or v.nb_read_packets is None:
        raise ErroMidia(f"{p}: sem vídeo")
    return int(v.nb_read_packets)


def aparar(origem: Path, destino: Path, limiar_db: int = -45) -> None:
    """Tira o silêncio que o TTS põe no começo e no fim (senão vira pausa entre cenas)."""
    tira = f"silenceremove=start_periods=1:start_threshold={limiar_db}dB:start_silence=0.03"
    rodar(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(origem),
            "-af",
            f"{tira},areverse,{tira},areverse",
            str(destino),
        ]
    )


def para_48k_mono(origem: Path, destino: Path) -> None:
    rodar(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(origem),
            "-af",
            "aresample=48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(destino),
        ]
    )


def concatenar_wav(partes: list[Path], destino: Path, silencio_s: float = 0.6) -> None:
    """Junta WAVs de taxas diferentes (Piper 22,05 kHz, Kokoro 24 kHz) em 48 kHz mono, com silêncio entre eles."""
    if not partes:
        raise ErroMidia("nada para juntar")
    ent: list[str] = []
    fil: list[str] = []
    rotulos = ""
    for i, p in enumerate(partes):
        ent += ["-i", str(p)]
        fil.append(
            f"[{i}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=mono,"
            f"apad=pad_dur={silencio_s:.2f}[p{i}]"
        )
        rotulos += f"[p{i}]"
    fil.append(f"{rotulos}concat=n={len(partes)}:v=0:a=1[a]")
    rodar(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            *ent,
            "-filter_complex",
            ";".join(fil),
            "-map",
            "[a]",
            "-c:a",
            "pcm_s16le",
            str(destino),
        ]
    )


_SIL = re.compile(r"silence_start: (-?[\d.]+).*?silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", re.S)


def silencios(p: Path, ruido_db: int = -40, minimo_s: float = 0.3) -> list[tuple[float, float, float]]:
    """(início, fim, duração) de cada silêncio do 1º fluxo de áudio."""
    r = rodar(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(p),
            "-map",
            "0:a:0",
            "-af",
            f"silencedetect=noise={ruido_db}dB:d={minimo_s}",
            "-f",
            "null",
            "-",
        ]
    )
    return [(float(a), float(b), float(c)) for a, b, c in _SIL.findall(r.stderr)]


def srt_tempo(s: float) -> str:
    ms = round(max(s, 0.0) * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    seg, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{seg:02},{ms:03}"


def srt_segundos(ts: str) -> float:
    h, m, r = ts.split(":")
    s, ms = r.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


_SRT = re.compile(r"(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)\s*\n(.*?)(?:\n\s*\n|\Z)", re.S)


def escrever_srt(cues: list[tuple[float, float, str]], destino: Path) -> None:
    destino.write_text(
        "\n".join(f"{n + 1}\n{srt_tempo(a)} --> {srt_tempo(b)}\n{t}\n" for n, (a, b, t) in enumerate(cues)),
        encoding="utf-8",
    )


def ler_srt(arq: Path) -> list[tuple[float, float, str]]:
    txt = arq.read_text(encoding="utf-8").replace("\r\n", "\n")
    return [(srt_segundos(a), srt_segundos(b), t.strip()) for a, b, t in _SRT.findall(txt)]


def legendas_do_video(mp4: Path, tmp: Path) -> list[tuple[float, float, str]]:
    """Legenda do vídeo: o .srt ao lado (se houver) ou a faixa embutida; nenhuma = lista vazia."""
    lado = mp4.with_suffix(".srt")
    if lado.exists():
        return ler_srt(lado)
    if not any(f.codec_type == "subtitle" for f in fluxos(mp4)):
        return []
    rodar(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-map", "0:s:0", "-f", "srt", str(tmp)])
    return ler_srt(tmp)


def dump(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
