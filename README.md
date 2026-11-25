# narrated-demo

Skill do Claude Code que produz **vídeos de demonstração de software narrados em PT-BR**. A IA escreve o roteiro,
opera o software com cursor visível, grava a tela, gera a narração com TTS **local** e monta o vídeo, com QA
automático de pausas. Nada sai da máquina sem aprovação.

> Rascunho para revisão. A skill é genérica: os exemplos usam um "app de tarefas" fictício.

## O que faz

| Etapa | Como |
| --- | --- |
| Roteiro | `roteiro/ROTEIRO.md`: por cena, `[tela]`, fala, prova no código, transição e tempo medido |
| Fonética | dicionário persistente (escrito → falado), sugestões ouvidas e escolhidas pelo usuário |
| Gravação | web (Playwright), desktop offscreen (motor no app Qt), desktop com mouse real (com trava), imagens |
| Voz | Piper (faber, cadu) ou Kokoro (pm_alex, pf_dora), ritmo calibrado em palavras/min |
| Montagem | a fala manda no tempo; acelera até 2×, desacelera até 1,4× e congela; xfade; legenda opcional |
| QA | `silencedetect` (pausa máxima) e avisos de roteiro em palavras, até zerar |
| Vídeo único | cartela, uma abertura animada por parte (HTML local), transições variadas, fecho |

## Requisitos

