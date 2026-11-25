"""Vídeo único (opcional): cartela inicial, uma abertura animada por parte, as partes e o fecho.

Remonta tudo a partir dos finais das partes (só lidos, nunca alterados):
  1. mede cada parte (quadros, silêncio do começo e do fim);
  2. sintetiza o nome falado de cada parte (voz e ritmo do projeto, com o dicionário) e apara;
  3. calcula a linha do tempo em quadros (30 fps): pausa de `pausa_s` antes e depois do nome, já descontada a
     sobreposição das transições; a borda de cada parte é cortada ou congelada (até `ajuste_max_s`) para a pausa
     ficar igual em todas;
  4. grava as cenas de assets/abertura.html (HTML/CSS/canvas local, sem CDN) com Playwright `page.screencast`;
     cena com os mesmos parâmetros e o mesmo HTML não é regravada (`--forcar` regrava todas);
  5. áudio das cenas: nome falado + fundo sonoro discreto gerado no ffmpeg (aevalsrc), nada baixado;
  6. junta numa passada: xfade variado na imagem, acrossfade no áudio, legenda = legendas das partes deslocadas
     + nomes das aberturas (modo do projeto: nenhuma | faixa | queimada | arquivo);
  7. QA: especificação e pausa máxima FORA das aberturas (as pausas delas são intencionais); pausa que a própria
     parte já tem conta como herdada. Quadros de conferência em montagem/quadros/.

Configuração em <projeto>/unico.json (ver `vdia unico --modelo`).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from vdia import config, midia, roteiro, voz

FPS = config.FPS
AQ = 48000 // FPS  # amostras de áudio por quadro (1600)
HTML = config.ASSETS / "abertura.html"
Visual = Literal["ondas", "grade", "particulas", "aneis"]
VISUAIS: tuple[Visual, ...] = ("ondas", "grade", "particulas", "aneis")


class Tema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fundo: str = "#0b1220"
    primaria: str = "#4f8cff"
    acento: str = "#f5b942"
    texto: str = "#eef3ff"
    fonte: str = "Segoe UI, Arial, sans-serif"


class Cartela(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kicker: str = ""
    nome: str
    titulo: str = ""
    mostrar_partes: bool = True  # chips com o nome das partes
    dur_s: float = Field(default=4.5, ge=1.5, le=15)
    visual: Visual = "ondas"


class Parte(BaseModel):
    model_config = ConfigDict(extra="forbid")
    arquivo: str  # relativo à pasta do projeto do vídeo único, ou absoluto
    nome: str  # grande, na tela
    titulo: str = ""  # linha de baixo
    fala: str  # texto ESCRITO do que a voz diz (a pronúncia vem do dicionário)
    visual: Visual = "ondas"
    entra: str = "fade"  # xfade da abertura para a parte
    sai: str = "fadeblack"  # xfade do fim da parte para a próxima abertura (ou o fecho)


class Unico(BaseModel):
    model_config = ConfigDict(extra="forbid")
    marca: str = ""  # texto pequeno no canto (sem logo de instituição)
    tema: Tema = Field(default_factory=Tema)
    abertura: Cartela
    fecho: Cartela
    partes: list[Parte] = Field(min_length=1)
    entrada_primeira: str = "smoothup"
    pausa_s: float = Field(default=0.75, ge=0.3, le=2.0)
    transicao_q: int = Field(default=21, ge=6, le=60)
    transicao_cartela_q: int = Field(default=24, ge=6, le=60)
    ajuste_max_s: float = Field(default=0.5, ge=0.0, le=2.0)
    fundo_sonoro: bool = True


MODELO = Unico(
    marca="Demonstrações",
    abertura=Cartela(kicker="Apresentação", nome="Demonstrações", titulo="Os sistemas em ação"),
    fecho=Cartela(kicker="Fim", nome="Obrigado", titulo="Perguntas?", mostrar_partes=False, dur_s=3.2),
    partes=[
        Parte(
            arquivo="../app-tarefas/final/app-tarefas.mp4",
            nome="App de tarefas",
            titulo="Organizar a semana num só lugar",
            fala="App de tarefas.",
            entra="circleopen",
        )
    ],
)


class ErroUnico(RuntimeError):
    """Parte fora da especificação, gravação de cena curta ou QA reprovado."""


@dataclass
class Medida:
    quadros: int
    lead: float
    tail: float


def medir(mp4: Path) -> Medida:
    v = next((f for f in midia.fluxos(mp4, contar_quadros=True) if f.codec_type == "video"), None)
    if v is None or (v.width, v.height, v.r_frame_rate) != (config.LARG, config.ALT, f"{FPS}/1"):
        raise ErroUnico(f"{mp4}: esperado {config.LARG}x{config.ALT} a {FPS} fps")
    q = int(v.nb_read_packets or 0)
    dur = q / FPS
    sil = midia.silencios(mp4, minimo_s=0.05)
    lead = sil[0][1] if sil and sil[0][0] <= 0.02 else 0.0
    tail = 0.0
    e = midia.rodar(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(mp4),
            "-map",
            "0:a:0",
            "-af",
            "silencedetect=noise=-40dB:d=0.05",
            "-f",
            "null",
            "-",
        ]
    ).stderr
    ultimo_ini = e.rfind("silence_start: ")
    if ultimo_ini >= 0:
        ini = float(e[ultimo_ini + 15 :].split()[0])
        if not sil or sil[-1][1] >= dur - 0.06 or "silence_end" not in e[ultimo_ini:]:
            tail = max(dur - ini, 0.0)
    return Medida(q, lead, tail)


@dataclass
class Cena:
    nome: str
    params: dict[str, object]
    quadros: int
    fala_wav: Path | None
    fala_ini: int  # amostra em que a fala começa
    fala_amostras: int
    legenda: str


def _chave(c: Cena) -> str:
    h = hashlib.sha256(HTML.read_bytes())
    h.update(json.dumps(c.params, sort_keys=True, ensure_ascii=False).encode())
    h.update(str(c.quadros).encode())
    return h.hexdigest()[:16]


def _falar(proj: config.Projeto, texto: str, destino: Path) -> int:
    """Sintetiza, apara e devolve a duração em amostras (48 kHz mono). Reusa se nada mudou."""
    marca = destino.with_suffix(".txt")
    from vdia import pronuncia

    ident = f"{proj.voz.id}|{proj.voz.escala}|{pronuncia.falado(texto)}"
    if destino.exists() and marca.exists() and marca.read_text(encoding="utf-8") == ident:
        return round(voz.duracao_wav(destino) * 48000)
    apar = destino.with_suffix(".apar.wav")
    voz.fala(proj.voz.id, proj.voz.escala, texto, apar)
    midia.para_48k_mono(apar, destino)
    apar.unlink()
    marca.write_text(ident, encoding="utf-8")
    return round(voz.duracao_wav(destino) * 48000)


def _cortar_cena(bruto: Path, c: Cena, destino: Path) -> None:
    """Corta no 1º quadro não branco (fim da página branca) e deixa exatamente c.quadros."""
    e = midia.rodar(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(bruto),
            "-vf",
            "negate,blackdetect=d=0:pix_th=0.06:pic_th=0.98",
            "-an",
            "-f",
            "null",
            "-",
        ]
    ).stderr
    pos = e.find("black_end:")
    if pos < 0:
        raise ErroUnico(f"{bruto}: não achei o início da animação (página branca antes de tocar)")
    ini = float(e[pos + 10 :].split()[0])
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
            f"trim=start={ini:.3f},setpts=PTS-STARTPTS,fps={FPS},tpad=stop_mode=clone:stop_duration=1,"
            f"trim=end_frame={c.quadros},format=yuv420p",
            "-frames:v",
            str(c.quadros),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "14",
            str(destino),
        ]
    )
    sobra = midia.duracao(bruto) - ini
    if midia.quadros(destino) != c.quadros or sobra < c.quadros / FPS - 0.1:
        raise ErroUnico(f"{c.nome}: gravação curta ({sobra:.2f} s de animação para {c.quadros / FPS:.2f} s)")


def _gravar_cenas(cenas: list[Cena], pasta: Path, forcar: bool) -> list[str]:
    from playwright.sync_api import sync_playwright

    def em_dia(c: Cena) -> bool:
        k = pasta / f"{c.nome}.chave"
        return (pasta / f"{c.nome}.mp4").exists() and k.exists() and k.read_text() == _chave(c)

    pendentes = [c for c in cenas if forcar or not em_dia(c)]
    if not pendentes:
        return []
    tmp = pasta / "gravando"
    tmp.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        try:
            ctx = nav.new_context(viewport={"width": config.LARG, "height": config.ALT})
            for c in pendentes:
                pg = ctx.new_page()  # página nova por cena: trocar só o hash não recarrega o documento
                pg.goto(f"{HTML.as_uri()}#{quote(json.dumps(c.params, ensure_ascii=False))}")
                pg.wait_for_function("window.__pronto === true")
                pg.mouse.move(config.LARG - 1, config.ALT - 1)
                bruto = tmp / f"{c.nome}.webm"
                with pg.screencast.start(path=str(bruto), fps=FPS, size={"width": config.LARG, "height": config.ALT}):
                    pg.wait_for_timeout(600)  # página branca: marca do início
                    pg.evaluate("() => window.tocar()")
                    pg.wait_for_function("window.__fim === true", timeout=60000)
                pg.close()
                _cortar_cena(bruto, c, pasta / f"{c.nome}.mp4")
                (pasta / f"{c.nome}.chave").write_text(_chave(c))
        finally:
            nav.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return [c.nome for c in pendentes]


DRONE = (
    "0.30*sin(2*PI*55*t)+0.22*sin(2*PI*82.41*t)+0.16*sin(2*PI*110*t)*(0.7+0.3*sin(2*PI*0.3*t))"
    "+0.08*sin(2*PI*164.81*t+sin(2*PI*0.2*t))"
)
TOQUE = "0.9*sin(2*PI*(46+38*exp(-9*t))*t)*exp(-4.5*t)+0.10*sin(2*PI*880*t)*exp(-6*t)+0.06*sin(2*PI*1318.5*t)*exp(-7*t)"


def _audio_cena(c: Cena, destino: Path, fundo_sonoro: bool) -> None:
    d = c.quadros / FPS
    amostras = c.quadros * AQ
    ent: list[str] = []
    fil: list[str] = []
    mix = ""
    n = 0
    if fundo_sonoro:
        toque_ini = max(int(c.fala_ini - 0.28 * 48000), 0) if c.fala_wav else int(0.6 * 48000)
        ent += [
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc='{DRONE}':s=48000:c=mono:d={d + 0.1:.3f}",
            "-f",
            "lavfi",
            "-i",
            f"aevalsrc='{TOQUE}':s=48000:c=mono:d=2.5",
        ]
        fil += [
            f"[0:a]lowpass=f=700,volume=0.05,afade=t=in:d=0.5,afade=t=out:st={max(d - 0.6, 0):.3f}:d=0.6[dr]",
            f"[1:a]lowpass=f=2500,volume=0.11,adelay={toque_ini}S:all=1[to]",
        ]
        mix, n = "[dr][to]", 2
    else:
        ent += ["-f", "lavfi", "-i", f"anullsrc=r=48000:cl=mono:d={d + 0.1:.3f}"]
        mix, n = "[0:a]", 1
    if c.fala_wav:
        ent += ["-i", str(c.fala_wav)]
        fil.append(f"[{n}:a]adelay={c.fala_ini}S:all=1[fa]")
        mix += "[fa]"
        n += 1
    fil.append(
        f"{mix}amix=inputs={n}:normalize=0:duration=longest,apad,atrim=end_sample={amostras},"
        "aformat=sample_rates=48000:channel_layouts=mono[a]"
    )
    midia.rodar(
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


@dataclass
class ResultadoUnico:
    video: Path
    duracao_s: float
    regravadas: list[str]
    qa: dict[str, object]


def montar(pasta: Path, forcar: bool = False) -> ResultadoUnico:
    proj = config.ler_projeto(pasta)
    cfg = Unico.model_validate_json((pasta / "unico.json").read_bytes())
    for p in cfg.partes:
        for t in (p.entra, p.sai):
            if t not in roteiro.TRANSICOES:
                raise ErroUnico(f"transição desconhecida: {t}")
    cenas_dir, mont = pasta / "cenas", pasta / "montagem"
    final = pasta / "final" / f"{proj.nome}.mp4"
    for d in (cenas_dir, mont, final.parent):
        d.mkdir(parents=True, exist_ok=True)
    tq, tc = cfg.transicao_q, cfg.transicao_cartela_q
    borda = tq + 2
    tema = cfg.tema.model_dump()

    # 1. partes
    finais: list[Path] = []
    for p in cfg.partes:
        f = Path(p.arquivo) if Path(p.arquivo).is_absolute() else (pasta / p.arquivo).resolve()
        if not f.exists():
            raise ErroUnico(f"falta a parte: {f}")
        finais.append(f)
    med = [medir(f) for f in finais]
    ajustes: list[tuple[int, int, int, int]] = []  # quadros cortados/congelados no início e no fim
    for m in med:
        di, df = borda / FPS - m.lead, borda / FPS - m.tail
        ci, pi = max(round(min(-di, cfg.ajuste_max_s) * FPS), 0), max(round(di * FPS), 0)
        cf, pf = max(round(min(-df, cfg.ajuste_max_s) * FPS), 0), max(round(df * FPS), 0)
        ajustes.append((ci, pi, cf, pf))
    q_proj = [m.quadros - ci + pi - cf + pf for m, (ci, pi, cf, pf) in zip(med, ajustes, strict=True)]
    lead_q = [round(m.lead * FPS) - ci + pi for m, (ci, pi, _, _) in zip(med, ajustes, strict=True)]
    tail_q = [round(m.tail * FPS) - cf + pf for m, (_, _, cf, pf) in zip(med, ajustes, strict=True)]

    # 2-3. falas e cenas em quadros
    chips = [p.nome for p in cfg.partes]
    q_ab, q_fe = round(cfg.abertura.dur_s * FPS), round(cfg.fecho.dur_s * FPS)
    cenas: list[Cena] = [
        Cena(
            "00-abertura",
            {
                "visual": cfg.abertura.visual,
                "kicker": cfg.abertura.kicker,
                "nome": cfg.abertura.nome,
                "titulo": cfg.abertura.titulo,
                "marca": cfg.marca,
                "tema": tema,
                "fi": 0.7,
                "chips": chips if cfg.abertura.mostrar_partes else [],
                "dur": q_ab / FPS,
            },
            q_ab,
            None,
            0,
            0,
            "",
        )
    ]
    for k, p in enumerate(cfg.partes):
        w = mont / f"fala-{k + 1:02}.wav"
        am = _falar(proj, p.fala, w)
        t_in = tc if k == 0 else tq
        pausa_q = round(cfg.pausa_s * FPS)
        pre = t_in + 12 if k == 0 else max(t_in, pausa_q - (tail_q[k - 1] - t_in))
        pos = max(tq, pausa_q - (lead_q[k] - tq))
        fala_q = -(-am // AQ)
        q = pre + fala_q + pos
        cenas.append(
            Cena(
                f"{k + 1:02}-abertura",
                {
                    "visual": p.visual,
                    "n": k + 1,
                    "total": len(cfg.partes),
                    "nome": p.nome,
                    "titulo": p.titulo,
                    "marca": cfg.marca,
                    "tema": tema,
                    "fi": pre / FPS,
                    "ff": pre / FPS + am / 48000,
                    "dur": q / FPS,
                },
                q,
                w,
                pre * AQ,
                am,
                p.fala.rstrip("."),
            )
        )
    cenas.append(
        Cena(
            "99-fecho",
            {
                "visual": cfg.fecho.visual,
                "kicker": cfg.fecho.kicker,
                "nome": cfg.fecho.nome,
                "titulo": cfg.fecho.titulo,
                "marca": cfg.marca,
                "tema": tema,
                "fi": 0.5,
                "chips": chips if cfg.fecho.mostrar_partes else [],
                "dur": q_fe / FPS,
            },
            q_fe,
            None,
            0,
            0,
            "",
        )
    )

    # 4-5. gravação (só o que mudou) e áudio
    regravadas = _gravar_cenas(cenas, cenas_dir, forcar)
    for c in cenas:
        _audio_cena(c, mont / f"{c.nome}.wav", cfg.fundo_sonoro)

    # 6. linha do tempo: abertura, (abertura k, parte k) x N, fecho
    itens: list[tuple[str, int]] = [("cena", 0)]
    for k in range(len(cfg.partes)):
        itens += [("cena", k + 1), ("parte", k)]
    itens.append(("cena", len(cenas) - 1))
    trans: list[str] = [cfg.entrada_primeira]
    durs_t: list[int] = [tc]
    for k, p in enumerate(cfg.partes):
        trans += [p.entra, p.sai]
        durs_t += [tq, tc if k == len(cfg.partes) - 1 else tq]
    qd = [cenas[i].quadros if tipo == "cena" else q_proj[i] for tipo, i in itens]
    ini = [0]
    for i in range(1, len(itens)):
        ini.append(ini[-1] + qd[i - 1] - durs_t[i - 1])
    total_q = ini[-1] + qd[-1]

    ent: list[str] = []
    fil: list[str] = []
    for j, (tipo, i) in enumerate(itens):
        nv = len(ent) // 2
        if tipo == "cena":
            c = cenas[i]
            ent += ["-i", str((cenas_dir / f"{c.nome}.mp4").resolve()), "-i", str((mont / f"{c.nome}.wav").resolve())]
            fil.append(f"[{nv}:v]fps={FPS},format=yuv420p,setsar=1,settb=1/{FPS},setpts=PTS-STARTPTS[v{j}]")
            fil.append(f"[{nv + 1}:a]aformat=sample_rates=48000:channel_layouts=mono[a{j}]")
        else:
            ci, pi, cf, pf = ajustes[i]
            ent += ["-i", str(finais[i])]
            q0 = med[i].quadros
            fil.append(
                f"[{nv}:v]fps={FPS},trim=start_frame={ci}:end_frame={q0 - cf},setpts=PTS-STARTPTS,"
                f"tpad=start_mode=clone:start={pi}:stop_mode=clone:stop={pf},format=yuv420p,setsar=1,"
                f"settb=1/{FPS},setpts=PTS-STARTPTS[v{j}]"
            )
            fil.append(
                f"[{nv}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=mono,"
                f"atrim=start_sample={ci * AQ}:end_sample={(q0 - cf) * AQ},asetpts=PTS-STARTPTS,"
                f"adelay={pi * AQ}S:all=1,apad,atrim=end_sample={q_proj[i] * AQ}[a{j}]"
            )
    uv, ua = "[v0]", "[a0]"
    for j in range(1, len(itens)):
        fil.append(
            f"{uv}[v{j}]xfade=transition={trans[j - 1]}:duration={durs_t[j - 1] / FPS:.4f}:"
            f"offset={ini[j] / FPS - 0.002:.6f}[x{j}]"
        )
        fil.append(f"{ua}[a{j}]acrossfade=ns={durs_t[j - 1] * AQ}:c1=tri:c2=tri[y{j}]")
        uv, ua = f"[x{j}]", f"[y{j}]"

    # legenda: partes deslocadas + nomes das aberturas
    cues: list[tuple[float, float, str]] = []
    for j, (tipo, i) in enumerate(itens):
        t0 = ini[j] / FPS
        if tipo == "cena":
            c = cenas[i]
            if c.fala_wav:
                a = t0 + c.fala_ini / 48000
                cues.append((a - 0.25, a + c.fala_amostras / 48000 + 0.35, c.legenda))
        else:
            ci, pi, _, _ = ajustes[i]
            desloc = t0 + (pi - ci) / FPS
            fim_seg = t0 + q_proj[i] / FPS
            for a, b, txt in midia.legendas_do_video(finais[i], mont / f"legenda-{i + 1:02}.srt"):
                a2, b2 = max(a + desloc, t0), min(b + desloc, fim_seg - durs_t[j] / FPS)
                if b2 > a2:
                    cues.append((a2, b2, txt))
    cues.sort()
    srt = mont / f"{proj.nome}.srt"
    midia.escrever_srt(cues, srt)
    modo = proj.legenda.modo
    if modo == "queimada":
        fil.append(f"{uv}subtitles={srt.name}:force_style='{proj.legenda.estilo.replace(chr(39), '')}'[xq]")
        uv = "[xq]"
    (mont / "filtro.txt").write_text(";\n".join(fil), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *ent]
    mapas = ["-map", uv, "-map", ua]
    if modo == "faixa":
        cmd += ["-i", srt.name]
        mapas += ["-map", f"{len(ent) // 2}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=por"]
    cmd += [
        "-/filter_complex",
        "filtro.txt",
        *mapas,
        "-frames:v",
        str(total_q),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(final.resolve()),
    ]
    midia.rodar(cmd, cwd=mont)
    if modo in ("faixa", "queimada", "arquivo"):
        shutil.copyfile(srt, final.with_suffix(".srt"))
    else:
        final.with_suffix(".srt").unlink(missing_ok=True)

    # 7. QA
    janelas = [
        (ini[j] / FPS - 0.05, (ini[j] + qd[j]) / FPS + 0.05) for j, (tipo, _) in enumerate(itens) if tipo == "cena"
    ]
    limites: list[tuple[float, float, float]] = []
    for j, (tipo, i) in enumerate(itens):
        if tipo == "parte":
            dur_i = med[i].quadros / FPS
            proprio = max((c for _, b, c in midia.silencios(finais[i]) if b < dur_i - 0.05), default=0.0)
            limites.append((ini[j] / FPS, (ini[j] + qd[j]) / FPS, max(proj.montagem.pausa_max_s, proprio + 0.01)))
    qa = _qa(final, janelas, limites, proj.montagem.pausa_max_s, modo)
    _quadros_conferencia(final, mont, itens, ini, qd, durs_t, cenas)
    marcos = [
        {
            "item": cenas[i].nome if tipo == "cena" else cfg.partes[i].nome,
            "inicio_s": round(ini[j] / FPS, 2),
            "dur_s": round(qd[j] / FPS, 2),
        }
        for j, (tipo, i) in enumerate(itens)
    ]
    (mont / "metricas.json").write_text(
        midia.dump(
            {"duracao_s": round(midia.duracao(final), 2), "linha_do_tempo": marcos, "qa": qa, "regravadas": regravadas}
        ),
        encoding="utf-8",
    )
    return ResultadoUnico(final, round(midia.duracao(final), 2), regravadas, qa)


def _qa(
    mp4: Path,
    janelas: list[tuple[float, float]],
    limites: list[tuple[float, float, float]],
    pausa_max: float,
    modo: config.ModoLegenda,
) -> dict[str, object]:
    tipos = {f.codec_type: f for f in midia.fluxos(mp4)}
    v, a = tipos.get("video"), tipos.get("audio")
    spec = (
        v is not None
        and v.codec_name == "h264"
        and v.width == config.LARG
        and v.height == config.ALT
        and v.r_frame_rate == f"{FPS}/1"
        and a is not None
        and a.codec_name == "aac"
    )
    s = tipos.get("subtitle")
    spec = spec and ((s is not None and s.codec_name == "mov_text") if modo == "faixa" else s is None)
    fora = [(x, c) for x, b, c in midia.silencios(mp4) if not any(x < j1 and b > j0 for j0, j1 in janelas)]

    def limite(x: float) -> float:
        return next((lim for l0, l1, lim in limites if l0 <= x < l1), pausa_max)

    acima = [(x, c) for x, c in fora if c > limite(x)]
    herdadas = [(x, c) for x, c in fora if pausa_max < c <= limite(x)]
    return {
        "especificacao_ok": spec,
        "maior_pausa_fora_das_aberturas_s": round(max((c for _, c in fora), default=0.0), 3),
        "herdadas_das_partes": [[round(x, 2), round(c, 3)] for x, c in herdadas],
        "reprovadas": [[round(x, 2), round(c, 3)] for x, c in acima],
        "aprovado": spec and not acima,
    }


def _quadros_conferencia(
    mp4: Path,
    mont: Path,
    itens: list[tuple[str, int]],
    ini: list[int],
    qd: list[int],
    durs_t: list[int],
    cenas: list[Cena],
) -> None:
    """Por abertura: [meio da transição de entrada | nome | meio da transição de saída] num PNG."""
    pasta = mont / "quadros"
    shutil.rmtree(pasta, ignore_errors=True)
    pasta.mkdir()
    for j, (tipo, i) in enumerate(itens):
        if tipo != "cena":
            continue
        c = cenas[i]
        tempos: list[int] = []
        if j > 0:
            tempos.append(ini[j] + durs_t[j - 1] // 2)
        tempos.append(ini[j] + ((c.fala_ini + c.fala_amostras) // AQ if c.fala_wav else qd[j] // 2))
        if j < len(itens) - 1:
            tempos.append(ini[j] + qd[j] - durs_t[j] // 2)
        sel = "+".join(f"eq(n\\,{t})" for t in tempos)
        midia.rodar(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(mp4),
                "-vf",
                f"select='{sel}',scale=640:360,tile={len(tempos)}x1:padding=6:color=white",
                "-frames:v",
                "1",
                "-update",
                "1",
                str(pasta / f"{c.nome}.png"),
            ]
        )
