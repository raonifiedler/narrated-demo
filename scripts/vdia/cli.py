"""Linha de comando: `vdia <comando>` (o mesmo que `narrated-demo <comando>`). Ver README.md."""

from __future__ import annotations

import argparse
import io
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from vdia import config, fonetica, imagens, instalar, legenda, midia, projeto, pronuncia, roteiro, unico, voz

_IDS = TypeAdapter(list[str])


def _proj(args: argparse.Namespace) -> Path:
    ref: str | None = args.projeto
    return config.achar_projeto(ref)


def _voz_ativa(ref: str | None) -> config.Voz:
    """Voz do projeto (se houver) ou a padrão do catálogo."""
    try:
        return config.ler_projeto(config.achar_projeto(ref)).voz
    except config.ErroConfig:
        if ref:
            raise
        return config.Voz()


def _amostra_arq() -> Path:
    return config.area() / "vozes" / "amostra-vozes.wav"


# ── comandos ────────────────────────────────────────────────────────────────────────────────
def c_novo(a: argparse.Namespace) -> None:
    p = projeto.novo(a.nome, a.titulo, a.rota, a.formato)
    print(f"projeto criado: {p}\npróximo passo: briefing e roteiro em {p / 'roteiro' / 'ROTEIRO.md'}")


def c_instalar(a: argparse.Namespace) -> None:
    pasta = Path(a.destino) if a.destino else None
    sit = instalar.verificar(a.vozes or None, pasta) if a.verificar else instalar.instalar(a.vozes or None, pasta)
    for s in sit:
        print(f"{s.estado:>20}  {s.arquivo}")
    print(f"pasta dos modelos: {pasta or config.pasta_modelos()}")
    if any(s.estado != "ok" and s.estado != "baixado" for s in sit):
        raise SystemExit(1)


def c_voz_lista(_a: argparse.Namespace) -> None:
    for v in voz.catalogo():
        marca = "instalada" if voz.instalada(v) else "não instalada"
        print(f"{v.id:14} {marca:14} {v.nome}\n{'':29}{v.nota}\n{'':29}Licença: {v.licenca}")
    print("TTS em nuvem: desligado (ver references/seguranca.md).")


def c_voz_amostra(a: argparse.Namespace) -> None:
    destino = _amostra_arq()
    vozes = voz.amostra(destino, a.frase or voz.FRASE_AMOSTRA, a.vozes or None)
    destino.with_suffix(".json").write_text(json.dumps([v.id for v in vozes]), encoding="utf-8")
    print(f"ouça: {destino}\nlista: {destino.with_suffix('.txt')}")
    for n, v in enumerate(vozes, 1):
        print(f"  Voz {n}: {v.id}")
    print("para escolher: vdia voz escolher <número> --projeto <nome>")


def _ritmo(a: argparse.Namespace, atual: config.Voz) -> tuple[str, float]:
    if a.ritmo is None:
        return atual.ritmo, atual.palavras_por_min
    r: str = a.ritmo
    return r, config.ritmo_ppm(r)


def _calibrar_em(pasta: Path, p: config.Projeto) -> None:
    cal = voz.calibrar(p.voz.id, alvo=p.voz.palavras_por_min, escala_inicial=p.voz.escala)
    p.voz.escala = cal.escala
    p.voz.calibrado_em = datetime.now().isoformat(timespec="seconds")
    config.salvar_projeto(pasta, p)
    estado = "convergiu" if cal.convergiu else "NÃO convergiu (usei a melhor rodada)"
    print(f"calibração {estado}: escala {cal.escala} -> {cal.palavras_por_min} pal/min (alvo {cal.alvo:.0f})")
    for e, ppm in cal.rodadas:
        print(f"  escala {e:<7} {ppm} pal/min")


