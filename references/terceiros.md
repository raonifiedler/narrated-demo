# Ferramentas de terceiros

Nenhum binário, modelo ou skill de terceiros está copiado nesta skill. Os pacotes Python vêm do PyPI pelo
`uv sync`; os modelos de voz são baixados por `vdia instalar` (URLs e sha256 em `scripts/vdia/vozes.json`).
"Versão testada" = a instalada no ambiente em que os testes desta skill passaram (Windows 11, CPU).
Confira as licenças de novo antes de uso comercial ou redistribuição.

| Ferramenta | Versão testada | URL | Licença | Uso aqui |
| --- | --- | --- | --- | --- |
| Piper (`piper-tts`) | 1.8.0 | https://github.com/OHF-Voice/piper1-gpl (o antigo rhasspy/piper está arquivado) | GPL-3.0-or-later (embute espeak-ng) | TTS local principal |
| Vozes Piper pt_BR faber e cadu (medium) | arquivos de `rhasspy/piper-voices` | https://huggingface.co/rhasspy/piper-voices | repositório MIT; dados de treino CC0 segundo o MODEL_CARD de cada voz | vozes `piper-faber`, `piper-cadu` |
| kokoro-onnx | 0.6.1 | https://github.com/thewh1teagle/kokoro-onnx | MIT | TTS local alternativo |
| Kokoro-82M (pesos, vozes pm_alex e pf_dora) | model-files-v1.0 | https://huggingface.co/hexgrad/Kokoro-82M (ONNX nos releases do kokoro-onnx) | Apache-2.0 | vozes `kokoro-alex`, `kokoro-dora` |
| phonemizer / espeakng-loader (dependências do Kokoro) | 3.6.0 / 0.2.4 | PyPI | GPL-3.0 / MIT (espeak-ng GPL-3.0) | fonemização pt-br |
| ONNX Runtime | 1.32.0 | https://github.com/microsoft/onnxruntime | MIT | inferência das vozes |
| Playwright para Python | 1.65.2 | https://github.com/microsoft/playwright-python | Apache-2.0 | rota web (`page.screencast`, `show_actions`) e gravação das aberturas |
| FFmpeg / ffprobe | build N-125752 (2026-07) | https://ffmpeg.org | LGPL-2.1+ ou GPL conforme o build (libx264 e libass: GPL) | gravação gdigrab, montagem, xfade, legenda, QA |
| PyAutoGUI | 0.9.54 | https://github.com/asweigart/pyautogui | BSD-3-Clause | rota desktop com mouse real (extra `desktop`); sem commit desde 2023 |
| pywinauto | 0.6.9 | https://github.com/pywinauto/pywinauto | BSD-3-Clause | localizar elementos por UI Automation (extra `desktop`, opcional) |
| faster-whisper | 1.2.1 | https://github.com/SYSTRAN/faster-whisper | MIT (modelos Whisper: MIT) | conferência da legenda (extra `whisper`) |
| soundfile | 0.14.0 | https://github.com/bastibe/python-soundfile | BSD-3-Clause | leitura e escrita de WAV |
| pydantic | 2.14.4 | https://github.com/pydantic/pydantic | MIT | validação de `projeto.json`, `unico.json`, catálogo |
| NumPy | 2.5.5 | https://numpy.org | BSD-3-Clause | dependência do Kokoro |
| PySide6 (Essentials) | 6.12.0 | https://doc.qt.io/qtforpython | LGPL-3.0 ou GPL-2.0/3.0 (ou comercial) | só o exemplo da rota offscreen (extra `offscreen`) |
| HyperFrames (opcional, não usado pelos scripts) | 0.9.89 (testada na avaliação inicial) | https://github.com/heygen-com/hyperframes | Apache-2.0 | títulos e faixas ricas, se o usuário quiser |
| edge-tts (documentado, desligado) | 7.3.1 (avaliado, não instalado aqui) | https://github.com/rany2/edge-tts | LGPL-3.0 | TTS em nuvem só com aprovação explícita |

## HyperFrames: telemetria e skills

- Render local por `npx hyperframes@<versão> render` (fixe a versão: a API ainda é pré-1.0).
- Telemetria: exporte `DO_NOT_TRACK=1` antes de rodar (a eficácia não foi verificada).
- Os HTML gerados pelos modelos do HyperFrames puxam GSAP de CDN; as aberturas desta skill **não** usam
  HyperFrames nem CDN (`scripts/vdia/assets/abertura.html` é canvas/CSS puro).
- **Skills do HyperFrames:** não foram copiadas para cá. Quem quiser instalá-las roda, por conta própria,
  `npx hyperframes skills update` (núcleo) ou `npx hyperframes skills update <nome>`; elas carregam numa sessão nova
  do agente. A licença (Apache-2.0) permitiria copiar com aviso, mas não há necessidade, e uma delas (`media-use`)
  prefere serviços pagos de nuvem e pede login antes de cair no TTS local: se instalar, instrua o agente a usar só
  render local e TTS local, sem login.

## Avaliadas e não usadas
VoiceStudio (AGPL-3.0; voz padrão com pesos CC-BY-NC), F5-TTS, XTTS-v2 e MMS-TTS (pesos não comerciais),
Remotion (licença paga para empresas acima de 3 pessoas), OpenCut (sem entrega, reescrita), Cap (AGPL),
OBS websocket (alternativa de gravação, GPL), MoviePy (desnecessário: ffmpeg direto).
