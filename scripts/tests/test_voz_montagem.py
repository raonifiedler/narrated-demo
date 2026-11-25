"""Testes com síntese e ffmpeg (segundos a minutos). Precisam de VDIA_MODELOS e do ffmpeg no PATH."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path

import pytest
import soundfile as sf

from vdia import config, fonetica, instalar, midia, projeto, pronuncia, roteiro, unico, voz

pytestmark = pytest.mark.lento


def test_instalar_verificar(com_vozes: list[voz.EntradaVoz]) -> None:
    sit = instalar.verificar([v.id for v in com_vozes])
    assert sit
    assert all(s.estado == "ok" for s in sit), sit


def test_sugerir_e_escolher(area: Path, com_vozes: list[voz.EntradaVoz]) -> None:
    wav = fonetica.sugerir("Kubernetes", "O {} distribui os contêineres.", None, "piper-faber", 1.3)
    assert wav.exists()
    assert voz.duracao_wav(wav) > 3
    txt = wav.with_suffix(".txt").read_text(encoding="utf-8")
    assert "Opção 1: Kubernetes" in txt
    assert "Opção 2:" in txt
    opcoes = fonetica.Sugestao.model_validate_json(wav.with_suffix(".json").read_text(encoding="utf-8")).opcoes
    e = fonetica.escolher("Kubernetes", 2)
    assert e.entradas == {"Kubernetes": opcoes[1]}
    assert pronuncia.ler()["Kubernetes"] == opcoes[1]
    assert not wav.exists()
    assert (wav.parent / "escolhidas" / wav.name).exists()
    with pytest.raises(fonetica.ErroFonetica):
        fonetica.escolher("Kubernetes", 2)  # a sugestão já foi arquivada


def test_opcoes_do_usuario_e_variantes(area: Path, com_vozes: list[voz.EntradaVoz]) -> None:
    fonetica.sugerir("web", "É uma aplicação web.", ["web", "uébi"], "piper-faber", 1.3)
    e = fonetica.escolher("web", 2, variantes_caixa=True)
    assert e.entradas == {"WEB": "uébi", "Web": "uébi", "web": "uébi"}
    with pytest.raises(fonetica.ErroFonetica):
        fonetica.sugerir("web", "Frase sem a palavra.", None, "piper-faber", 1.3)


def test_sintese_aplica_dicionario(
    area: Path, com_vozes: list[voz.EntradaVoz], monkeypatch: pytest.MonkeyPatch
) -> None:
    pronuncia.gravar_entradas({"SQL": "ésse quê éle"})
    recebido: list[str] = []
    original = voz.sintetizar

    def espiao(voz_id: str, texto: str, destino: Path, escala: float) -> float:
        recebido.append(texto)
        return original(voz_id, texto, destino, escala)

    monkeypatch.setattr(voz, "sintetizar", espiao)
    d = voz.fala("piper-faber", 1.3, "O banco fala SQL.", area / "f.wav")
    assert recebido == ["O banco fala ésse quê éle."]
    assert d > 0.5
    voz.fala("piper-faber", 1.3, "O banco fala SQL.", area / "g.wav", com_dicionario=False)
    assert recebido[-1] == "O banco fala SQL."


@pytest.mark.parametrize("ritmo", ["padrao", "agil"])
def test_calibracao_converge(com_vozes: list[voz.EntradaVoz], ritmo: str) -> None:
    alvo = config.ritmo_ppm(ritmo)
    cal = voz.calibrar("piper-faber", alvo=alvo)
    assert cal.convergiu, cal
    assert abs(cal.palavras_por_min - alvo) / alvo <= 0.02
    assert len(cal.rodadas) <= 8


def test_amostra_de_vozes(area: Path, com_vozes: list[voz.EntradaVoz]) -> None:
    destino = area / "vozes" / "amostra.wav"
    vozes = voz.amostra(destino)
    assert [v.id for v in vozes] == [v.id for v in com_vozes]
    i = sf.info(str(destino))
    assert i.samplerate == 48000
    assert i.frames / i.samplerate > 4 * len(vozes)
    linhas = destino.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == len(vozes)
    assert linhas[0].startswith("Voz 1:")


def test_pagina_local(area: Path, com_vozes: list[voz.EntradaVoz]) -> None:
    pronuncia.gravar_entradas({"Kubernetes": "Cubernêtis"})
    srv = fonetica.criar_servidor("piper-faber", 1.3, porta=0)
    porta = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{porta}"
        with urllib.request.urlopen(f"{base}/texto?t=O%20Kubernetes&d=1") as r:
            assert r.read().decode() == "O Cubernêtis"
        with urllib.request.urlopen(f"{base}/texto?t=O%20Kubernetes&d=") as r:
            assert r.read().decode() == "O Kubernetes"
        with urllib.request.urlopen(f"{base}/falar?t=Ol%C3%A1&d=1") as r:
            assert r.read()[:4] == b"RIFF"
        with urllib.request.urlopen(base) as r:
            assert "Cubernêtis" in r.read().decode()
    finally:
        srv.shutdown()
        srv.server_close()


ROTEIRO = """# Roteiro

## 1. Abertura
**Tela:** [lista de tarefas]
**Fala:** O app de tarefas organiza a semana num só lugar, com prazos e responsáveis.
**Prova:** sintético
**Transição:** fade
**Tempo:**

