# Regras de produção (R1 a R8)

Valem para todo vídeo feito com a narrated-demo. O montador e o QA aplicam as que dá para medir.

## R1. A abertura diz o que é e para que serve
O 1º clipe responde em até 15 s: **o que é** o sistema, **para que é usado** e **o que melhora** (missão,
qualidade de vida ou eficiência). Os clipes seguintes mostram as funcionalidades.

## R2. Um clipe por funcionalidade, sem o caminho até ela
- Cada funcionalidade é um clipe separado que já começa na tela certa.
- O caminho (login, menus, importar arquivo, abrir projeto) roda **antes** da gravação e não aparece:
  `preparar` na web; o motor de roteiro na rota offscreen; o script antes de `gravando()` no desktop.
- Entre clipes, transição de 0,5 s (`fade`, `smoothleft`, `circleopen`...).

## R3. A fala manda no tempo: sem silêncio
O áudio é sintetizado primeiro e o vídeo se ajusta a ele:

| Situação | O montador |
| --- | --- |
| ação mais longa que a fala | acelera até 2× e, se ainda sobrar, corta o fim |
| ação mais curta que a fala | desacelera até 1,4× e, se ainda faltar, congela o último quadro |

- O silêncio que o TTS põe no começo e no fim de cada fala é aparado; entre falas, respiro de 0,2 s.
- **QA:** reprova pausa maior que `pausa_max_s` (0,7 s), medida com `silencedetect`.
- **Avisos de roteiro**, pela taxa de palavras/s do ritmo escolhido: "fala curta para a ação: acrescente
  ~N palavras" e "N s de imagem parada: acrescente ação ou encurte a fala".
- Cada aviso volta para o roteiro, e a rodada se repete até não haver aviso.

## R4. Ritmo de escrita
- Ritmo escolhido pelo usuário: calmo 130, **padrão 145**, ágil 156, rápido 170 palavras/min (ou um número).
  Recomende 140 a 150; acelere só quando o tempo for curto. A voz já sai no ritmo (calibração da escala);
  não acelere o vídeo depois.
- Uma frase por ação visível. A fala descreve **o que está na tela naquele momento**: nada citado e não mostrado,
  nada mostrado e não citado.
- A ação com o mouse dura de 1 a 1,3 vezes a fala. Movimentos lentos: trajetória suave e ~0,6 s antes de cada clique.

## R5. Verdade e dados
- Toda funcionalidade citada é comprovada no código ou na tela, com o arquivo anotado em **Prova:**.
- O que não existe vira "proposta" na fala, e a prova diz "sem campo/sem código: proposta".
- Só dados fictícios (lorem ipsum, nomes inventados, exemplos de demonstração). Nunca dados reais.
- O repositório original nunca é alterado: tudo roda numa cópia.

## R6. Segurança da rota desktop com mouse real
- O app vem para a frente e espera ~2,5 s (a barra de tarefas some); a gravação cobre só a janela, na área útil.
- **Trava** antes de cada gesto: tela desbloqueada; cursor onde o script o deixou; janela sob o cursor e janela da
  frente do pid do app. Se algo falhar, aborta sem tocar em nada.
- O PC fica livre durante a gravação (`esperar_ocioso`); o usuário combina o horário. FAILSAFE ligado.
- Prefira a rota offscreen quando o app for seu e for Qt (ou adaptável): não usa o mouse real.

## R7. Pronúncia
- A legenda fica como o texto escrito.
- A fala passa pelo dicionário da área de trabalho (palavra inteira, a mais longa primeiro, sensível a maiúsculas).
- Palavra nova: `vdia fonetica sugerir` gera um WAV de opções numeradas; o usuário escolhe; `escolher` grava.
- Transcrição automática (Whisper) é só indício.

## R8. Entrega
- Um MP4 por vídeo: 1920×1080 (paisagem) ou 1080×1920 (`formato: retrato`, celular em pé), 30 fps, H.264 + AAC; legenda conforme o modo (`nenhuma`, `faixa`, `queimada`, `arquivo`).
- Confira a soma das durações contra o teto combinado com o usuário.
- Vídeo único (opcional): cartela inicial, uma abertura por parte com o nome falado e pausa intencional antes e
  depois, transições variadas com crossfade de áudio, fecho; o QA ignora as pausas das aberturas; a legenda das
  partes entra deslocada; quando uma parte muda, `vdia unico` remonta e só regrava o que mudou.
