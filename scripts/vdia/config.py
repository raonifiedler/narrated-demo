"""Caminhos, área de trabalho e `projeto.json` (validado na fronteira com pydantic).

- Área de trabalho: `VDIA_AREA` ou a pasta atual. Nela ficam os projetos (`<area>/<nome>/`) e a fonética
  comum (`<area>/fonetica/dicionario.json`), que vale para todos os vídeos.
- Modelos de voz: `VDIA_MODELOS` ou a pasta de cache do usuário (nunca dentro da skill).
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL = SCRIPTS.parent
ASSETS = Path(__file__).resolve().parent / "assets"
VOZES_JSON = Path(__file__).resolve().parent / "vozes.json"
DICIONARIO_MODELO = SKILL / "fonetica" / "dicionario.json"

FPS = 30

# Formato do quadro. "retrato" = celular em pé (1080 x 1920). `config.LARG` e `config.ALT` valem para o
# projeto lido por último (`ler_projeto` chama `aplicar_formato`) e são lidos na hora do uso, pelo
# __getattr__ do módulo (PEP 562): não são constantes, e paisagem é o padrão.
Formato = Literal["paisagem", "retrato"]
DIMENSOES: dict[str, tuple[int, int]] = {"paisagem": (1920, 1080), "retrato": (1080, 1920)}
_quadro: dict[str, int] = {"LARG": 1920, "ALT": 1080}


def aplicar_formato(formato: str) -> tuple[int, int]:
    if formato not in DIMENSOES:
        raise ErroConfig(f"formato '{formato}' inválido: use {', '.join(DIMENSOES)}")
    larg, alt = DIMENSOES[formato]
    _quadro["LARG"], _quadro["ALT"] = larg, alt
    return larg, alt


def __getattr__(nome: str) -> int:
    if nome in _quadro:
        return _quadro[nome]
    raise AttributeError(f"module 'vdia.config' has no attribute '{nome}'")


ModoLegenda = Literal["nenhuma", "faixa", "queimada", "arquivo"]
PASTAS_PROJETO = ("roteiro", "scripts", "material", "cenas", "montagem", "final")


class ErroConfig(RuntimeError):
    """Arquivo de configuração ausente ou inválido."""


def area() -> Path:
    return Path(os.environ.get("VDIA_AREA") or Path.cwd()).resolve()


def pasta_modelos() -> Path:
    env = os.environ.get("VDIA_MODELOS")
    if env:
        return Path(env).resolve()
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "narrated-demo" / "modelos"


def pasta_fonetica() -> Path:
    return area() / "fonetica"


def dicionario_path() -> Path:
    """Dicionário da área de trabalho; nasce da cópia do modelo da skill (entradas escolhidas + exemplo)."""
    p = pasta_fonetica() / "dicionario.json"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(DICIONARIO_MODELO, p)
    return p


# Ritmo da fala (palavras/min). Padrão 145: faixa confortável de narração institucional e e-learning
# (140 a 150). Acelere só quando o tempo for curto.
RITMOS: dict[str, float] = {"calmo": 130.0, "padrao": 145.0, "agil": 156.0, "rapido": 170.0}
RITMO_PADRAO = "padrao"


def ritmo_ppm(ritmo: str) -> float:
    """'calmo' | 'padrao' | 'agil' | 'rapido' ou um número de palavras/min (60 a 260)."""
    chave = ritmo.strip().lower().replace("ã", "a").replace("á", "a")
    if chave in RITMOS:
        return RITMOS[chave]
    try:
        valor = float(chave.replace(",", "."))
    except ValueError as e:
        raise ErroConfig(f"ritmo '{ritmo}' inválido: use {', '.join(RITMOS)} ou um número") from e
    if not 60 <= valor <= 260:
        raise ErroConfig(f"ritmo {valor} fora da faixa 60 a 260 palavras/min")
    return valor


class Voz(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = "piper-faber"
    # preset ou número em texto ("145"); palavras_por_min é o valor que a calibração mirou
    ritmo: str = RITMO_PADRAO
    # escala de duração: > 1 fala mais devagar (Piper: length_scale; Kokoro: speed = 1/escala)
    escala: float = Field(default=1.4, gt=0.3, lt=3.0)
    palavras_por_min: float = Field(default=RITMOS[RITMO_PADRAO], gt=60, lt=260)
    calibrado_em: str | None = None

    @property
    def palavras_por_s(self) -> float:
        return self.palavras_por_min / 60.0


class Legenda(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modo: ModoLegenda = "faixa"
    # tamanho máximo de cada bloco de legenda; None = 64 no retrato e 90 na paisagem (duas linhas)
    max_caracteres: int | None = Field(default=None, ge=20, le=200)
    # estilo ASS do modo `queimada` (letra grande, contorno, faixa inferior)
    estilo: str = (
        "FontName=Arial,FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BackColour=&H80000000,BorderStyle=4,Outline=1,Shadow=0,MarginV=22"
    )


class Montagem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transicao_s: float = Field(default=0.5, ge=0.0, le=2.0)
    respiro_s: float = Field(default=0.2, ge=0.0, le=1.0)
    fecho_s: float = Field(default=0.6, ge=0.0, le=3.0)
    acel_max: float = Field(default=2.0, ge=1.0, le=4.0)
    desacel_max: float = Field(default=1.4, ge=1.0, le=3.0)
    pausa_max_s: float = Field(default=0.7, gt=0.1, le=3.0)
    aviso_congelado_s: float = Field(default=1.5, ge=0.0)
    aviso_aceleracao: float = Field(default=1.5, ge=1.0)
    fundo: str = "white"


class Gravacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rota: Literal["web", "desktop", "offscreen", "imagens"] = "web"
    zoom_css: float = Field(default=1.0, gt=0.25, le=3.0)
    url: str = "http://127.0.0.1:5173/"


class Nuvem(BaseModel):
    """TTS em nuvem fica DESLIGADO. Ligar exige aprovação explícita do usuário (ver references/seguranca.md)."""

    model_config = ConfigDict(extra="forbid")
    permitida: bool = False
    aprovado_por: str | None = None
    aprovado_em: str | None = None


class Projeto(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    titulo: str = ""
    criado_em: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    formato: Formato = "paisagem"
    voz: Voz = Field(default_factory=Voz)
    legenda: Legenda = Field(default_factory=Legenda)
    montagem: Montagem = Field(default_factory=Montagem)
    gravacao: Gravacao = Field(default_factory=Gravacao)
    nuvem: Nuvem = Field(default_factory=Nuvem)


def achar_projeto(ref: str | None) -> Path:
    """`ref` = nome (na área), caminho, ou None (pasta atual ou um pai com projeto.json)."""
    if ref:
        for cand in (Path(ref), area() / ref):
            if (cand / "projeto.json").exists():
                return cand.resolve()
        raise ErroConfig(f"projeto não encontrado: {ref} (procurei em {Path(ref).resolve()} e {area() / ref})")
    aqui = Path.cwd().resolve()
    for p in (aqui, *aqui.parents):
        if (p / "projeto.json").exists():
            return p
    raise ErroConfig("nenhum projeto.json na pasta atual; use --projeto <nome>")


def ler_projeto(pasta: Path) -> Projeto:
    arq = pasta / "projeto.json"
    try:
        proj = Projeto.model_validate_json(arq.read_text(encoding="utf-8"))
        aplicar_formato(proj.formato)
        return proj
    except FileNotFoundError as e:
        raise ErroConfig(f"falta {arq}") from e
    except ValidationError as e:
        raise ErroConfig(f"{arq} inválido:\n{e}") from e


def salvar_projeto(pasta: Path, p: Projeto) -> None:
    (pasta / "projeto.json").write_text(p.model_dump_json(indent=2) + "\n", encoding="utf-8")


_OBJ = TypeAdapter(dict[str, object])


def ler_json_objeto(arq: Path) -> dict[str, object]:
    """Lê um JSON que precisa ser objeto (dict); qualquer outra forma é erro."""
    try:
        return _OBJ.validate_json(arq.read_bytes())
    except ValidationError as e:
        raise ErroConfig(f"{arq}: esperado um objeto JSON ({e})") from e