## 2. Filtro
**Tela:** [filtro de hoje]
**Fala:** O filtro deixa só o que vence hoje, e o botão de concluir atualiza o progresso.
**Prova:** sintético
**Transição:** smoothleft
**Tempo:**
"""


def _bruto(destino: Path, dur: float) -> None:
    midia.rodar(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=1920x1080:rate=30:duration={dur:.2f}",
            "-pix_fmt",
            "yuv420p",
            str(destino),
        ]
    )


def _projeto_sintetico(nome: str, modo: config.ModoLegenda) -> Path:
    p = projeto.novo(nome, "App de tarefas")
    proj = config.ler_projeto(p)
    proj.legenda.modo = modo
    proj.voz.escala = 1.3
    config.salvar_projeto(p, proj)
    (p / "roteiro" / "ROTEIRO.md").write_text(ROTEIRO, encoding="utf-8")
    med = roteiro.medir(p)  # o bruto sintético fica ~10% mais longo que o segmento da fala
    for i, m in enumerate(med):
        _bruto(p / "cenas" / f"bruto{i}.mp4", (m.segundos + proj.montagem.respiro_s + 0.5) * 1.1)
    return p


@pytest.mark.parametrize("modo", ["faixa", "queimada"])
def test_montagem_minima(area: Path, com_vozes: list[voz.EntradaVoz], modo: config.ModoLegenda) -> None:
    p = _projeto_sintetico(f"teste-{modo}", modo)
    assert "**Tempo:** " in (p / "roteiro" / "ROTEIRO.md").read_text(encoding="utf-8")
    assert (p / "roteiro" / "narracao.wav").exists()
    res = projeto.montar(p)
    assert res.qa.especificacao_ok, res.qa
    assert res.qa.aprovado, res.qa
    assert res.avisos_roteiro == [], res.avisos_roteiro
    final = p / "final" / f"teste-{modo}.mp4"
    tipos = {f.codec_type for f in midia.fluxos(final)}
    assert ("subtitle" in tipos) == (modo == "faixa")
    srt = midia.ler_srt(p / "final" / f"teste-{modo}.srt")
    assert srt[0][2].startswith("O app de tarefas")  # legenda = texto escrito
    metricas = json.loads((p / "montagem" / "metricas.json").read_text(encoding="utf-8"))
    assert metricas["qa"]["aprovado"] is True


def test_aviso_de_imagem_parada(area: Path, com_vozes: list[voz.EntradaVoz]) -> None:
    p = _projeto_sintetico("teste-aviso", "arquivo")
    _bruto(p / "cenas" / "bruto1.mp4", 1.0)
    res = projeto.montar(p)
    assert any("imagem parada" in a and "palavras" in a for a in res.avisos_roteiro), res.avisos_roteiro
    assert res.qa.aprovado  # congelar não cria silêncio: a fala continua
    assert not res.zerado


def test_video_unico(area: Path, com_vozes: list[voz.EntradaVoz]) -> None:
    partes = [_projeto_sintetico(n, "faixa") for n in ("parte-a", "parte-b")]
    for p in partes:
        projeto.montar(p)
    u = projeto.novo("apresentacao", "Apresentação")
    cfg = unico.MODELO.model_copy(deep=True)
    cfg.partes = [
        unico.Parte(
            arquivo=f"../{p.name}/final/{p.name}.mp4", nome=f"Parte {k}", titulo="Exemplo", fala=f"Parte {k}.", visual=v
        )
        for k, (p, v) in enumerate(zip(partes, unico.VISUAIS[::3], strict=True), 1)
    ]
    (u / "unico.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
    res = unico.montar(u)
    assert res.qa["aprovado"], res.qa
    assert len(res.regravadas) == 4
    srt = midia.ler_srt(u / "final" / "apresentacao.srt")
    assert any(t == "Parte 1" for _, _, t in srt)
    assert any(t.startswith("O app de tarefas") for _, _, t in srt)
    res2 = unico.montar(u)  # nada mudou: nenhuma abertura é regravada
    assert res2.regravadas == []


def test_gravar_web_e_imagem(tmp_path: Path) -> None:
    from playwright.sync_api import Page

    from vdia import gravar_web as gw
    from vdia import imagens

    pagina = (Path(__file__).resolve().parents[1] / "exemplos" / "app_tarefas.html").as_uri()

    def preparar(pg: Page) -> None:
        pg.goto(pagina)

    def acoes(pg: Page, r: gw.Relogio) -> None:
        gw.clicar(pg, r, pg.locator("#nova"), "campo")
        gw.digitar(pg, r, "Preparar a apresentação", atraso_ms=30)
        gw.clicar(pg, r, pg.locator("#adicionar"), "adicionar")
        gw.clicar(pg, r, pg.locator("li").first, "concluir")

    with gw.navegador(zoom_css=1.5) as pg:
        brutos = gw.gravar(pg, [gw.CenaWeb("Adicionar", acoes, preparar)], tmp_path / "cenas")
        assert pg.locator("li").count() == 4
        pg.screenshot(path=str(tmp_path / "print.png"))
    assert midia.duracao(brutos[0]) > 1.5
    assert (tmp_path / "cenas" / "acoes.jsonl").read_text(encoding="utf-8").count("clique") == 3
    clipe = imagens.zoom_lento(tmp_path / "print.png", tmp_path / "zoom.mp4", duracao_s=2.0)
    assert midia.quadros(clipe) == 60