def c_voz_escolher(a: argparse.Namespace) -> None:
    pasta = _proj(a)
    p = config.ler_projeto(pasta)
    escolha: str = a.voz
    if escolha.isdigit():
        lista_arq = _amostra_arq().with_suffix(".json")
        if not lista_arq.exists():
            raise SystemExit("gere antes a amostra: vdia voz amostra")
        ids = _IDS.validate_json(lista_arq.read_bytes())
        n = int(escolha)
        if not 1 <= n <= len(ids):
            raise SystemExit(f"escolha entre 1 e {len(ids)}")
        escolha = ids[n - 1]
    voz.entrada(escolha)
    p.voz.id = escolha
    p.voz.ritmo, p.voz.palavras_por_min = _ritmo(a, p.voz)
    p.voz.calibrado_em = None
    config.salvar_projeto(pasta, p)
    print(f"voz do projeto: {escolha}; ritmo {p.voz.ritmo} ({p.voz.palavras_por_min:.0f} pal/min)")
    if not a.sem_calibrar:
        _calibrar_em(pasta, p)


def c_voz_calibrar(a: argparse.Namespace) -> None:
    pasta = _proj(a)
    p = config.ler_projeto(pasta)
    p.voz.ritmo, p.voz.palavras_por_min = _ritmo(a, p.voz)
    _calibrar_em(pasta, p)


def c_fon_sugerir(a: argparse.Namespace) -> None:
    v = _voz_ativa(a.projeto)
    opcoes = [o.strip() for o in a.opcoes.split(",") if o.strip()] if a.opcoes else None
    wav = fonetica.sugerir(a.palavra, a.frase, opcoes, v.id, v.escala)
    print(f"ouça: {wav}\n{wav.with_suffix('.txt').read_text(encoding='utf-8')}")


def c_fon_escolher(a: argparse.Namespace) -> None:
    e = fonetica.escolher(a.palavra, a.numero, a.variantes_caixa)
    print(f"gravado em {e.dicionario}: " + ", ".join(f"{k} -> {v}" for k, v in e.entradas.items()))


def c_fon_faltantes(a: argparse.Namespace) -> None:
    pasta = _proj(a)
    cenas = roteiro.ler(pasta / "roteiro" / "ROTEIRO.md")
    falta = fonetica.faltantes([c.fala for c in cenas])
    if not falta:
        print("nenhuma palavra suspeita sem entrada no dicionário")
        return
    print("sem entrada no dicionário (ouça e escolha; se a voz já fala certo, escolha a opção 1):")
    for w in falta:
        print(f'  {w}    -> vdia fonetica sugerir "{w}"')


