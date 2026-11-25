"""Vozes locais (Piper, Kokoro): catálogo, síntese, amostra comparativa e calibração do ritmo.

`escala` é a mesma ideia nos dois motores: > 1 fala mais devagar.
  - Piper: SynthesisConfig(length_scale=escala)
  - Kokoro: create(speed=1/escala)
A calibração mede palavras/min do texto ESCRITO sobre a fala aparada (sem o silêncio de borda do TTS).
"""

from __future__ import annotations

import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import soundfile as sf
from pydantic import BaseModel, ConfigDict

from vdia import config, midia, pronuncia


class ErroVoz(RuntimeError):
    """Voz desconhecida, não instalada ou motor bloqueado."""


class Arquivo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    url: str
    sha256: str


class EntradaVoz(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    motor: Literal["piper", "kokoro"]
    nome: str
    modelo: str
    voz: str | None
    arquivos: list[Arquivo]
    licenca: str
    nota: str


class _Catalogo(BaseModel):
    model_config = ConfigDict(extra="allow")
    vozes: list[EntradaVoz]


def catalogo() -> list[EntradaVoz]:
    return _Catalogo.model_validate_json(config.VOZES_JSON.read_bytes()).vozes


def entrada(voz_id: str) -> EntradaVoz:
    for v in catalogo():
        if v.id == voz_id:
            return v
    ids = ", ".join(v.id for v in catalogo())
    raise ErroVoz(
        f"voz '{voz_id}' não está no catálogo local ({ids}). TTS em nuvem fica desligado: ver references/seguranca.md"
    )


def instalada(v: EntradaVoz) -> bool:
    return all((config.pasta_modelos() / a.nome).exists() for a in v.arquivos)


def instaladas() -> list[EntradaVoz]:
    return [v for v in catalogo() if instalada(v)]


# ── motores ─────────────────────────────────────────────────────────────────────────────────
@dataclass
class _Cache:
    piper: dict[str, object]
    kokoro: dict[str, object]


_CACHE = _Cache({}, {})


def _sintetizar_piper(v: EntradaVoz, texto: str, destino: Path, escala: float) -> None:
    from piper import PiperVoice, SynthesisConfig

    modelo = config.pasta_modelos() / v.modelo
    carregada = _CACHE.piper.get(v.id)
    voz = carregada if isinstance(carregada, PiperVoice) else PiperVoice.load(str(modelo))
    _CACHE.piper[v.id] = voz
    with wave.open(str(destino), "wb") as w:
        voz.synthesize_wav(texto, w, syn_config=SynthesisConfig(length_scale=escala))


def _sintetizar_kokoro(v: EntradaVoz, texto: str, destino: Path, escala: float) -> None:
    from kokoro_onnx import Kokoro

    pasta = config.pasta_modelos()
    carregado = _CACHE.kokoro.get(v.modelo)
    k = carregado if isinstance(carregado, Kokoro) else Kokoro(str(pasta / v.modelo), str(pasta / "voices-v1.0.bin"))
    _CACHE.kokoro[v.modelo] = k
    if v.voz is None:
        raise ErroVoz(f"{v.id}: o catálogo não diz qual voz do Kokoro usar")
    amostras, taxa = k.create(texto, voice=v.voz, speed=1.0 / escala, lang="pt-br")
    sf.write(str(destino), amostras, taxa)


def sintetizar(voz_id: str, texto: str, destino: Path, escala: float) -> float:
    """Sintetiza `texto` (já falado, isto é, com o dicionário aplicado). Devolve o tempo gasto (s)."""
    v = entrada(voz_id)
    if not instalada(v):
        raise ErroVoz(
            f"voz '{voz_id}' não instalada em {config.pasta_modelos()}: rode `vdia instalar {voz_id}` "
            "ou aponte VDIA_MODELOS para a pasta dos modelos"
        )
    t = time.perf_counter()
    destino.parent.mkdir(parents=True, exist_ok=True)
    match v.motor:
        case "piper":
            _sintetizar_piper(v, texto, destino, escala)
        case "kokoro":
            _sintetizar_kokoro(v, texto, destino, escala)
    return time.perf_counter() - t


def duracao_wav(p: Path) -> float:
    i = sf.info(str(p))
    return float(i.frames) / float(i.samplerate)


def fala(voz_id: str, escala: float, texto_escrito: str, destino: Path, com_dicionario: bool = True) -> float:
    """Sintetiza o texto escrito (com o dicionário) e apara o silêncio de borda. Devolve a duração (s)."""
    texto = pronuncia.falado(texto_escrito) if com_dicionario else texto_escrito
    cru = destino.with_name(destino.stem + "-cru.wav")
    sintetizar(voz_id, texto, cru, escala)
    midia.aparar(cru, destino)
    cru.unlink()
    return duracao_wav(destino)


# ── amostra comparativa ─────────────────────────────────────────────────────────────────────
FRASE_AMOSTRA = (
    "Este é o aplicativo de tarefas: você cria uma lista, marca o que já foi feito "
    "e acompanha o andamento da semana num só lugar."
)


def amostra(destino: Path, frase: str = FRASE_AMOSTRA, ids: list[str] | None = None) -> list[EntradaVoz]:
    """Um WAV só com 'Voz 1. <frase>', 'Voz 2. <frase>'... na voz de cada número, mais um .txt com a lista."""
    vozes = [entrada(i) for i in ids] if ids else instaladas()
    vozes = [v for v in vozes if instalada(v)]
    if not vozes:
        raise ErroVoz(f"nenhuma voz instalada em {config.pasta_modelos()}; rode `vdia instalar`")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        partes: list[Path] = []
        for n, v in enumerate(vozes, 1):
            w = Path(tmp) / f"voz{n}.wav"
            fala(v.id, 1.0, f"Voz {n}. {frase}", w)
            partes.append(w)
        midia.concatenar_wav(partes, destino, silencio_s=0.8)
    linhas = [f"Voz {n}: {v.id} ({v.nome}). {v.nota} Licença: {v.licenca}" for n, v in enumerate(vozes, 1)]
    destino.with_suffix(".txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return vozes


# ── ritmo ───────────────────────────────────────────────────────────────────────────────────
TEXTO_CALIBRACAO = (
    "Na tela inicial aparecem as tarefas da semana, separadas por projeto. Ao clicar numa tarefa, o painel "
    "ao lado mostra a descrição, o prazo e quem é o responsável. O filtro no alto deixa só o que vence hoje, "
    "e o botão de concluir risca o item e atualiza o progresso. No fim do dia, o relatório resume o que foi "
    "feito e o que ficou para amanhã, sem planilha à parte."
)


@dataclass
class Calibracao:
    escala: float
    palavras_por_min: float
    alvo: float
    rodadas: list[tuple[float, float]]  # (escala, palavras/min medidas)
    convergiu: bool


def ritmo(voz_id: str, escala: float, texto: str = TEXTO_CALIBRACAO) -> float:
    """Palavras/min do texto escrito na voz e escala dadas (fala aparada)."""
    with tempfile.TemporaryDirectory() as tmp:
        d = fala(voz_id, escala, texto, Path(tmp) / "ritmo.wav")
    return pronuncia.contar_palavras(texto) / d * 60.0


def calibrar(
    voz_id: str,
    alvo: float = config.RITMOS[config.RITMO_PADRAO],
    escala_inicial: float = 1.0,
    tolerancia: float = 0.02,
    max_rodadas: int = 8,
    texto: str = TEXTO_CALIBRACAO,
) -> Calibracao:
    """Procura a escala que dá `alvo` palavras/min. O ritmo é ~ inversamente proporcional à escala."""
    e = escala_inicial
    rodadas: list[tuple[float, float]] = []
    for _ in range(max_rodadas):
        ppm = ritmo(voz_id, e, texto)
        rodadas.append((round(e, 4), round(ppm, 1)))
        if abs(ppm - alvo) / alvo <= tolerancia:
            return Calibracao(round(e, 4), round(ppm, 1), alvo, rodadas, True)
        e = min(max(e * ppm / alvo, 0.4), 2.8)
    melhor = min(rodadas, key=lambda r: abs(r[1] - alvo))
    return Calibracao(melhor[0], melhor[1], alvo, rodadas, False)
