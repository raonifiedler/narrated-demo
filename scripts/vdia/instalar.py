"""Baixa os modelos de voz do catálogo (URLs oficiais) para VDIA_MODELOS, conferindo o sha256.

Nada é copiado para dentro da skill. Arquivo que já existe com o sha256 certo não é baixado de novo.
Um sha256 diferente é erro (o arquivo baixado é apagado): confira a URL no catálogo antes de seguir.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from vdia import config, voz


class ErroInstalar(RuntimeError):
    """Download falhou ou o checksum não confere."""


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


@dataclass
class Situacao:
    arquivo: str
    estado: str  # "ok" | "falta" | "checksum diferente" | "baixado"


def _arquivos(ids: list[str] | None) -> list[voz.Arquivo]:
    vozes = [voz.entrada(i) for i in ids] if ids else voz.catalogo()
    vistos: dict[str, voz.Arquivo] = {}
    for v in vozes:
        for a in v.arquivos:
            vistos.setdefault(a.nome, a)
    return list(vistos.values())


def verificar(ids: list[str] | None = None, pasta: Path | None = None) -> list[Situacao]:
    destino = pasta or config.pasta_modelos()
    saida: list[Situacao] = []
    for a in _arquivos(ids):
        p = destino / a.nome
        if not p.exists():
            saida.append(Situacao(a.nome, "falta"))
        else:
            saida.append(Situacao(a.nome, "ok" if sha256(p) == a.sha256 else "checksum diferente"))
    return saida


def instalar(ids: list[str] | None = None, pasta: Path | None = None) -> list[Situacao]:
    destino = pasta or config.pasta_modelos()
    destino.mkdir(parents=True, exist_ok=True)
    saida: list[Situacao] = []
    for a in _arquivos(ids):
        p = destino / a.nome
        if p.exists() and sha256(p) == a.sha256:
            saida.append(Situacao(a.nome, "ok"))
            continue
        if not a.url.startswith("https://"):
            raise ErroInstalar(f"{a.nome}: só baixo por https ({a.url})")
        tmp = p.with_suffix(p.suffix + ".baixando")
        print(f"baixando {a.nome} de {a.url} ...", flush=True)
        try:
            with urllib.request.urlopen(a.url, timeout=60) as r, tmp.open("wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise ErroInstalar(f"{a.nome}: download falhou ({e})") from e
        obtido = sha256(tmp)
        if obtido != a.sha256:
            tmp.unlink()
            raise ErroInstalar(f"{a.nome}: sha256 {obtido} difere do catálogo ({a.sha256}); nada foi instalado")
        tmp.replace(p)
        saida.append(Situacao(a.nome, "baixado"))
    return saida