def c_fon_servir(a: argparse.Namespace) -> None:
    v = _voz_ativa(a.projeto)
    srv = fonetica.criar_servidor(v.id, v.escala, a.porta)
    print(f"abra http://127.0.0.1:{a.porta}  (só nesta máquina; Ctrl+C para sair)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.server_close()


def c_roteiro_medir(a: argparse.Namespace) -> None:
    pasta = _proj(a)
    med = roteiro.medir(pasta)
    for m in med:
        print(f"{m.cena.numero}. {m.cena.titulo}: {m.segundos:.1f} s, {m.palavras} palavras")
    print(f"total de fala: {sum(m.segundos for m in med):.1f} s; ouça {pasta / 'roteiro' / 'narracao.wav'}")
    falta = fonetica.faltantes([m.cena.fala for m in med])
    if falta:
        print("palavras sem fonética: " + ", ".join(falta) + "  (vdia fonetica faltantes)")


def c_montar(a: argparse.Namespace) -> None:
    pasta = _proj(a)
    if a.legenda:
        p = config.ler_projeto(pasta)
        p.legenda.modo = a.legenda
        config.salvar_projeto(pasta, p)
    res = projeto.montar(pasta)
    print(
        midia.dump(
            {
                "video": res.video,
                "duracao_s": res.duracao_s,
                "legenda": res.modo_legenda,
                "qa": asdict(res.qa),
                "avisos_roteiro": res.avisos_roteiro,
            }
        )
    )
    for aj in res.ajustes:
        print(
            f"  {aj.clipe}: bruto {aj.bruto_s} s -> {aj.alvo_s} s (x{aj.aceleracao}, congelado {aj.congelado_s} s, "
            f"cortado {aj.cortado_s} s)"
        )
    if not res.zerado:
        raise SystemExit("QA reprovado ou com avisos de roteiro: ajuste o ROTEIRO.md (ou as ações) e monte de novo")
    print("QA zerado: pronto para entrega")


def c_legenda_whisper(a: argparse.Namespace) -> None:
    pasta = _proj(a)
    p = config.ler_projeto(pasta)
    mp4 = pasta / "final" / f"{p.nome}.mp4"
    texto = " ".join(c.fala for c in roteiro.ler(pasta / "roteiro" / "ROTEIRO.md"))
    conf = legenda.transcrever(mp4, texto, a.modelo, a.baixar)
    print(f"transcrição: {conf.srt}\nsimilaridade com o roteiro: {conf.similaridade:.0%} (indício, não prova)")


def c_imagem(a: argparse.Namespace) -> None:
    # o quadro (paisagem ou retrato) vem do projeto: o --projeto dado, ou o da pasta atual se houver
    try:
        config.ler_projeto(config.achar_projeto(a.projeto))
    except config.ErroConfig:
        if a.projeto:
            raise
    fx, fy = (float(x) for x in a.foco.split(","))
    print(imagens.zoom_lento(Path(a.imagem), Path(a.destino), a.duracao, a.zoom, (fx, fy)))


def c_unico(a: argparse.Namespace) -> None:
    if a.modelo:
        print(unico.MODELO.model_dump_json(indent=2))
        return
    res = unico.montar(_proj(a), a.forcar)
    print(midia.dump({"video": str(res.video), "duracao_s": res.duracao_s, "regravadas": res.regravadas, "qa": res.qa}))
    if not res.qa.get("aprovado"):
        raise SystemExit("QA do vídeo único reprovado")


def c_dicionario(_a: argparse.Namespace) -> None:
    print(f"{config.dicionario_path()}\n" + midia.dump(pronuncia.ler()))


# ── parser ──────────────────────────────────────────────────────────────────────────────────
def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="vdia", description="Vídeos de demonstração narrados, tudo local (PT-BR).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("novo", help="cria a estrutura de um projeto de vídeo")
    s.add_argument("nome")
    s.add_argument("--titulo")
    s.add_argument("--rota", choices=["web", "desktop", "offscreen", "imagens"], default="web")
    s.add_argument("--formato", choices=["paisagem", "retrato"], default="paisagem",
                   help="retrato = 1080x1920, celular em pé")
    s.set_defaults(f=c_novo)

    s = sub.add_parser("instalar", help="baixa os modelos de voz (sha256 conferido)")
    s.add_argument("vozes", nargs="*", help="ids do catálogo (vazio = todas)")
    s.add_argument("--verificar", action="store_true", help="só confere o que já existe, sem baixar")
    s.add_argument("--destino", help="pasta (padrão: VDIA_MODELOS ou o cache do usuário)")
    s.set_defaults(f=c_instalar)

    vz = sub.add_parser("voz", help="catálogo, amostra comparativa, escolha e calibração").add_subparsers(
        dest="sub", required=True
    )
    s = vz.add_parser("lista")
    s.set_defaults(f=c_voz_lista)
    s = vz.add_parser("amostra", help="a mesma frase em cada voz instalada, num WAV só")
    s.add_argument("--frase")
    s.add_argument("--vozes", nargs="*")
    s.set_defaults(f=c_voz_amostra)
    ritmo_ajuda = f"preset ({', '.join(f'{k}={v:.0f}' for k, v in config.RITMOS.items())}) ou palavras/min"
    s = vz.add_parser("escolher", help="grava a voz no projeto.json e calibra o ritmo")
    s.add_argument("voz", help="número da amostra ou id do catálogo")
    s.add_argument("--projeto")
    s.add_argument("--ritmo", help=ritmo_ajuda)
    s.add_argument("--sem-calibrar", action="store_true")
    s.set_defaults(f=c_voz_escolher)
    s = vz.add_parser("calibrar", help="mede a escala que dá o ritmo pedido")
    s.add_argument("--projeto")
    s.add_argument("--ritmo", help=ritmo_ajuda)
    s.set_defaults(f=c_voz_calibrar)

    fo = sub.add_parser("fonetica", help="sugerir, escolher, faltantes, servir").add_subparsers(
        dest="sub", required=True
    )
    s = fo.add_parser("sugerir", help="WAV com 'Opção 1… Opção 2…' para uma palavra")
    s.add_argument("palavra")
    s.add_argument("--frase", help="frase com {} (ou com a palavra) para ouvir no contexto")
    s.add_argument("--opcoes", help="grafias separadas por vírgula; sem isso, a heurística sugere")
    s.add_argument("--projeto")
    s.set_defaults(f=c_fon_sugerir)
    s = fo.add_parser("escolher", help="grava a opção no dicionário")
    s.add_argument("palavra")
    s.add_argument("numero", type=int)
    s.add_argument("--variantes-caixa", action="store_true", help="grava também minúscula, Título e MAIÚSCULA")
    s.set_defaults(f=c_fon_escolher)
    s = fo.add_parser("faltantes", help="palavras do roteiro sem entrada no dicionário")
    s.add_argument("--projeto")
    s.set_defaults(f=c_fon_faltantes)
    s = fo.add_parser("servir", help="página local para ouvir com e sem o dicionário")
    s.add_argument("--porta", type=int, default=8765)
    s.add_argument("--projeto")
    s.set_defaults(f=c_fon_servir)
    s = fo.add_parser("dicionario", help="mostra o dicionário em uso")
    s.set_defaults(f=c_dicionario)

    ro = sub.add_parser("roteiro", help="mede as falas do ROTEIRO.md").add_subparsers(dest="sub", required=True)
    s = ro.add_parser("medir")
    s.add_argument("--projeto")
    s.set_defaults(f=c_roteiro_medir)

    s = sub.add_parser("montar", help="monta final/<nome>.mp4 com QA")
    s.add_argument("--projeto")
    s.add_argument("--legenda", choices=["nenhuma", "faixa", "queimada", "arquivo"])
    s.set_defaults(f=c_montar)

    lg = sub.add_parser("legenda", help="conferência pela transcrição local").add_subparsers(dest="sub", required=True)
    s = lg.add_parser("whisper")
    s.add_argument("--projeto")
    s.add_argument("--modelo", default="small")
    s.add_argument("--baixar", action="store_true", help="permite baixar o modelo do Hugging Face (com aprovação)")
    s.set_defaults(f=c_legenda_whisper)

    s = sub.add_parser("imagem", help="clipe de zoom lento sobre um print")
    s.add_argument("imagem")
    s.add_argument("destino")
    s.add_argument("--duracao", type=float, default=6.0)
    s.add_argument("--zoom", type=float, default=1.15)
    s.add_argument("--foco", default="0.5,0.5")
    s.add_argument("--projeto", help="projeto cujo formato (paisagem/retrato) define o quadro")
    s.set_defaults(f=c_imagem)

    s = sub.add_parser("unico", help="vídeo único com aberturas (unico.json no projeto)")
    s.add_argument("--projeto")
    s.add_argument("--forcar", action="store_true", help="regrava todas as aberturas")
    s.add_argument("--modelo", action="store_true", help="imprime um unico.json de exemplo")
    s.set_defaults(f=c_unico)
    return ap


def main(argv: list[str] | None = None) -> None:
    saida = sys.stdout
    if isinstance(saida, io.TextIOWrapper):
        saida.reconfigure(encoding="utf-8")  # acentos no console do Windows
    a = parser().parse_args(argv)
    erros = (
        config.ErroConfig,
        voz.ErroVoz,
        fonetica.ErroFonetica,
        roteiro.ErroRoteiro,
        projeto.ErroProjeto,
        midia.ErroMidia,
        instalar.ErroInstalar,
        legenda.ErroLegenda,
        unico.ErroUnico,
    )
    try:
        a.f(a)
    except erros as e:
        raise SystemExit(f"erro: {e}") from e
