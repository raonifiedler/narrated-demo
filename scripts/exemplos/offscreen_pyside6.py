"""Rota desktop OFFSCREEN: um "motor de roteiro" dentro do próprio app Qt filma a janela sem tocar no mouse real.

Exemplo mínimo e genérico: um app de tarefas (lista + campo + botão). O motor:
  - roda com QT_QPA_PLATFORM=offscreen (nenhuma janela aparece; o PC fica livre);
  - executa os gestos por QTimer, em tempo VIRTUAL: cada tique = um quadro de 1/30 s (determinístico);
  - move um cursor desenhado com easing, mostra um anel no clique e entrega o clique (QTest) e as teclas
    (QKeyEvent) ao widget: eventos Qt de verdade, os sinais do app disparam como no uso real;
  - compõe o quadro com `janela.grab()` + cursor e manda RGB cru para o ffmpeg (1920x1080, 30 fps).

Rodar (da pasta scripts/):  uv run --extra offscreen python exemplos/offscreen_pyside6.py saida.mp4
Para o SEU app: importe `MotorRoteiro`, passe a janela principal e uma lista de gestos que achem os widgets
por objectName (findChild). Ver references/rota-desktop-offscreen.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase, QImage, QKeyEvent, QPainter, QPen, QPolygonF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

LARG, ALT, FPS = 1920, 1080, 30


# ── o "app" de exemplo ──────────────────────────────────────────────────────────────────────
class AppTarefas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Tarefas")
        self.setStyleSheet("QWidget{font-size:28px} QListWidget{font-size:30px}")
        self.lista = QListWidget()
        self.lista.setObjectName("lista")
        self.lista.addItems(["Revisar o relatório da semana", "Enviar o orçamento", "Marcar a reunião"])
        self.campo = QLineEdit()
        self.campo.setObjectName("campo")
        self.campo.setPlaceholderText("Nova tarefa")
        self.botao = QPushButton("Adicionar")
        self.botao.setObjectName("adicionar")
        self.botao.clicked.connect(self.adicionar)
        linha = QHBoxLayout()
        linha.addWidget(self.campo)
        linha.addWidget(self.botao)
        corpo = QVBoxLayout(self)
        corpo.addLayout(linha)
        corpo.addWidget(self.lista)

    def adicionar(self) -> None:
        texto = self.campo.text().strip()
        if texto:
            self.lista.addItem(texto)
            self.campo.clear()


# ── motor de roteiro ────────────────────────────────────────────────────────────────────────
def suave(n: float) -> float:
    return 2 * n * n if n < 0.5 else 1 - (-2 * n + 2) ** 2 / 2


@dataclass
class Gesto:
    """Um passo: mover o cursor até `alvo` (ou ficar parado) por `dur` s e, no fim, `acao`."""

    alvo: Callable[[], QPoint] | None
    dur: float
    acao: Callable[[], None] | None = None
    clique: bool = False
    digitar: tuple[QWidget, str] | None = None  # texto digitado aos poucos durante o gesto


def tecla(w: QWidget, ch: str) -> None:
    """Um caractere como evento de teclado real. (QTest.keyClicks derruba o processo com acentos no
    PySide6 6.12 offscreen; QKeyEvent com o texto funciona com qualquer caractere.)"""
    for tipo in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(w, QKeyEvent(tipo, 0, Qt.KeyboardModifier.NoModifier, ch))


class MotorRoteiro:
    def __init__(self, janela: QWidget, gestos: list[Gesto], destino: Path) -> None:
        self.janela = janela
        self.gestos = gestos
        self.cursor = QPointF(janela.width() * 0.6, janela.height() * 0.7)
        self.anel = 0  # quadros restantes do anel de clique
        self.ff = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                f"{LARG}x{ALT}",
                "-r",
                str(FPS),
                "-i",
                "-",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                str(destino),
            ],
            stdin=subprocess.PIPE,
        )
        self.i = 0  # gesto atual
        self.q = 0  # quadro dentro do gesto
        self.origem = QPointF(self.cursor)
        self.timer = QTimer()
        self.timer.timeout.connect(self.tique)

    def iniciar(self) -> None:
        self.timer.start(0)  # tempo virtual: o relógio do vídeo é o número do quadro, não o relógio da parede

    def tique(self) -> None:
        if self.i >= len(self.gestos):
            self.timer.stop()
            self.fechar()
            return
        g = self.gestos[self.i]
        n = max(round(g.dur * FPS), 1)
        if self.q == 0:
            self.origem = QPointF(self.cursor)
        if g.alvo is not None:
            destino = QPointF(g.alvo())
            k = suave(min((self.q + 1) / n, 1.0))
            self.cursor = self.origem + (destino - self.origem) * k
        if g.digitar is not None:
            w, texto = g.digitar
            ja = round(len(texto) * self.q / n)
            agora = round(len(texto) * (self.q + 1) / n)
            for ch in texto[ja:agora]:
                tecla(w, ch)
        self.quadro()
        self.q += 1
        if self.q >= n:
            if g.clique:
                pos = self.cursor.toPoint()
                alvo = self.janela.childAt(pos) or self.janela
                QTest.mouseClick(alvo, Qt.MouseButton.LeftButton, pos=alvo.mapFrom(self.janela, pos))
                self.anel = 12
            if g.acao is not None:
                g.acao()
            self.i += 1
            self.q = 0

    def quadro(self) -> None:
        img = self.janela.grab().toImage().convertToFormat(QImage.Format.Format_RGB888)
        tela = QImage(LARG, ALT, QImage.Format.Format_RGB888)
        tela.fill(QColor("white"))
        p = QPainter(tela)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawImage(0, 0, img)
        x, y = self.cursor.x(), self.cursor.y()
        if self.anel > 0:
            r = 18 + (12 - self.anel) * 3
            p.setPen(QPen(QColor(255, 140, 0, 20 * self.anel), 4))
            p.drawEllipse(QPointF(x, y), r, r)
            self.anel -= 1
        seta = QPolygonF(
            [
                QPointF(x, y),
                QPointF(x, y + 34),
                QPointF(x + 9, y + 26),
                QPointF(x + 16, y + 40),
                QPointF(x + 22, y + 37),
                QPointF(x + 15, y + 23),
                QPointF(x + 26, y + 23),
            ]
        )
        p.setPen(QPen(QColor("white"), 2))
        p.setBrush(QBrush(QColor("black")))
        p.drawPolygon(seta)
        p.end()
        ptr = tela.constBits()
        largura_linha = tela.bytesPerLine()
        dados = bytes(ptr)
        if self.ff.stdin is None:
            raise RuntimeError("ffmpeg sem stdin")
        for linha in range(ALT):  # bytesPerLine pode ter preenchimento: manda só a parte útil
            self.ff.stdin.write(dados[linha * largura_linha : linha * largura_linha + LARG * 3])

    def fechar(self) -> None:
        if self.ff.stdin:
            self.ff.stdin.close()
        self.ff.wait(timeout=120)
        QApplication.quit()


FONTES = [
    Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
]


def carregar_fonte(app: QApplication) -> None:
    """A plataforma offscreen não enxerga as fontes do sistema (o texto vira quadradinhos): registra uma."""
    for f in FONTES:
        if f.exists():
            fid = QFontDatabase.addApplicationFont(str(f))
            familias = QFontDatabase.applicationFontFamilies(fid)
            if familias:
                app.setFont(QFont(familias[0]))
                return
    raise SystemExit("nenhuma fonte TTF encontrada para a plataforma offscreen; ajuste FONTES")


def centro(w: QWidget, janela: QWidget) -> QPoint:
    return w.mapTo(janela, w.rect().center())


def main() -> None:
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "offscreen-exemplo.mp4").resolve()
    app = QApplication(sys.argv)
    carregar_fonte(app)
    j = AppTarefas()
    j.resize(LARG, ALT)
    j.show()
    campo = j.findChild(QLineEdit, "campo")
    botao = j.findChild(QPushButton, "adicionar")
    lista = j.findChild(QListWidget, "lista")
    if campo is None or botao is None or lista is None:
        raise SystemExit("widgets do roteiro não encontrados (objectName)")
    gestos = [
        Gesto(None, 0.5),
        Gesto(lambda: centro(lista, j), 1.0),
        Gesto(lambda: centro(campo, j), 0.9, clique=True),
        Gesto(None, 1.6, digitar=(campo, "Preparar a apresentação")),
        Gesto(None, 0.8),
        Gesto(lambda: centro(botao, j), 0.8, clique=True),
        Gesto(None, 1.2),
    ]
    motor = MotorRoteiro(j, gestos, destino)
    motor.iniciar()
    app.exec()
    print(destino)


if __name__ == "__main__":
    main()
