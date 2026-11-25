"""Fonética: sugerir grafias, escolher, listar palavras sem entrada e página local de escuta.

- `sugerir`: um WAV por palavra em <area>/fonetica/sugestoes/<palavra>.wav com "Opção 1. <frase>...",
  mais <palavra>.txt (a lista, para o usuário) e <palavra>.json (para o `escolher`).
- `escolher`: grava a opção no dicionário e move os três arquivos para sugestoes/escolhidas/.
- `servir`: página em http://127.0.0.1:<porta> (só nesta máquina) para ouvir com e sem o dicionário.
"""

from __future__ import annotations

import html
import io
import json
import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

from vdia import config, midia, pronuncia, voz

FRASE_PADRAO = "Na tela aparece {}, logo abaixo do título."

LETRAS = {
    "A": "á",
    "B": "bê",
    "C": "cê",
    "D": "dê",
    "E": "é",
    "F": "éfe",
    "G": "gê",
    "H": "agá",
    "I": "í",
    "J": "jóta",
    "K": "cá",
    "L": "éle",
    "M": "ême",
    "N": "êne",
    "O": "ó",
    "P": "pê",
    "Q": "quê",
    "R": "érre",
    "S": "ésse",
    "T": "tê",
    "U": "ú",
    "V": "vê",
    "W": "dáblio",
    "X": "xís",
    "Y": "ípsilon",
    "Z": "zê",
}
DIGITOS = ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"]
_AGUDO = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}
_CIRC = {"a": "â", "e": "ê", "o": "ô"}
_VOGAIS = "aeiouáéíóúâêôãõ"


class ErroFonetica(RuntimeError):
    """Sugestão ausente, número fora da lista ou frase sem a palavra."""


# ── heurística de candidatas ────────────────────────────────────────────────────────────────
def soletrar(palavra: str) -> str:
    partes: list[str] = []
    for ch in palavra:
        if ch.upper() in LETRAS:
            partes.append(LETRAS[ch.upper()])
        elif ch.isdigit():
            partes.append(DIGITOS[int(ch)])
    return " ".join(partes)


def aportuguesar(palavra: str) -> str:
    """Grafia aportuguesada aproximada (regras simples de inglês para português)."""
    p = palavra.lower()
    trocas = [
        ("tion", "tion"),
        ("ph", "f"),
        ("th", "t"),
        ("sh", "x"),
        ("ck", "k"),
        ("oo", "u"),
        ("ee", "i"),
        ("ea", "i"),
        ("w", "u"),
        ("y", "i"),
    ]
    for a, b in trocas:
        p = p.replace(a, b)
    p = re.sub(r"k(?=[ei])", "qu", p)
    p = p.replace("k", "c")
    p = re.sub(r"(.)\1", r"\1", p)  # letras dobradas
    if p and p[-1] not in _VOGAIS + "lmnrsz":
        p += "i"  # consoante final que o português não fecha: web -> uebi
    return p


def _silabas_vogais(p: str) -> list[int]:
    """Índice da 1ª vogal de cada grupo vocálico (aproxima as sílabas)."""
    idx: list[int] = []
    anterior = False
    for i, ch in enumerate(p):
        e_vogal = ch.lower() in _VOGAIS
        if e_vogal and not anterior:
            idx.append(i)
        anterior = e_vogal
    return idx


def acentuar(p: str, posicao: int, circunflexo: bool = False) -> str:
    """Põe acento na vogal do grupo `posicao` (-1 = última sílaba, -2 = penúltima)."""
    grupos = _silabas_vogais(p)
    if len(grupos) < -posicao:
        return p
    i = grupos[posicao]
    ch = p[i].lower()
    tabela = _CIRC if circunflexo else _AGUDO
    if ch not in tabela:
        return p
    novo = tabela[ch]
    return p[:i] + (novo.upper() if p[i].isupper() else novo) + p[i + 1 :]


def _tem_acento(p: str) -> bool:
    return any(unicodedata.decomposition(c) for c in p if c.isalpha())


