"""ROTEIRO.md: a fonte única do texto do vídeo (o usuário revisa e reescreve aqui).

Formato (ver references/roteiro-modelo.md):

    ## 1. Abertura
    **Tela:** [lista de tarefas da semana; o cursor percorre os itens]
    **Fala:** O app de tarefas organiza a semana num só lugar.
    **Prova:** src/paginas/Lista.tsx
    **Transição:** fade
    **Tempo:** (preenchido por `vdia roteiro medir`)

`medir` sintetiza cada fala (voz e ritmo do projeto, com o dicionário), reescreve as linhas **Tempo:** e gera
roteiro/narracao.wav (a narração inteira para ouvir). A legenda usa sempre a **Fala:** escrita.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from vdia import config, midia, pronuncia, voz

_CENA = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$", re.M)
_CAMPO = re.compile(r"^\*\*(Tela|Fala|Prova|Transição|Tempo):\*\*[ \t]*(.*)$", re.M)
TRANSICOES = {
    "fade",
    "fadeblack",
    "fadewhite",
    "smoothleft",
    "smoothright",
    "smoothup",
    "smoothdown",
    "slideleft",
    "slideright",
    "slideup",
    "slidedown",
    "circleopen",
    "circleclose",
    "circlecrop",
    "wipeleft",
    "wiperight",
    "wipeup",
    "wipedown",
    "radial",
    "diagtl",
    "diagtr",
    "dissolve",
    "pixelize",
}


class ErroRoteiro(RuntimeError):
    """ROTEIRO.md fora do formato."""


@dataclass
class Cena:
    numero: int
    titulo: str
    tela: str
    fala: str
    prova: str
    transicao: str


MODELO = """# Roteiro: {titulo}

Revise e reescreva as falas. Uma cena = um clipe = uma funcionalidade. O que não existe no código ou na
tela entra como "proposta" na fala. Depois de editar: `vdia roteiro medir`.

## 1. Abertura
**Tela:** [a tela principal do sistema; o cursor percorre as áreas]
**Fala:** O {titulo} é um aplicativo para (para que serve), e com ele (quem usa) ganha (o que melhora).
**Prova:** (arquivo do código ou tela que comprova)
**Transição:** fade
**Tempo:**

## 2. Primeira funcionalidade
**Tela:** [o que aparece e o que o cursor faz]
**Fala:** (uma frase por ação visível)
**Prova:** (arquivo)
**Transição:** smoothleft
**Tempo:**
"""


def ler(arq: Path) -> list[Cena]:
    if not arq.exists():
        raise ErroRoteiro(f"falta {arq}")
    txt = arq.read_text(encoding="utf-8")
    marcas = list(_CENA.finditer(txt))
    if not marcas:
        raise ErroRoteiro(f"{arq}: nenhuma cena ('## 1. Título')")
    cenas: list[Cena] = []
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(txt)
        campos = {k: v.strip() for k, v in _CAMPO.findall(txt[m.end() : fim])}
        fala = campos.get("Fala", "")
        if not fala or fala.startswith("("):
            raise ErroRoteiro(f"{arq}: cena {m.group(1)} sem **Fala:** escrita")
        trans = campos.get("Transição", "fade") or "fade"
        if trans not in TRANSICOES:
            raise ErroRoteiro(
                f"{arq}: cena {m.group(1)}: transição '{trans}' desconhecida ({', '.join(sorted(TRANSICOES))})"
            )
        cenas.append(Cena(int(m.group(1)), m.group(2), campos.get("Tela", ""), fala, campos.get("Prova", ""), trans))
    return cenas


@dataclass
class Medida:
    cena: Cena
    segundos: float
    palavras: int


def medir(pasta: Path) -> list[Medida]:
    proj = config.ler_projeto(pasta)
    arq = pasta / "roteiro" / "ROTEIRO.md"
    cenas = ler(arq)
    medidas: list[Medida] = []
    with tempfile.TemporaryDirectory() as tmp:
        falas: list[Path] = []
        for c in cenas:
            w = Path(tmp) / f"fala{c.numero}.wav"
            d = voz.fala(proj.voz.id, proj.voz.escala, c.fala, w)
            falas.append(w)
            medidas.append(Medida(c, d, pronuncia.contar_palavras(c.fala)))
        midia.concatenar_wav(falas, pasta / "roteiro" / "narracao.wav", silencio_s=proj.montagem.respiro_s)
    txt = arq.read_text(encoding="utf-8")
    marcas = list(_CENA.finditer(txt))
    partes: list[str] = [txt[: marcas[0].start()]]
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(txt)
        bloco = txt[m.start() : fim]
        md = medidas[i]
        linha = f"**Tempo:** {md.segundos:.1f} s ({md.palavras} palavras, {proj.voz.palavras_por_min:.0f} pal/min)"
        bloco = (
            re.sub(r"^\*\*Tempo:\*\*.*$", linha, bloco, flags=re.M)
            if "**Tempo:**" in bloco
            else bloco.rstrip("\n") + "\n" + linha + "\n\n"
        )
        partes.append(bloco)
    total = sum(m.segundos for m in medidas) + proj.montagem.respiro_s * len(medidas)
    novo = re.sub(r"\n_Total medido:.*\n?$", "", "".join(partes).rstrip("\n"))
    arq.write_text(novo + f"\n_Total medido: {total:.1f} s de fala._\n", encoding="utf-8")
    return medidas
