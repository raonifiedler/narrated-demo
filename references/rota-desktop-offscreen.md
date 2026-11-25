# Rota desktop offscreen: o motor de roteiro dentro do app

**Padrão recomendado quando o app é Qt/PySide** (e o código do app está à mão, numa cópia). Em vez de mover o mouse
real e gravar a tela, um motor dentro do próprio app compõe as janelas, desenha o cursor e executa os gestos.

## Por que

| Mouse real (PyAutoGUI + gdigrab) | Offscreen (motor no app) |
| --- | --- |
| ocupa o mouse e o teclado do usuário | o PC fica livre; roda até em servidor sem tela |
| depende de foco, DPI, notificações, tela bloqueada | nada disso existe (`QT_QPA_PLATFORM=offscreen`) |
| tempo real: um atraso do app vira atraso no vídeo | tempo virtual: cada tique é um quadro; o vídeo é determinístico |
| precisa da trava de segurança | não toca em nada fora do processo |

## Como funciona (exemplo: `scripts/exemplos/offscreen_pyside6.py`)

1. `QT_QPA_PLATFORM=offscreen` antes de criar a `QApplication`; a janela recebe `resize(1920, 1080)` e `show()`.
2. **Fonte:** a plataforma offscreen não enxerga as fontes do sistema; registre uma TTF com
   `QFontDatabase.addApplicationFont` (senão o texto vira quadradinhos).
3. **Gestos** são dados: `Gesto(alvo, dur, acao, clique, digitar)`. O alvo é uma função que devolve a posição de
   um widget achado por `objectName` (`findChild`), então o roteiro sobrevive a mudanças de layout.
4. **Motor:** um `QTimer` com intervalo 0 chama `tique()`; cada tique é um quadro de 1/30 s. O cursor anda com
   easing da origem ao alvo; no fim do gesto, o clique vai ao widget com `QTest.mouseClick` e as teclas com
   `QKeyEvent` (eventos Qt de verdade: sinais e validações do app rodam como no uso real).
   - `QTest.keyClicks` derruba o processo com caracteres acentuados no PySide6 6.12 offscreen; use `QKeyEvent`
     com o texto, como no exemplo.
5. **Quadro:** `janela.grab()` + cursor desenhado (seta e anel de clique) num `QImage` 1920x1080 RGB888, enviado
   cru ao `ffmpeg -f rawvideo` (respeite `bytesPerLine`).
6. **Estado antes do clipe** (o "caminho até a tela"): o motor executa passos sem gravar (abrir arquivo, importar
   dados fictícios, selecionar) e só então começa a mandar quadros. Um clipe por funcionalidade: um `MotorRoteiro`
   por clipe, ou um campo `gravar: bool` por gesto.
7. Popups e diálogos modais: grave a janela de nível superior que estiver ativa (`QApplication.activeModalWidget()`
   ou `activePopupWidget()`) e componha sobre a principal na posição dela (`mapToGlobal`). Menus nativos não
   existem no offscreen: use os do Qt.
8. Conteúdo web embutido (QWebEngineView) pode não pintar no `grab()`; nesse caso grave essa área com a rota web ou
   use a rota com mouse real só para essa cena.

## Adaptar a outros toolkits

O padrão é o mesmo: **renderizar a janela num buffer, desenhar o cursor, disparar eventos do próprio toolkit e
contar o tempo em quadros.**

| Toolkit | Renderizar sem tela | Disparar eventos |
| --- | --- | --- |
| Qt (C++/PySide/PyQt) | `QT_QPA_PLATFORM=offscreen` + `QWidget.grab()` / `QQuickWindow.grabWindow()` | `QTest`, `QCoreApplication.sendEvent` |
| GTK 4 | `GDK_BACKEND=broadway` ou Xvfb + `gtk_widget_snapshot` / `GskRenderer` | `gtk_test_widget_*`, sinais |
| Tkinter | Xvfb (Linux) + captura da janela (`xwd`/ffmpeg x11grab) | `widget.event_generate("<Button-1>", x=, y=)` |
| Electron / Tauri | é web: use a rota web (Playwright conecta ao Electron; Tauri expõe o WebView) | Playwright |
| WinForms / WPF | `Control.DrawToBitmap` / `RenderTargetBitmap` | `SendMessage`/UI Automation dentro do processo |
| Jogos e canvas próprios | o próprio loop de render escreve o quadro | injete os eventos no loop |

Regra: o motor fica numa **cópia** do app (ou atrás de uma flag de desenvolvimento) e nunca muda o comportamento
do app, só o observa e o dirige.