def candidatas(palavra: str, limite: int = 7) -> list[str]:
    """Grafias para ouvir. A 1ª é sempre a palavra como está (a voz pode já falar certo)."""
    saida: list[str] = [palavra]
    letras = re.sub(r"[^A-Za-z0-9]", "", palavra)
    if letras.isupper() and 2 <= len(letras) <= 6:  # sigla
        saida.append(soletrar(letras))
        saida.append(letras.capitalize())  # lida como palavra (ex.: "Nasa")
    base = aportuguesar(palavra)
    if palavra[:1].isupper():
        base = base[:1].upper() + base[1:]
    saida.append(base)
    if not _tem_acento(base):
        saida.append(acentuar(base, -2))
        saida.append(acentuar(base, -2, circunflexo=True))
        saida.append(acentuar(base, -1))
    vistos: list[str] = []
    for c in saida:
        if c and c not in vistos:
            vistos.append(c)
    return vistos[:limite]


# ── sugerir / escolher ──────────────────────────────────────────────────────────────────────
class Sugestao(BaseModel):
    palavra: str
    frase: str
    voz: str
    escala: float
    opcoes: list[str]


def _nome_seguro(palavra: str) -> str:
    s = unicodedata.normalize("NFKD", palavra).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "palavra"


def pasta_sugestoes() -> Path:
    return config.pasta_fonetica() / "sugestoes"


def _frase_com(frase: str, palavra: str) -> str:
    if "{}" in frase:
        return frase
    padrao = rf"(?<![\w-]){re.escape(palavra)}(?![\w-])"
    if not re.search(padrao, frase):
        raise ErroFonetica(f"a frase precisa ter '{{}}' ou a palavra '{palavra}'")
    return re.sub(padrao, "{}", frase, count=1)


def sugerir(palavra: str, frase: str | None, opcoes: list[str] | None, voz_id: str, escala: float) -> Path:
    modelo = _frase_com(frase or FRASE_PADRAO, palavra)
    lista = opcoes or candidatas(palavra)
    dic = pronuncia.ler()
    dic.pop(palavra, None)  # a palavra em teste nunca passa pelo dicionário
    pasta = pasta_sugestoes()
    pasta.mkdir(parents=True, exist_ok=True)
    nome = _nome_seguro(palavra)
    destino = pasta / f"{nome}.wav"
    linhas: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        partes: list[Path] = []
        for n, g in enumerate(lista, 1):
            antes, depois = modelo.split("{}", 1)
            falado = f"Opção {n}. " + pronuncia.aplicar(antes, dic) + g + pronuncia.aplicar(depois, dic)
            w = Path(tmp) / f"op{n}.wav"
            voz.sintetizar(voz_id, falado, w, escala)
            partes.append(w)
            linhas.append(f"Opção {n}: {g}    ({modelo.format(g)})")
        midia.concatenar_wav(partes, destino, silencio_s=0.7)
    (pasta / f"{nome}.txt").write_text(
        f"Palavra: {palavra}\nVoz: {voz_id} (escala {escala})\n"
        + "\n".join(linhas)
        + f'\n\nPara fixar: vdia fonetica escolher "{palavra}" <número>\n',
        encoding="utf-8",
    )
    sug = Sugestao(palavra=palavra, frase=modelo, voz=voz_id, escala=escala, opcoes=lista)
    (pasta / f"{nome}.json").write_text(sug.model_dump_json(indent=2), encoding="utf-8")
    return destino


@dataclass
class Escolha:
    palavra: str
    falado: str
    entradas: dict[str, str]
    dicionario: Path


def escolher(palavra: str, numero: int, variantes_caixa: bool = False) -> Escolha:
    pasta = pasta_sugestoes()
    nome = _nome_seguro(palavra)
    arq = pasta / f"{nome}.json"
    if not arq.exists():
        raise ErroFonetica(f"sem sugestão para '{palavra}' em {pasta}; rode antes `vdia fonetica sugerir`")
    sug = Sugestao.model_validate_json(arq.read_text(encoding="utf-8"))
    if not 1 <= numero <= len(sug.opcoes):
        raise ErroFonetica(f"escolha entre 1 e {len(sug.opcoes)} (veio {numero})")
    falado = sug.opcoes[numero - 1]
    entradas = pronuncia.variantes_caixa(sug.palavra, falado) if variantes_caixa else {sug.palavra: falado}
    dic = pronuncia.gravar_entradas(entradas)
    arquivo_ok = pasta / "escolhidas"
    arquivo_ok.mkdir(parents=True, exist_ok=True)
    for ext in (".wav", ".txt", ".json"):
        origem = pasta / f"{nome}{ext}"
        if origem.exists():
            shutil.move(str(origem), str(arquivo_ok / origem.name))
    return Escolha(sug.palavra, falado, entradas, dic)


