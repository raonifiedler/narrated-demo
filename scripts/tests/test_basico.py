"""Testes rápidos sem síntese: estrutura, dicionário, heurísticas, roteiro, ritmo e trava desktop."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from vdia import config, fonetica, projeto, pronuncia, roteiro
from vdia.gravar_desktop import GestoCancelado, Interferencia, TelaBloqueada, Trava


def test_novo_cria_estrutura(area: Path) -> None:
    p = projeto.novo("app-tarefas", "App de tarefas")
    for sub in config.PASTAS_PROJETO:
        assert (p / sub).is_dir()
    proj = config.ler_projeto(p)
    assert proj.nome == "app-tarefas"
    assert proj.voz.ritmo == "padrao" and proj.voz.palavras_por_min == 145
    assert proj.nuvem.permitida is False
    assert (p / "roteiro" / "ROTEIRO.md").exists()
    assert (p / "scripts" / "gravar.py").exists()
    assert (area / "fonetica" / "dicionario.json").exists()
    # a área nasce com as entradas do dicionário-modelo da skill (sem os comentários)
    assert pronuncia.ler() == pronuncia.ler(config.DICIONARIO_MODELO)
    assert "_leia" not in pronuncia.ler()
    with pytest.raises(projeto.ErroProjeto):
        projeto.novo("app-tarefas")
    with pytest.raises(projeto.ErroProjeto):
        projeto.novo("Nome Ruim")


def test_formato_retrato(area: Path) -> None:
    p = projeto.novo("celular", "Celular", formato="retrato")
    proj = config.ler_projeto(p)
    assert proj.formato == "retrato"
    assert (config.LARG, config.ALT) == (1080, 1920)
    q = projeto.novo("tela", "Tela")
    assert config.ler_projeto(q).formato == "paisagem"
    assert (config.LARG, config.ALT) == (1920, 1080)
    with pytest.raises(config.ErroConfig):
        config.aplicar_formato("quadrado")


def testnome_seguro_sem_colisao() -> None:
    from vdia.fonetica import nome_seguro

    termos = ["%", "&", "#", "\\BEL", "\\BEL+", "\\BEL-", "BEL", "Kubernetes", "dados.txt", "Nº"]
    assert len({nome_seguro(t) for t in termos}) == len(termos)
    assert nome_seguro("Kubernetes") == "Kubernetes"


def test_dicionario_regras() -> None:
    dic = {"Node": "Nôude", "Node.js": "Nôude ponto jota ésse", "web": "uébi", "Web": "Uébi"}
    assert pronuncia.aplicar("Use Node.js e Node.", dic) == "Use Nôude ponto jota ésse e Nôude."
    assert pronuncia.aplicar("a web e a Web, não WEB", dic) == "a uébi e a Uébi, não WEB"
    assert pronuncia.aplicar("webinar e web-app", dic) == "webinar e web-app"  # só palavra inteira
    assert pronuncia.variantes_caixa("Web", "uébi") == {"WEB": "uébi", "Web": "uébi", "web": "uébi"}
    # "_leia" é comentário; o símbolo "_" sozinho é termo de verdade
    assert pronuncia.eh_comentario("_leia") and not pronuncia.eh_comentario("_")
    assert pronuncia.aplicar("Para &, _ e $.", {"_": "sublinhado"}) == "Para &, sublinhado e $."


def test_ritmos() -> None:
    assert config.ritmo_ppm("calmo") == 130
    assert config.ritmo_ppm("padrao") == 145
    assert config.ritmo_ppm("padrão") == 145
    assert config.ritmo_ppm("agil") == 156
    assert config.ritmo_ppm("rapido") == 170
    assert config.ritmo_ppm("150") == 150
    with pytest.raises(config.ErroConfig):
        config.ritmo_ppm("lento-demais")
    with pytest.raises(config.ErroConfig):
        config.ritmo_ppm("400")


def test_candidatas() -> None:
    c = fonetica.candidatas("Kubernetes")
    assert c[0] == "Kubernetes" and len(c) >= 3 and len(set(c)) == len(c)
    s = fonetica.candidatas("API")
    assert "á pê í" in s
    assert fonetica.aportuguesar("web") == "uebi"


def test_faltantes() -> None:
    textos = ["O painel usa Kubernetes e a API REST do GitHub.", "Exporta em CSV, como sempre."]
    falta = fonetica.faltantes(textos, {"CSV": "cê ésse vê"})
    assert "Kubernetes" in falta and "API" in falta and "REST" in falta and "GitHub" in falta
    assert "CSV" not in falta and "painel" not in falta and "Exporta" not in falta
    # pedaço de termo composto que está no dicionário não é faltante
    compostos = {"\\BEL+": "barra bél mais", "SIGN/imagens": "sáin barra imagens"}
    assert fonetica.faltantes(["Incluir é \\BEL+, na pasta SIGN/imagens."], compostos) == []
    assert fonetica.faltantes(["Incluir é \\BEL+."], {}) == ["BEL+"]


def test_roteiro_ler(tmp_path: Path) -> None:
    arq = tmp_path / "ROTEIRO.md"
    arq.write_text(
        "# R\n\n## 1. Abertura\n**Tela:** [lista]\n**Fala:** O app organiza a semana.\n**Prova:** a.tsx\n"
        "**Transição:** fade\n**Tempo:**\n\n## 2. Filtro\n**Tela:** [filtro]\n**Fala:** O filtro deixa só hoje.\n"
        "**Prova:** b.tsx\n**Transição:** smoothleft\n",
        encoding="utf-8",
    )
    cenas = roteiro.ler(arq)
    assert [c.titulo for c in cenas] == ["Abertura", "Filtro"]
    assert cenas[1].transicao == "smoothleft" and cenas[0].prova == "a.tsx"
    arq.write_text("## 1. X\n**Fala:** oi\n**Transição:** girar\n", encoding="utf-8")
    with pytest.raises(roteiro.ErroRoteiro):
        roteiro.ler(arq)


def test_projeto_json_invalido(area: Path) -> None:
    p = projeto.novo("app-x")
    dado = json.loads((p / "projeto.json").read_text(encoding="utf-8"))
    dado["legenda"]["modo"] = "piscando"
    (p / "projeto.json").write_text(json.dumps(dado), encoding="utf-8")
    with pytest.raises(config.ErroConfig):
        config.ler_projeto(p)


@dataclass
class SistemaFalso:
    pos: tuple[int, int] = (100, 100)
    sob: int = 42
    frente: int = 42
    bloqueada: bool = False

    def posicao(self) -> tuple[int, int]:
        return self.pos

    def pid_sob(self, x: int, y: int) -> int:
        return self.sob

    def pid_frente(self) -> int:
        return self.frente

    def tela_bloqueada(self) -> bool:
        return self.bloqueada

    def ocioso_s(self) -> float:
        return 60.0


def test_trava_desktop() -> None:
    s = SistemaFalso()
    t = Trava(42, s, esperado=(100, 100))
    t.conferir()  # tudo certo: não levanta
    s.sob = 7
    with pytest.raises(GestoCancelado):
        t.conferir()  # janela sob o cursor é de outro app
    s.sob, s.frente = 42, 7
    with pytest.raises(GestoCancelado):
        t.conferir()  # outro app na frente
    s.frente, s.pos = 42, (300, 100)
    with pytest.raises(Interferencia):
        t.conferir()  # alguém mexeu no mouse
    s.pos, s.bloqueada = (100, 100), True
    with pytest.raises(TelaBloqueada):
        t.conferir()


def test_cli(area: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from vdia import cli

    cli.main(["novo", "app-cli", "--titulo", "App de tarefas"])
    assert (area / "app-cli" / "projeto.json").exists()
    cli.main(["voz", "lista"])
    saida = capsys.readouterr().out
    assert "piper-faber" in saida
    assert "nuvem: desligado" in saida
    with pytest.raises(SystemExit):
        cli.main(["voz", "calibrar", "--projeto", "app-cli", "--ritmo", "devagarinho"])
