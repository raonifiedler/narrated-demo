"""Montador: um clipe por funcionalidade + narração contínua. A FALA manda no tempo.

Para cada cena:
  - a fala é sintetizada (texto escrito -> dicionário -> TTS) e aparada (sem o silêncio de borda do TTS);
  - o clipe bruto é ajustado para durar a fala + respiro (+ a transição):
      clipe mais longo que a fala  -> acelera até `acel_max` (2x); se ainda sobrar, corta o fim;
      clipe mais curto que a fala  -> desacelera até `desacel_max` (1,4x mais lento); se faltar, congela o
                                      último quadro (a fala continua: nunca há silêncio).
Entre clipes: `xfade`. QA: `silencedetect` reprova pausa > `pausa_max_s`; avisos de roteiro dizem quantas
palavras acrescentar ou quantos segundos de imagem parada sobram, pela taxa de palavras/s do ritmo escolhido.
Saída: 1920x1080, 30 fps, H.264 + AAC; legenda conforme o modo (nenhuma | faixa | queimada | arquivo).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vdia import config, midia, voz


@dataclass
class Clipe:
    nome: str
    texto: str  # fala ESCRITA: vira a legenda; a voz recebe o texto com o dicionário aplicado
    transicao: str = "fade"
    recorte: tuple[int, int, int] | None = None  # (x, y, largura) no quadro do bruto; altura = largura * 9/16


@dataclass
class Ajuste:
    clipe: str
    bruto_s: float
    alvo_s: float
    aceleracao: float
    congelado_s: float
    cortado_s: float


@dataclass
class QA:
    silencios_internos: list[tuple[float, float]]
    maior_pausa_s: float
    pausa_max_s: float
    especificacao_ok: bool
    aprovado: bool


@dataclass
class Resultado:
    video: str
    legenda_srt: str | None
    modo_legenda: str
    duracao_s: float
    falas_s: list[float]
    ajustes: list[Ajuste]
    qa: QA
    avisos_roteiro: list[str] = field(default_factory=list)

    @property
    def zerado(self) -> bool:
        """Pronto para entrega: QA aprovado e nenhum aviso de roteiro."""
        return self.qa.aprovado and not self.avisos_roteiro


def ajustar(
    bruto: Path, alvo: float, destino: Path, m: config.Montagem, recorte: tuple[int, int, int] | None
) -> Ajuste:
    d = midia.duracao(bruto)
    acel = min(max(d / alvo, 1.0 / m.desacel_max), m.acel_max)
    apos = d / acel
    congela = max(alvo - apos, 0.0)
    pre = ""
    if recorte:
        x, y, w = recorte
        h = round(w * 9 / 16)
        pre = f"crop={w}:{h}:{x}:{y},scale={config.LARG}:{config.ALT}:flags=lanczos,"
    vf = (
        f"{pre}setpts=PTS/{acel:.4f},fps={config.FPS},"
        f"scale={config.LARG}:{config.ALT}:force_original_aspect_ratio=decrease,"
        f"pad={config.LARG}:{config.ALT}:(ow-iw)/2:(oh-ih)/2:color={m.fundo},setsar=1,"
        f"tpad=stop_mode=clone:stop_duration={congela + 0.05:.3f},trim=duration={alvo:.3f},setpts=PTS-STARTPTS"
    )
    midia.rodar(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(bruto),
            "-an",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(destino),
        ]
    )
    return Ajuste(
        bruto.stem, round(d, 2), round(alvo, 2), round(acel, 2), round(congela, 2), round(max(apos - alvo, 0.0), 2)
    )


def avisos(nome: str, aj: Ajuste, m: config.Montagem, palavras_por_s: float) -> list[str]:
    saida: list[str] = []
    if aj.cortado_s > 0 or aj.aceleracao > m.aviso_aceleracao:
        falta = max(aj.bruto_s / 1.3 - aj.alvo_s, 0.5)  # ideal: ação no máximo 1,3x mais rápida que o real
        saida.append(
            f"{nome}: fala curta para a ação; acrescente ~{round(falta * palavras_por_s)} palavras "
            f"(~{falta:.0f} s) ou encurte as ações"
        )
    if aj.congelado_s > m.aviso_congelado_s:
        saida.append(
            f"{nome}: {aj.congelado_s:.1f} s de imagem parada; acrescente ação ou encurte a fala "
            f"(~{round(aj.congelado_s * palavras_por_s)} palavras)"
        )
    return saida


def qa_video(mp4: Path, m: config.Montagem, modo_legenda: config.ModoLegenda) -> QA:
    dur = midia.duracao(mp4)
    internos = [(a, c) for a, b, c in midia.silencios(mp4) if b < dur - 0.05]
    maior = max((c for _, c in internos), default=0.0)
    tipos = {f.codec_type: f for f in midia.fluxos(mp4)}
    v, a = tipos.get("video"), tipos.get("audio")
    spec = (
        v is not None
        and v.codec_name == "h264"
        and v.width == config.LARG
        and v.height == config.ALT
        and v.r_frame_rate == f"{config.FPS}/1"
        and a is not None
        and a.codec_name == "aac"
    )
    if modo_legenda == "faixa":
        s = tipos.get("subtitle")
        spec = spec and s is not None and s.codec_name == "mov_text"
    else:
        spec = spec and "subtitle" not in tipos
    return QA(
        [(round(x, 2), round(c, 2)) for x, c in internos],
        round(maior, 2),
        m.pausa_max_s,
        spec,
        spec and maior <= m.pausa_max_s,
    )


def montar(clipes: list[Clipe], brutos: list[Path], proj: config.Projeto, out: Path, nome: str = "video") -> Resultado:
    if len(clipes) != len(brutos) or not clipes:
        raise ValueError(f"{len(clipes)} clipes para {len(brutos)} brutos")
    m = proj.montagem
    modo = proj.legenda.modo
    out.mkdir(parents=True, exist_ok=True)
    n = len(clipes)
    falas: list[Path] = []
    durs: list[float] = []
    for i, c in enumerate(clipes):
        w = out / f"fala{i}.wav"
        durs.append(voz.fala(proj.voz.id, proj.voz.escala, c.texto, w))
        falas.append(w)
    seg = [d + m.respiro_s for d in durs]  # cada segmento na linha do tempo (sem sobreposição)
    ajustes: list[Ajuste] = []
    lista_avisos: list[str] = []
    ajustados: list[Path] = []
    for i, b in enumerate(brutos):
        alvo = seg[i] + (m.transicao_s if i < n - 1 else m.fecho_s)
        dst = out / f"clipe{i}.mp4"
        aj = ajustar(b, alvo, dst, m, clipes[i].recorte)
        aj.clipe = clipes[i].nome
        ajustes.append(aj)
        lista_avisos += avisos(clipes[i].nome, aj, m, proj.voz.palavras_por_s)
        ajustados.append(dst)

    ent: list[str] = []
    for p in ajustados:
        ent += ["-i", str(p.resolve())]
    fil: list[str] = []
    ult = "[0:v]"
    t = 0.0
    for i in range(1, n):
        t += seg[i - 1]
        fil.append(f"{ult}[{i}:v]xfade=transition={clipes[i].transicao}:duration={m.transicao_s}:offset={t:.3f}[v{i}]")
        ult = f"[v{i}]"
    if n == 1:
        fil.append("[0:v]null[v0]")
        ult = "[v0]"
    inicio = [sum(seg[:i]) for i in range(n)]
    for i, w in enumerate(falas):
        ent += ["-i", str(w.resolve())]
        fil.append(f"[{n + i}:a]aresample=48000,adelay={round(inicio[i] * 1000)}:all=1[a{i}]")
    fil.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,apad[aud]")

    srt = out / f"{nome}.srt"
    midia.escrever_srt([(inicio[i], inicio[i] + durs[i], c.texto) for i, c in enumerate(clipes)], srt)
    if modo == "queimada":
        estilo = proj.legenda.estilo.replace("'", "")
        fil.append(f"{ult}subtitles={srt.name}:force_style='{estilo}'[vq]")
        ult = "[vq]"
    total = sum(seg) + m.fecho_s
    mp4 = out / f"{nome}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *ent]
    mapas = ["-map", ult, "-map", "[aud]"]
    if modo == "faixa":
        cmd += ["-i", srt.name]
        mapas += ["-map", f"{2 * n}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=por"]
    cmd += [
        "-filter_complex",
        ";".join(fil),
        *mapas,
        "-t",
        f"{total:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(config.FPS),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        mp4.name,
    ]
    midia.rodar(cmd, cwd=out)  # cwd = out: o filtro `subtitles` recebe só o nome do .srt (sem escapar C:\)
    manter_srt = modo in ("faixa", "queimada", "arquivo")
    if not manter_srt:
        srt.unlink()
    qa = qa_video(mp4, m, modo)
    return Resultado(
        str(mp4),
        str(srt) if manter_srt else None,
        modo,
        round(midia.duracao(mp4), 2),
        [round(x, 2) for x in durs],
        ajustes,
        qa,
        lista_avisos,
    )


def salvar(res: Resultado, out: Path) -> Path:
    arq = out / "metricas.json"
    arq.write_text(json.dumps(asdict(res), ensure_ascii=False, indent=2), encoding="utf-8")
    return arq
