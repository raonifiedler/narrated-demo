"""Gravação web deste projeto (modelo criado por `vdia novo`; adapte as funções).

Um clipe por cena do roteiro/ROTEIRO.md, na mesma ordem. `preparar` roda FORA da gravação (login, menus,
filtros); `acoes` é o que aparece. Saída: cenas/bruto<i>.webm + cenas/acoes.jsonl.

Rodar: uv run --project <skill>/scripts python scripts/gravar.py
Antes: o sistema precisa estar no ar (numa CÓPIA do repositório, com dados fictícios). Avise o usuário
antes de subir Docker ou serviços.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

from vdia import config, roteiro
from vdia import gravar_web as gw

PROJETO = Path(__file__).resolve().parents[1]


def preparar_abertura(pg: Page) -> None:
    proj = config.ler_projeto(PROJETO)
    pg.goto(proj.gravacao.url)
    pg.wait_for_load_state("networkidle")
    pg.mouse.move(1500, 700)


def acoes_abertura(pg: Page, r: gw.Relogio) -> None:
    r.marca("percorre", alvo="tela inicial")
    for x, y in ((300, 200), (900, 320), (1400, 500), (800, 700)):
        gw.ir(pg, x, y, passos=10, pausa_ms=400)


def acoes_funcionalidade(pg: Page, r: gw.Relogio) -> None:
    r.marca("percorre", alvo="funcionalidade")
    gw.ir(pg, 960, 540, passos=10, pausa_ms=1500)


# uma entrada por cena do ROTEIRO.md, na ordem: (acoes, preparar)
ACOES = [
    (acoes_abertura, preparar_abertura),
    (acoes_funcionalidade, None),
]


def main() -> None:
    proj = config.ler_projeto(PROJETO)
    cenas = roteiro.ler(PROJETO / "roteiro" / "ROTEIRO.md")
    if len(cenas) != len(ACOES):
        raise SystemExit(f"o roteiro tem {len(cenas)} cenas e ACOES tem {len(ACOES)}: ajuste scripts/gravar.py")
    web = [gw.CenaWeb(c.titulo, a, p) for c, (a, p) in zip(cenas, ACOES, strict=True)]
    with gw.navegador(zoom_css=proj.gravacao.zoom_css) as pg:
        brutos = gw.gravar(pg, web, PROJETO / "cenas")
    print("\n".join(str(b) for b in brutos))


if __name__ == "__main__":
    main()
