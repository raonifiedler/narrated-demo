---
name: narrated-demo
description: Produz vídeos de demonstração de software narrados em PT-BR, tudo local. A IA faz o briefing, escreve o roteiro, opera o app (web pelo Playwright, desktop com mouse real e trava de segurança, ou offscreen dentro de um app Qt) com cursor visível, grava a tela, gera a narração com TTS local (Piper/Kokoro), ajusta a fonética, monta o vídeo (a fala manda no tempo, xfade, legenda opcional) e roda o QA de pausas. Use quando o usuário pedir para "fazer vídeo de demonstração", "gravar tela com narração", "vídeo do sistema", "roteiro de vídeo", "vídeo de apresentação do app", "tutorial em vídeo" ou, em inglês, "narrated demo", "screencast with voiceover", "app walkthrough video", "product demo video".
---

# narrated-demo: vídeo de demonstração narrado, feito pela IA

Ferramentas: `scripts/` (pacote Python `vdia`, CLI `vdia`). Rode sempre assim, da pasta de trabalho do usuário:

```
uv run --project "<pasta desta skill>/scripts" vdia <comando>
```

A pasta de trabalho é `VDIA_AREA` ou a pasta atual. Os modelos de voz ficam em `VDIA_MODELOS` (ou no cache
do usuário). Comandos e exemplos: `README.md`. Regras completas: `references/regras-producao.md`.

## Regras que valem o tempo todo

- **Verdade:** só cite o que existe no código ou na tela, com o arquivo ou a tela anotados em **Prova:** no
  roteiro. O que não existe vira "proposta" na fala ("na proposta, cada tarefa terá...").
- **Dados fictícios** sempre (nomes, números, documentos). Nada real na tela.
- **Cópia, nunca o original:** clone o repositório para uma pasta de trabalho e rode tudo lá.
- **Avise antes** de subir Docker ou serviços, e antes de usar o mouse real (o usuário precisa deixar o PC livre).
- **Nada sai da máquina** sem aprovação explícita: TTS em nuvem fica desligado; prints e telas não vão para
  serviços externos; baixar modelos (voz, Whisper) só com o ok do usuário. Ver `references/seguranca.md`.
- Não afrouxe o QA para passar: o conserto é no roteiro ou nas ações.

## Etapas

### 1. Briefing
Pergunte e anote em `roteiro/BRIEFING.md` (crie o projeto antes com `vdia novo <nome>`):
- o que é o sistema, para que serve, quem usa, o que melhora (missão, qualidade de vida ou eficiência);
- as funcionalidades a mostrar (uma cena por funcionalidade) e a ordem;
- de onde vêm os dados fictícios; duração-alvo; rota de gravação (web, desktop, offscreen, imagens);
- voz e ritmo (etapa 5) e modo de legenda (`nenhuma`, `faixa`, `queimada`, `arquivo`).

Leia o código para achar a prova de cada funcionalidade antes de escrever a fala.

### 2. Roteiro (PARE para aprovação)
Escreva `roteiro/ROTEIRO.md` no formato de `references/roteiro-modelo.md`: por cena, `[o que aparece na tela]`,
a fala, a prova e a transição. A 1ª cena diz em até 15 s o que é, para que serve e o que melhora.
Rode `vdia roteiro medir` (tempos por cena e `roteiro/narracao.wav`). **Pare e peça ao usuário para aprovar e
reescrever o texto.** Não grave nada antes do ok.

### 3. Fonética
`vdia fonetica faltantes` lista siglas e nomes estrangeiros sem entrada. Para cada um:
`vdia fonetica sugerir "<palavra>" --frase "<frase do roteiro>"` gera um WAV com "Opção 1… Opção 2…".
Mande o WAV ao usuário, ele escolhe o número, e você grava com `vdia fonetica escolher "<palavra>" <n>`
(`--variantes-caixa` para gravar minúscula, Título e MAIÚSCULA). A legenda nunca muda: só a fala.
Página para ouvir com e sem o dicionário: `vdia fonetica servir` (127.0.0.1).

### 4. Gravação: um clipe por funcionalidade
O caminho até a tela (login, menus, abrir arquivo) roda **fora** da gravação; cada clipe já começa na tela certa.
Saída: `cenas/bruto<i>.webm|mp4`, na ordem das cenas. Rotas (detalhes no README):
- **web:** `scripts/gravar.py` (modelo criado pelo `novo`) com `vdia.gravar_web` (Playwright, cursor desenhado,
  `zoom_css` para letra legível);
- **offscreen (Qt/PySide):** motor de roteiro dentro do app, sem mouse real (`references/rota-desktop-offscreen.md`);
- **desktop com mouse real:** `vdia.gravar_desktop.SessaoDesktop` com a trava obrigatória
  (`references/seguranca.md`); combine o horário com o usuário;
- **imagens:** `vdia imagem <print.png> cenas/bruto<i>.mp4` (zoom lento).
Ação com o mouse: de 1 a 1,3 vezes a duração da fala; trajetória suave; ~0,6 s antes de cada clique.
Confira 2 ou 3 quadros de cada clipe (ffmpeg) antes de montar.

### 5. Narração (voz e ritmo)
`vdia voz amostra` gera um WAV com a mesma frase em cada voz instalada ("Voz 1… Voz 2…"). O usuário escolhe;
`vdia voz escolher <n> --ritmo padrao` grava em `projeto.json` e calibra a escala da voz para o ritmo
(calmo 130, **padrao 145**, agil 156, rapido 170 palavras/min, ou um número). Recomende 140 a 150; acelerar só
quando o tempo for curto.

### 6. Montagem
`vdia montar [--legenda faixa|queimada|arquivo|nenhuma]`: a fala manda no tempo; o clipe acelera até 2× ou
desacelera até 1,4× e depois congela; xfade entre cenas; 1920x1080 (ou 1080x1920 com `formato: retrato`, criado por
`vdia novo <nome> --formato retrato`, para celular em pé), 30 fps, H.264 + AAC.
Recorte/zoom de uma cena densa: `montagem/recortes.json` (`{"2": [x, y, largura]}`).

### 7. QA em ciclo até zerar
O `montar` reprova pausa maior que `pausa_max_s` (0,7 s) e emite avisos de roteiro ("acrescente ~N palavras",
"N s de imagem parada"), calculados pela taxa do ritmo escolhido. Corrija o roteiro (com ok do usuário quando
a fala mudar) ou as ações, regrave o que mudou e monte de novo até sair "QA zerado". Opcional:
`vdia legenda whisper` (transcrição local, só indício).

### 8. Entrega
Entregue `final/<nome>.mp4` (+ `.srt` conforme o modo), a duração, o modo de legenda e as provas usadas.
Vídeo único com aberturas (opcional): `unico.json` + `vdia unico` (ver README).
