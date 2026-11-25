"""Rota desktop com MOUSE REAL (Windows): PyAutoGUI com easing + ffmpeg gdigrab (`draw_mouse`).

Use só quando o app não puder ser filmado por dentro (rota offscreen, ver references/rota-desktop-offscreen.md).
O mouse e o teclado do usuário ficam ocupados: combine o horário e deixe o PC livre.

TRAVA DE SEGURANÇA (obrigatória; não há gesto fora dela): antes de cada clique, scroll, arrasto, tecla ou texto
  1. a tela não pode estar bloqueada;
  2. o cursor tem de estar onde o script o deixou (senão alguém mexeu no mouse: aborta);
  3. a janela sob o cursor E a janela da frente têm de ser do pid do app;
  + FAILSAFE do PyAutoGUI (cursor no canto superior esquerdo aborta tudo).
Antes de gravar: `esperar_ocioso` (GetLastInputInfo) e `trazer_para_frente`.

    sessao = SessaoDesktop(pid=app.pid)
    sessao.esperar_ocioso(20)
    sessao.trazer_para_frente(hwnd)
    with sessao.gravando(regiao, pasta / "clipe0.mp4"):
        sessao.ir(400, 300)
        sessao.clicar()
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


def suave(n: float) -> float:
    """Easing in-out quadrático (trajetória que acelera e freia, legível no vídeo)."""
    return 2 * n * n if n < 0.5 else 1 - (-2 * n + 2) ** 2 / 2


class GestoCancelado(RuntimeError):
    """A trava recusou o gesto: nada foi tocado."""


class Interferencia(GestoCancelado):
    """Alguém mexeu no mouse durante a gravação."""


class TelaBloqueada(GestoCancelado):
    """A sessão do Windows está bloqueada (ou o desktop seguro está ativo)."""


class Sistema(Protocol):
    """O que a trava precisa do sistema operacional (trocável nos testes)."""

    def posicao(self) -> tuple[int, int]: ...
    def pid_sob(self, x: int, y: int) -> int: ...
    def pid_frente(self) -> int: ...
    def tela_bloqueada(self) -> bool: ...
    def ocioso_s(self) -> float: ...


class _Ponto(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _LII(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class _Ret(ctypes.Structure):
    _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]


class SistemaWindows:
    """Win32 por ctypes. Só existe no Windows."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise NotImplementedError("rota desktop com mouse real: só Windows nesta versão (ver README, Limites)")
        self.u32 = ctypes.WinDLL("user32", use_last_error=True)
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.u32.WindowFromPoint.argtypes = [_Ponto]
        self.u32.WindowFromPoint.restype = ctypes.c_void_p
        self.u32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.u32.GetAncestor.restype = ctypes.c_void_p
        self.u32.GetForegroundWindow.restype = ctypes.c_void_p
        self.u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        self.u32.OpenInputDesktop.restype = ctypes.c_void_p
        self.u32.SwitchDesktop.argtypes = [ctypes.c_void_p]
        self.u32.CloseDesktop.argtypes = [ctypes.c_void_p]
        self.u32.SetProcessDPIAware()

    def _pid(self, hwnd: int | None) -> int:
        if not hwnd:
            return 0
        raiz = self.u32.GetAncestor(hwnd, 2)  # GA_ROOT
        pid = ctypes.c_ulong(0)
        self.u32.GetWindowThreadProcessId(raiz, ctypes.byref(pid))
        return int(pid.value)

    def posicao(self) -> tuple[int, int]:
        p = _Ponto()
        self.u32.GetCursorPos(ctypes.byref(p))
        return int(p.x), int(p.y)

    def pid_sob(self, x: int, y: int) -> int:
        return self._pid(self.u32.WindowFromPoint(_Ponto(x, y)))

    def pid_frente(self) -> int:
        return self._pid(self.u32.GetForegroundWindow())

    def tela_bloqueada(self) -> bool:
        # Com a sessão bloqueada (ou UAC/Ctrl+Alt+Del), o desktop de entrada não pode ser ativado por nós.
        h = self.u32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
        if not h:
            return True
        try:
            return not self.u32.SwitchDesktop(h)
        finally:
            self.u32.CloseDesktop(h)

    def ocioso_s(self) -> float:
        lii = _LII(ctypes.sizeof(_LII), 0)
        self.u32.GetLastInputInfo(ctypes.byref(lii))
        return (int(self.k32.GetTickCount()) - int(lii.dwTime)) / 1000.0

    def area_util(self) -> tuple[int, int, int, int]:
        a = _Ret()
        self.u32.SystemParametersInfoW(0x0030, 0, ctypes.byref(a), 0)  # SPI_GETWORKAREA
        return int(a.l), int(a.t), int(a.r), int(a.b)

    def trazer_para_frente(self, hwnd: int, pid: int) -> bool:
        for _ in range(4):
            # o Windows só cede o foco a quem teve a última entrada: Alt sintético antes do pedido
            self.u32.keybd_event(0x12, 0, 0, 0)
            try:
                self.u32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
                self.u32.SetForegroundWindow(ctypes.c_void_p(hwnd))
            finally:
                self.u32.keybd_event(0x12, 0, 2, 0)
            time.sleep(0.6)
            if self.pid_frente() == pid:
                return True
        return False