# ── palavras do roteiro sem entrada ─────────────────────────────────────────────────────────
_ESTRANGEIRO = re.compile(r"[kwy]|th|sh|ph|ck|oo|ee|[bcdfgkptv]$", re.I)
_TOKEN = re.compile(r"[A-Za-zÀ-ÿ0-9][\wÀ-ÿ.+#'-]*[\wÀ-ÿ+#]|[A-Za-zÀ-ÿ]")
COMUNS = {"OK", "e-mail", "app", "online", "site", "login", "link", "mouse", "software", "web"}


def faltantes(textos: list[str], dic: dict[str, str] | None = None) -> list[str]:
    """Siglas (2+ maiúsculas), CamelCase, números com letras e nomes de grafia estrangeira sem entrada."""
    dic = dic if dic is not None else pronuncia.ler()
    achadas: list[str] = []
    for t in textos:
        for m in _TOKEN.finditer(t):
            w = m.group(0).rstrip(".")
            if w in dic or w in achadas or w.lower() in COMUNS:
                continue
            letras = re.sub(r"[^A-Za-z]", "", w)
            sigla = sum(c.isupper() for c in w) >= 2
            camel = bool(re.search(r"[a-z][A-Z]", w))
            misto = bool(re.search(r"\d", w)) and bool(letras)
            estrangeiro = w[:1].isupper() and bool(_ESTRANGEIRO.search(w)) and not _tem_acento(w)
            if sigla or camel or misto or estrangeiro or "." in w:
                achadas.append(w)
    return achadas


# ── página local ────────────────────────────────────────────────────────────────────────────
PAGINA = """<!doctype html><meta charset="utf-8"><title>Fonética · vdia</title>
<style>body{font:16px system-ui;max-width:780px;margin:2em auto}textarea{width:100%;height:6em;font-size:18px}
button{font-size:18px;padding:.4em 1.2em;margin:.5em .5em 0 0}pre{background:#f3f3f3;padding:1em}</style>
<h2>Teste de fonética (voz {voz}, local)</h2>
<p>Digite o texto como está no roteiro e ouça sem e com o dicionário. Só escuta em 127.0.0.1.</p>
<textarea id=t>O Kubernetes distribui os contêineres entre as máquinas.</textarea><br>
<button onclick="tocar('')">▶ Sem dicionário</button><button onclick="tocar('1')">▶ Com dicionário</button>
<audio id=a controls></audio><p id=f></p>
<h3>Dicionário em uso</h3><pre>{dic}</pre>
<script>async function tocar(d){const t=document.getElementById('t').value;const q=new URLSearchParams({t,d});
document.getElementById('a').src='/falar?'+q;document.getElementById('a').play();
const r=await fetch('/texto?'+q);document.getElementById('f').textContent='Falado: '+await r.text()}</script>"""


def _wav_bytes(voz_id: str, escala: float, texto: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp) / "f.wav"
        voz.sintetizar(voz_id, texto or "vazio", w, escala)
        return w.read_bytes()


def criar_servidor(voz_id: str, escala: float, porta: int = 8765) -> ThreadingHTTPServer:
    class Pagina(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            u = urlparse(self.path)
            q = parse_qs(u.query)
            texto = q.get("t", [""])[0][:2000]
            com_dic = bool(q.get("d", [""])[0])
            falado = pronuncia.falado(texto) if com_dic else texto
            if u.path == "/falar":
                corpo, tipo = _wav_bytes(voz_id, escala, falado), "audio/wav"
            elif u.path == "/texto":
                corpo, tipo = falado.encode("utf-8"), "text/plain; charset=utf-8"
            else:
                dic = html.escape(json.dumps(pronuncia.ler(), ensure_ascii=False, indent=1))
                corpo = PAGINA.replace("{dic}", dic).replace("{voz}", html.escape(voz_id)).encode("utf-8")
                tipo = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(io.BytesIO(corpo).getvalue())

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer(("127.0.0.1", porta), Pagina)
