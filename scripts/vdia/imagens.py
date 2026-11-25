"""Clipes de imagens: zoom lento (Ken Burns) sobre prints de telas estáticas, sem gravar nada ao vivo.

O clipe sai em 1920x1080, 30 fps, e entra na montagem como qualquer bruto (a fala ajusta o tempo).
"""

from __future__ import annotations

from pathlib import Path

from vdia import config, midia


def zoom_lento(
    imagem: Path,
    destino: Path,
    duracao_s: float = 6.0,
    zoom_final: float = 1.15,
    foco: tuple[float, float] = (0.5, 0.5),
    fundo: str = "white",
) -> Path:
    """Aproxima de 1,0 até `zoom_final` em `duracao_s`, centrado em `foco` (frações 0..1 da imagem)."""
    if not imagem.exists():
        raise FileNotFoundError(imagem)
    if not 1.0 <= zoom_final <= 3.0:
        raise ValueError("zoom_final entre 1,0 e 3,0")
    n = max(round(duracao_s * config.FPS), 1)
    fx, fy = foco
    larg2, alt2 = config.LARG * 2, config.ALT * 2  # trabalha em 2x para o movimento não tremer
    vf = (
        f"scale={larg2}:{alt2}:force_original_aspect_ratio=decrease,"
        f"pad={larg2}:{alt2}:(ow-iw)/2:(oh-ih)/2:color={fundo},"
        f"zoompan=z='1+({zoom_final}-1)*on/{n}':x='(iw-iw/zoom)*{fx}':y='(ih-ih/zoom)*{fy}':"
        f"d={n}:s={config.LARG}x{config.ALT}:fps={config.FPS},setsar=1,format=yuv420p"
    )
    destino.parent.mkdir(parents=True, exist_ok=True)
    midia.rodar(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(imagem),
            "-vf",
            vf,
            "-frames:v",
            str(n),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            str(destino),
        ]
    )
    return destino
