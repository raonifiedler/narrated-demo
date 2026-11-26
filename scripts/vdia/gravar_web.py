"""Rota web: Playwright `page.screencast` (um clipe por cena) + `show_actions` (cursor desenhado e animado).

Nada toca no mouse do usuário: o navegador roda headless e o cursor é desenhado pelo Playwright.

    from vdia import gravar_web as gw
    cenas = [gw.CenaWeb("Abertura", acoes=percorrer_lista, preparar=abrir_lista), ...]
    with gw.navegador(zoom_css=1.25) as pg:
        entrar(pg)                                   # login etc.: fora da gravação
        brutos = gw.gravar(pg, cenas, pasta / "cenas")

- `preparar(pg)` roda ANTES de a gravação começar (login, menus, filtros): o caminho não aparece.
- `acoes(pg, relogio)` é o que o espectador vê. Use `ir`, `ir_a`, `clicar`, `digitar` (trajetória suave e
  pausa de ~0,6 s antes do clique, para dar tempo de ler).
- `zoom_css` amplia a página como o zoom do navegador (o app não muda): letra legível no 1080p.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Locator, Page, sync_playwright

from vdia import config


@dataclass
class Relogio:
    t0: float = field(default_factory=time.perf_counter)
    log: list[dict[str, object]] = field(default_factory=lambda: [])

    def marca(self, acao: str, **dados: object) -> None:
        self.log.append({"t": round(time.perf_counter() - self.t0, 3), "acao": acao} | dados)


@dataclass
class CenaWeb:
    nome: str
    acoes: Callable[[Page, Relogio], None]
    preparar: Callable[[Page], None] | None = None


def zoom_script(zoom: float) -> str:
    return (
        "document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
        f"s.textContent = 'html{{zoom:{zoom}}}'; document.head.appendChild(s); }});"
    )


@contextmanager
def navegador(zoom_css: float = 1.0, largura: int | None = None, altura: int | None = None) -> Generator[Page]:
    """Sem largura/altura, usa o quadro do formato do projeto (config.LARG x config.ALT, lido na hora)."""
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        try:
            ctx = nav.new_context(viewport={"width": largura or config.LARG, "height": altura or config.ALT})
            if zoom_css != 1.0:
                ctx.add_init_script(zoom_script(zoom_css))
            yield ctx.new_page()
        finally:
            nav.close()


# ── gestos ──────────────────────────────────────────────────────────────────────────────────
def centro(loc: Locator) -> tuple[float, float]:
    bb = loc.first.bounding_box()
    if bb is None:
        raise RuntimeError(f"elemento sem caixa (invisível?): {loc}")
    return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2


def ir(pg: Page, x: float, y: float, passos: int = 8, pausa_ms: int = 0) -> None:
    pg.mouse.move(x, y, steps=passos)
    if pausa_ms:
        pg.wait_for_timeout(pausa_ms)


def ir_a(pg: Page, loc: Locator, passos: int = 8, pausa_ms: int = 0) -> None:
    x, y = centro(loc)
    ir(pg, x, y, passos, pausa_ms)


def clicar(pg: Page, r: Relogio, loc: Locator, nome: str, pausa_ms: int = 600) -> None:
    x, y = centro(loc)
    ir(pg, x, y)
    pg.wait_for_timeout(pausa_ms)
    r.marca("clique", alvo=nome, x=round(x), y=round(y))
    loc.first.click()


def digitar(pg: Page, r: Relogio, texto: str, atraso_ms: int = 120) -> None:
    r.marca("digita", texto=texto)
    pg.keyboard.type(texto, delay=atraso_ms)


# ── gravação ────────────────────────────────────────────────────────────────────────────────
def gravar(pg: Page, cenas: list[CenaWeb], pasta: Path) -> list[Path]:
    """Grava bruto<i>.webm por cena e acoes.jsonl (carimbos de cada gesto)."""
    pasta.mkdir(parents=True, exist_ok=True)
    brutos: list[Path] = []
    log: list[dict[str, object]] = []
    for i, c in enumerate(cenas):
        if c.preparar:
            c.preparar(pg)
        p = pasta / f"bruto{i}.webm"
        rel = Relogio()
        with (
            pg.screencast.start(path=str(p), fps=config.FPS, size={"width": config.LARG, "height": config.ALT}),
            pg.screencast.show_actions(cursor="pointer", duration=700, style={"title": "display:none"}),
        ):
            pg.wait_for_timeout(300)
            c.acoes(pg, rel)
            pg.wait_for_timeout(400)
        log.extend({"clipe": c.nome} | x for x in rel.log)
        brutos.append(p)
    (pasta / "acoes.jsonl").write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in log), encoding="utf-8")
    return brutos