@dataclass
class Trava:
    """A conferência que antecede TODO gesto. Pura: recebe o Sistema, não move nada."""

    pid: int
    sistema: Sistema
    tolerancia_px: int = 4
    esperado: tuple[int, int] | None = None

    def conferir(self) -> None:
        s = self.sistema
        if s.tela_bloqueada():
            raise TelaBloqueada("tela bloqueada: gravação cancelada sem tocar em nada")
        x, y = s.posicao()
        if self.esperado is not None:
            ex, ey = self.esperado
            if abs(x - ex) > self.tolerancia_px or abs(y - ey) > self.tolerancia_px:
                raise Interferencia(f"cursor em ({x},{y}), esperado ({ex},{ey}): alguém mexeu no mouse")
        sob, frente = s.pid_sob(x, y), s.pid_frente()
        if sob != self.pid or frente != self.pid:
            raise GestoCancelado(
                f"cursor em ({x},{y}) fora do app (pid {self.pid}; sob o cursor {sob}, "
                f"na frente {frente}): gesto cancelado"
            )


@dataclass
class SessaoDesktop:
    pid: int
    sistema: SistemaWindows = field(default_factory=SistemaWindows)
    log: list[dict[str, object]] = field(default_factory=lambda: [])
    t0: float = field(default_factory=time.perf_counter)

    def __post_init__(self) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self.trava = Trava(self.pid, self.sistema)

    def marca(self, acao: str, **d: object) -> None:
        self.log.append({"t": round(time.perf_counter() - self.t0, 3), "acao": acao} | d)

    def esperar_ocioso(self, minimo_s: float = 20.0, prazo_s: float = 1800.0) -> None:
        fim = time.monotonic() + prazo_s
        while self.sistema.ocioso_s() < minimo_s:
            if time.monotonic() > fim:
                raise GestoCancelado("o PC não ficou ocioso no prazo; gravação adiada")
            time.sleep(2)

    def trazer_para_frente(self, hwnd: int, espera_s: float = 2.5) -> None:
        if not self.sistema.trazer_para_frente(hwnd, self.pid):
            raise GestoCancelado("o app não veio para a frente; gravação cancelada")
        time.sleep(espera_s)  # a barra de tarefas some

    # gestos: TODOS passam pela trava
    def ir(self, x: float, y: float, dur: float = 0.6) -> None:
        import pyautogui

        if self.trava.esperado is not None:
            self.trava.conferir()  # ninguém mexeu desde o último gesto
        pyautogui.moveTo(round(x), round(y), duration=dur, tween=suave)
        self.trava.esperado = (round(x), round(y))

    def clicar(self, duplo: bool = False, pausa_s: float = 0.6) -> None:
        import pyautogui

        time.sleep(pausa_s)
        self.trava.conferir()
        self.marca("clique", x=self.trava.esperado)
        if duplo:
            pyautogui.doubleClick()
        else:
            pyautogui.click()

    def rolar(self, n: int) -> None:
        import pyautogui

        self.trava.conferir()
        pyautogui.scroll(n)

    def arrastar(self, x: float, y: float, dur: float = 1.0) -> None:
        import pyautogui

        self.trava.conferir()
        pyautogui.mouseDown()
        try:
            pyautogui.moveTo(round(x), round(y), duration=dur, tween=suave)
            self.trava.esperado = (round(x), round(y))
            self.trava.conferir()
        finally:
            pyautogui.mouseUp()

    def digitar(self, texto: str, intervalo_s: float = 0.06) -> None:
        import pyautogui

        self.trava.conferir()
        pyautogui.write(texto, interval=intervalo_s)

    def tecla(self, *teclas: str) -> None:
        import pyautogui

        self.trava.conferir()
        pyautogui.hotkey(*teclas)

    @contextmanager
    def gravando(self, regiao: tuple[int, int, int, int], destino: Path, fps: int = 30) -> Generator[None]:
        """Grava só a região do app (recortada à área útil: sem a barra de tarefas), com o cursor real."""
        l, t, r, b = self.sistema.area_util()  # noqa: E741
        x, y, w, h = regiao
        x0, y0, x1, y1 = max(x, l), max(y, t), min(x + w, r), min(y + h, b)
        w2, h2 = (x1 - x0) // 2 * 2, (y1 - y0) // 2 * 2
        destino.parent.mkdir(parents=True, exist_ok=True)
        ff = subprocess.Popen(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-f",
                "gdigrab",
                "-framerate",
                str(fps),
                "-draw_mouse",
                "1",
                "-offset_x",
                str(x0),
                "-offset_y",
                str(y0),
                "-video_size",
                f"{w2}x{h2}",
                "-i",
                "desktop",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "16",
                "-pix_fmt",
                "yuv420p",
                str(destino),
            ],
            stdin=subprocess.PIPE,
        )
        try:
            time.sleep(0.5)
            yield
        finally:
            if ff.stdin:
                ff.stdin.write(b"q")
                ff.stdin.flush()
            ff.wait(timeout=60)