- Windows 10/11 ou Linux (a rota desktop com mouse real é só Windows; as outras rodam nos dois).
- Python 3.12 ou mais novo e [uv](https://docs.astral.sh/uv/).
- ffmpeg e ffprobe no PATH, com `libass` (para a legenda queimada) e `libx264`.
- Chromium do Playwright: `uv run --project scripts playwright install chromium`.
- Node 22+: só se for usar o HyperFrames (opcional).
- Cerca de 500 MB para os modelos de voz (Kokoro é o maior).

## Instalação

```bash
cd <pasta da skill>/scripts
uv sync                       # base: Piper, Kokoro, Playwright
uv sync --extra whisper       # opcional: conferência da legenda por transcrição local
uv sync --extra desktop       # opcional: rota desktop com mouse real (Windows)
uv sync --extra offscreen     # opcional: exemplo da rota offscreen (PySide6)
uv run playwright install chromium
uv run vdia instalar          # baixa as vozes do catálogo, com sha256 conferido
```

Os modelos vão para `VDIA_MODELOS` (se definido) ou para `%LOCALAPPDATA%\narrated-demo\modelos`
(`~/.cache/narrated-demo/modelos` no Linux). Já tem os modelos baixados? Aponte `VDIA_MODELOS` para a pasta e
confira com `vdia instalar --verificar`.

Para instalar como skill do Claude Code, copie a pasta para `~/.claude/skills/narrated-demo/`.

## Início rápido (5 passos)

Defina um atalho (PowerShell: `function vdia { uv run --project "<skill>\scripts" vdia @args }`):

```bash
vdia novo app-tarefas --titulo "App de tarefas"          # 1. estrutura do projeto
# 2. escreva app-tarefas/roteiro/ROTEIRO.md e meça:
vdia roteiro medir --projeto app-tarefas
vdia voz amostra && vdia voz escolher 1 --projeto app-tarefas --ritmo padrao   # 3. voz e ritmo
uv run --project "<skill>/scripts" python app-tarefas/scripts/gravar.py      # 4. grava os clipes
vdia montar --projeto app-tarefas --legenda faixa                            # 5. monta + QA
```

## Comandos

| Comando | Exemplo | Faz |
| --- | --- | --- |
| `novo <nome>` | `vdia novo app-tarefas --titulo "App de tarefas" --rota web` | cria `projeto.json`, `roteiro/`, `scripts/`, `material/`, `cenas/`, `montagem/`, `final/` |
| `instalar [ids]` | `vdia instalar piper-faber` / `vdia instalar --verificar` | baixa os modelos (https, sha256) ou só confere |
| `voz lista` | `vdia voz lista` | catálogo com licença e nota |
| `voz amostra` | `vdia voz amostra --frase "Olá, este é o app."` | `vozes/amostra-vozes.wav`: "Voz 1… Voz 2…" |
| `voz escolher` | `vdia voz escolher 2 --projeto app-tarefas --ritmo calmo` | grava a voz e calibra o ritmo |
| `voz calibrar` | `vdia voz calibrar --projeto app-tarefas --ritmo 150` | recalibra (após mudar voz ou ritmo) |
| `fonetica faltantes` | `vdia fonetica faltantes --projeto app-tarefas` | siglas e nomes estrangeiros sem entrada |
| `fonetica sugerir` | `vdia fonetica sugerir Kubernetes --frase "O {} sobe os contêineres."` | WAV com as opções numeradas + `.txt` |
| `fonetica sugerir` (opções suas) | `vdia fonetica sugerir SQL --opcoes "SQL,ésse quê éle,síquel"` | idem, com as suas grafias |
| `fonetica escolher` | `vdia fonetica escolher Kubernetes 3 --variantes-caixa` | grava no dicionário e arquiva a sugestão |
| `fonetica servir` | `vdia fonetica servir --porta 8765` | página em 127.0.0.1 para ouvir com e sem o dicionário |
| `fonetica dicionario` | `vdia fonetica dicionario` | mostra o dicionário em uso |
| `roteiro medir` | `vdia roteiro medir --projeto app-tarefas` | tempo de cada fala, `narracao.wav`, palavras sem fonética |
| `montar` | `vdia montar --projeto app-tarefas --legenda queimada` | `final/<nome>.mp4` + QA; sai com erro se não zerar |
| `legenda whisper` | `vdia legenda whisper --projeto app-tarefas` | transcreve o final (local) e compara com o roteiro |
| `imagem` | `vdia imagem tela.png cenas/bruto3.mp4 --duracao 6 --zoom 1.2 --foco 0.3,0.4` | clipe de zoom lento |
| `unico` | `vdia unico --modelo > apresentacao/unico.json` e `vdia unico --projeto apresentacao` | vídeo único com aberturas |

`--projeto` aceita o nome (na área de trabalho) ou um caminho; sem ele, vale a pasta atual.

## Como escolher a voz

1. `vdia voz amostra`: ouça o WAV; a mesma frase em cada voz instalada, anunciada como "Voz 1", "Voz 2"...
2. `vdia voz escolher <número> --ritmo <preset>`: grava a voz e o ritmo em `projeto.json` e calibra.

**Ritmo** (palavras por minuto do texto escrito):

| Preset | pal/min | Quando |
| --- | --- | --- |
| `calmo` | 130 | público novo no assunto, telas densas |
| **`padrao`** | **145** | o padrão: faixa usual de narração institucional e e-learning |
| `agil` | 156 | quando o tempo é curto |
| `rapido` | 170 | só para quem já conhece o sistema |

Recomendação: **140 a 150 palavras/min** para entendimento confortável; acelere só quando o tempo for curto.
Também vale um número (`--ritmo 150`). A calibração mede o ritmo real da voz num texto de referência e ajusta a
escala de duração (`length_scale` no Piper, `speed` no Kokoro) até ficar a 2% do alvo.

Os **avisos de roteiro** usam a taxa do ritmo escolhido: "acrescente ~N palavras" converte os segundos que
faltam em palavras por `palavras/min ÷ 60` (a 145 pal/min, 1 s ≈ 2,4 palavras).

TTS em nuvem (ex.: edge-tts) é **opcional e fica desligado**: o texto do roteiro sairia da máquina. Ver
`references/seguranca.md` para a aprovação explícita que isso exige.

## Fonética: sugerir e fixar

- O dicionário fica em `<área>/fonetica/dicionario.json` (nasce do modelo da skill, vazio).
- Aplicado em **toda** síntese: palavra inteira, a mais longa primeiro, sensível a maiúsculas.
- A **legenda usa sempre o texto escrito**; só a voz recebe a grafia fonética.
- `sugerir` sem `--opcoes` gera candidatas por heurística: a palavra como está, sigla soletrada
  ("á pê í"), sigla lida como palavra, grafia aportuguesada ("uebi") e acento na sílaba tônica.
- Se a voz já fala certo, escolha a opção 1 (a palavra como está): ela entra no dicionário e sai da lista de faltantes.
- O Whisper é só indício: ele também erra siglas. A escolha é de ouvido.

## Legenda

| Modo | Resultado |
| --- | --- |
| `nenhuma` | sem legenda |
| `faixa` | legenda soft (`mov_text`) no MP4, PT; o player liga e desliga; `.srt` ao lado |
| `queimada` | gravada na imagem (letra branca, contorno e faixa escura; estilo em `projeto.json`) |
| `arquivo` | só o `.srt` ao lado do vídeo |

Conferência opcional: `vdia legenda whisper` (faster-whisper local; o modelo vem do cache, e baixar exige `--baixar`).

## Rotas de gravação

| Rota | Quando | Mouse do usuário |
| --- | --- | --- |
| web (`vdia.gravar_web`) | app no navegador | intocado (Chromium headless, cursor desenhado) |
| offscreen (`references/rota-desktop-offscreen.md`) | app Qt/PySide (adaptável a outros toolkits) | intocado (motor dentro do app) |
| desktop com mouse real (`vdia.gravar_desktop`) | app desktop que não dá para filmar por dentro | **ocupado**: combine o horário |
| imagens (`vdia imagem`) | telas estáticas, prints | intocado |

**Web:** `preparar(pg)` (fora da gravação) e `acoes(pg, relogio)` (gravado). `zoom_css` amplia a página como o zoom
do navegador (o app não muda) para a letra ficar legível em 1080p; recorte/zoom extra na montagem com
`montagem/recortes.json`.

**Desktop com mouse real: trava de segurança obrigatória.** Todo clique, scroll, arrasto, tecla ou texto passa por
`Trava.conferir()`: a tela não pode estar bloqueada; o cursor tem de estar onde o script o deixou (senão alguém
mexeu no mouse e tudo aborta); a janela sob o cursor e a janela da frente têm de ser do pid do app. Antes de gravar:
`esperar_ocioso` (o PC sem uso por N s, via `GetLastInputInfo`) e `trazer_para_frente`. O FAILSAFE do PyAutoGUI fica
ligado (cursor no canto superior esquerdo aborta). A gravação cobre só a janela, recortada à área útil.

## Vídeo único com aberturas

Num projeto próprio (`vdia novo apresentacao`), crie `unico.json` (`vdia unico --modelo` imprime um exemplo) com:
tema (cores e fonte), cartela inicial, fecho e a lista de partes (MP4 final, nome, título, fala, visual
`ondas|grade|particulas|aneis`, transições de entrada e saída). `vdia unico` então:
- grava as aberturas de `assets/abertura.html` (HTML/CSS/canvas local, sem CDN) com o Playwright;
- fala o nome de cada parte com pausa antes e depois (`pausa_s`, 0,75 s), com fundo sonoro gerado no ffmpeg;
- junta com xfade variado e crossfade de áudio, e a legenda das partes deslocada + os nomes das aberturas;
- faz QA ignorando as pausas intencionais das aberturas (pausa que a parte já tinha conta como herdada);
- **remonta quando uma parte muda**: só regrava a abertura cujo tempo ou texto mudou (`--forcar` regrava todas).
Sem logo nem identidade de instituição: só o texto e as cores que você puser no tema.

## Solução de problemas

| Sintoma | Causa e saída |
| --- | --- |
| "tela bloqueada" na rota desktop | a sessão do Windows bloqueou; desbloqueie e desative o bloqueio automático durante a gravação |
| "o app não veio para a frente" | o Windows só cede o foco a quem teve a última entrada: não use o PC na hora; feche notificações |
| "alguém mexeu no mouse" | a trava abortou; deixe o PC livre e grave de novo (combine o horário) |
| QA reprova pausa | fala curta para a ação ou respiro grande; siga os avisos ("acrescente ~N palavras") ou encurte as ações |
| "N s de imagem parada" | fala longa para a ação: acrescente ação na tela ou corte palavras |
| letra pequena no vídeo | web: `zoom_css` 1,25 a 1,5; montagem: `recortes.json`; desktop: aumente a fonte do app |
| texto em quadradinhos (offscreen) | a plataforma offscreen não vê as fontes do sistema: registre uma TTF (ver o exemplo) |
| `ffmpeg` sem `subtitles` | o build não tem libass: use `faixa` ou instale um ffmpeg completo |
| voz "não instalada" | `vdia instalar <id>` ou `VDIA_MODELOS` apontando para os modelos |

## Limites

- A rota desktop com mouse real é só Windows (Win32 por ctypes). No Linux, use offscreen, web ou imagens.
- O ritmo do Piper varia um pouco a cada síntese; a calibração aceita 2% e as falas são medidas de novo na montagem.
- A heurística de fonética é simples (sugere, não acerta): a escolha é sempre de ouvido.
- O Whisper serve só de indício; o download do modelo exige aprovação.
- O download das vozes (`vdia instalar`) não foi exercitado nos testes deste rascunho: os testes usaram modelos já
  baixados e conferiram os sha256.
- O vídeo único espera partes em 1920x1080 a 30 fps com áudio; o fundo do tema não pode ser branco puro (o branco
  marca o início da gravação das aberturas).
- Tudo em PT-BR (vozes, textos, heurísticas).

## Testes

```bash
cd scripts
VDIA_MODELOS=<pasta dos modelos> uv run pytest -q     # ~2,5 min; sem VDIA_MODELOS os testes de voz são pulados
uv run ruff check . && uv run basedpyright            # lint e tipos (strict)
```

Terceiros, versões e licenças: `references/terceiros.md`.

## Licença

O código desta skill está sob a licença MIT (`LICENSE`). As ferramentas e vozes de terceiros que ela usa têm licenças próprias, e nenhuma vem embutida no repositório. Os modelos são baixados pelo `vdia instalar`. Destaque: o `piper-tts` é GPL-3.0. A lista completa, com versões e links, está em `references/terceiros.md`.
