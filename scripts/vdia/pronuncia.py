"""Dicionário de pronúncia persistente: texto escrito -> como a voz deve falar.

Regras da troca (aplicada em TODA síntese; a legenda usa sempre o texto escrito):
- palavra inteira (não troca dentro de outra palavra nem de palavra com hífen);
- o termo mais longo primeiro ("Node.js" antes de "Node");
- sensível a maiúsculas: "Web" e "web" são entradas diferentes. As variantes de caixa são opcionais
  (`vdia fonetica escolher ... --variantes-caixa` grava minúscula, Título e MAIÚSCULA de uma vez).
- chaves que começam com "_" são comentários e são ignoradas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from vdia import config

_LETRA = r"\wÀ-ÿ"


def ler(arq: Path | None = None) -> dict[str, str]:
    p = arq or config.dicionario_path()
    bruto = config.ler_json_objeto(p)
    saida: dict[str, str] = {}
    for k, v in bruto.items():
        if k.startswith("_"):
            continue
        if not isinstance(v, str):
            raise config.ErroConfig(f"{p}: a entrada '{k}' precisa ser texto (veio {type(v).__name__})")
        saida[k] = v
    return saida


def gravar_entradas(novas: dict[str, str], arq: Path | None = None) -> Path:
    """Acrescenta/atualiza entradas, preservando os comentários ("_...") e a ordem existente."""
    p = arq or config.dicionario_path()
    bruto = config.ler_json_objeto(p)
    bruto.update(novas)
    p.write_text(json.dumps(bruto, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def aplicar(texto: str, dic: dict[str, str]) -> str:
    """Uma passada só (o que já foi trocado não é trocado de novo); alternativas da mais longa à mais curta."""
    if not dic:
        return texto
    termos = "|".join(re.escape(t) for t in sorted(dic, key=len, reverse=True))
    padrao = re.compile(rf"(?<![{_LETRA}-])(?:{termos})(?![{_LETRA}-])")
    return padrao.sub(lambda m: dic[m.group(0)], texto)


def falado(texto: str, extra: dict[str, str] | None = None) -> str:
    """Texto que vai para o TTS (dicionário da área de trabalho + `extra`)."""
    return aplicar(texto, ler() | (extra or {}))


def variantes_caixa(palavra: str, falado_: str) -> dict[str, str]:
    """minúscula, Título e MAIÚSCULA da palavra, todas com a mesma fala."""
    formas = {palavra, palavra.lower(), palavra[:1].upper() + palavra[1:].lower(), palavra.upper()}
    return {f: falado_ for f in sorted(formas)}


def contar_palavras(texto: str) -> int:
    return len(re.findall(rf"[{_LETRA}]+(?:['-][{_LETRA}]+)*", texto))
