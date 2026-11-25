"""`vdia novo <nome>` e `vdia montar`: estrutura padronizada do projeto e montagem a partir do roteiro.

<area>/<nome>/
  projeto.json   voz, ritmo, legenda, montagem, rota de gravação, nuvem (desligada)
  roteiro/       ROTEIRO.md (fonte do texto) e narracao.wav
  scripts/       gravar.py (modelo da rota web) e o que mais o projeto precisar
  material/      dados fictícios, prints, imagens
  cenas/         clipes brutos (bruto<i>.webm|mp4) e acoes.jsonl
  montagem/      intermediários e metricas.json
  final/         <nome>.mp4 (+ <nome>.srt conforme o modo de legenda)
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from pydantic import TypeAdapter

from vdia import config, montagem, roteiro

_RECORTES = TypeAdapter(dict[str, tuple[int, int, int]])


class ErroProjeto(RuntimeError):
    """Nome inválido, projeto existente ou clipe faltando."""


def novo(nome: str, titulo: str | None = None, rota: str = "web") -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", nome):
        raise ErroProjeto("nome: minúsculas, números e hífen (ex.: app-tarefas)")
    pasta = config.area() / nome
    if (pasta / "projeto.json").exists():
        raise ErroProjeto(f"já existe: {pasta}")
    for sub in config.PASTAS_PROJETO:
        (pasta / sub).mkdir(parents=True, exist_ok=True)
    t = titulo or nome.replace("-", " ").capitalize()
    proj = config.Projeto(nome=nome, titulo=t, gravacao=config.Gravacao.model_validate({"rota": rota}))
    config.salvar_projeto(pasta, proj)
    (pasta / "roteiro" / "ROTEIRO.md").write_text(roteiro.MODELO.format(titulo=t), encoding="utf-8")
    shutil.copyfile(config.ASSETS / "modelo_gravar_web.py", pasta / "scripts" / "gravar.py")
    (pasta / "material" / "LEIA.txt").write_text(
        "Só dados fictícios aqui (nomes, números e documentos inventados). Nada de dado real.\n", encoding="utf-8"
    )
    config.dicionario_path()  # garante a fonética da área de trabalho
    return pasta


def brutos_do_projeto(pasta: Path, n: int) -> list[Path]:
    saida: list[Path] = []
    faltam: list[str] = []
    for i in range(n):
        achados = [pasta / "cenas" / f"bruto{i}{ext}" for ext in (".webm", ".mp4", ".mkv")]
        existe = next((p for p in achados if p.exists()), None)
        if existe is None:
            faltam.append(f"cenas/bruto{i}.webm|mp4")
        else:
            saida.append(existe)
    if faltam:
        raise ErroProjeto(f"faltam clipes: {', '.join(faltam)}")
    return saida


def montar(pasta: Path) -> montagem.Resultado:
    """Monta final/<nome>.mp4 a partir do ROTEIRO.md e de cenas/bruto<i>.*; recortes opcionais em
    montagem/recortes.json: {"2": [x, y, largura]} (número da cena, a partir de 1)."""
    proj = config.ler_projeto(pasta)
    cenas = roteiro.ler(pasta / "roteiro" / "ROTEIRO.md")
    arq_rec = pasta / "montagem" / "recortes.json"
    recortes = _RECORTES.validate_json(arq_rec.read_bytes()) if arq_rec.exists() else {}
    clipes = [montagem.Clipe(c.titulo, c.fala, c.transicao, recortes.get(str(c.numero))) for c in cenas]
    brutos = brutos_do_projeto(pasta, len(cenas))
    res = montagem.montar(clipes, brutos, proj, pasta / "montagem", nome=proj.nome)
    montagem.salvar(res, pasta / "montagem")
    final = pasta / "final"
    final.mkdir(exist_ok=True)
    shutil.copyfile(res.video, final / f"{proj.nome}.mp4")
    if res.legenda_srt:
        shutil.copyfile(res.legenda_srt, final / f"{proj.nome}.srt")
    else:
        (final / f"{proj.nome}.srt").unlink(missing_ok=True)
    return res
