"""The small recording indicator that appears in a screen corner without taking focus."""

import math

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QFontMetrics
from PyQt6.QtWidgets import QWidget, QApplication

BARS = 22
HEIGHT = 56
MIN_WIDTH = 210
MAX_WIDTH = 460
MARGIN = 28

BG = QColor(22, 24, 29, 238)
BORDER = QColor(255, 255, 255, 28)
TEXT = QColor(235, 237, 242)
MUTED = QColor(150, 156, 168)
REC = QColor(240, 78, 82)
BUSY = QColor(120, 170, 255)
OK = QColor(80, 205, 140)
ERR = QColor(240, 100, 90)

STATE_COLORS = {"recording": REC, "busy": BUSY, "done": OK, "error": ERR}


class Overlay(QWidget):
    def __init__(self, corner="bottom-left"):
        super().__init__(None)
        self.corner = corner
        self.state = "idle"
        self.message = ""
        self.levels = [0.0] * BARS
        self.seconds = 0.0
        self._phase = 0.0

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.resize(MIN_WIDTH, HEIGHT)

        self._anim = QTimer(self)
        self._anim.setInterval(33)
        self._anim.timeout.connect(self._tick)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    # ---- public API --------------------------------------------------

    def show_recording(self):
        self.state = "recording"
        self.message = ""
        self.seconds = 0.0
        self.levels = [0.0] * BARS
        self._hide_timer.stop()
        self._appear()

    def show_busy(self, message):
        self.state = "busy"
        self.message = message
        self._hide_timer.stop()
        self._appear()

    def show_done(self, message="", msec=1100):
        self.state = "done"
        self.message = message
        self._appear()
        self._hide_timer.start(msec)

    def show_error(self, message, msec=6000):
        self.state = "error"
        self.message = message
        self._appear()
        self._hide_timer.start(msec)

    def dismiss(self):
        self._anim.stop()
        self._hide_timer.stop()
        self.hide()

    def push_level(self, level):
        self.levels = self.levels[1:] + [level]

    def set_seconds(self, seconds):
        self.seconds = seconds

    # ---- internals -----------------------------------------------------

    def _appear(self):
        self._resize_to_content()
        self._reposition()
        if not self.isVisible():
            self.show()
        self.raise_()
        if not self._anim.isActive():
            self._anim.start()

    def _resize_to_content(self):
        if self.state == "recording":
            width = MIN_WIDTH
        else:
            metrics = QFontMetrics(self._label_font())
            width = max(MIN_WIDTH, min(MAX_WIDTH, metrics.horizontalAdvance(self.message) + 76))
        self.resize(width, HEIGHT)

    def _reposition(self):
        # On a multi-monitor setup, show up where the user actually is.
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        left = "left" in self.corner
        top = "top" in self.corner
        x = area.left() + MARGIN if left else area.right() - self.width() - MARGIN
        y = area.top() + MARGIN if top else area.bottom() - self.height() - MARGIN
        self.move(int(x), int(y))

    def _tick(self):
        self._phase += 0.12
        if self.state == "recording":
            # keep the ribbon moving even through a pause in speech
            self.levels = self.levels[1:] + [self.levels[-1] * 0.72]
        self.update()

    def _label_font(self):
        font = QFont(self.font())
        font.setPointSizeF(10.5)
        return font

    # ---- painting --------------------------------------------------

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)

        path = QPainterPath()
        path.addRoundedRect(rect, 15, 15)
        painter.fillPath(path, BG)
        painter.setPen(QPen(BORDER, 1))
        painter.drawPath(path)

        accent = STATE_COLORS.get(self.state, MUTED)
        self._draw_indicator(painter, accent)

        if self.state == "recording":
            self._draw_waveform(painter)
            self._draw_time(painter)
        else:
            self._draw_message(painter)

    def _draw_indicator(self, painter, accent):
        cx, cy = 26.0, self.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        if self.state == "recording":
            pulse = 0.62 + 0.38 * (0.5 + 0.5 * math.sin(self._phase * 1.6))
            glow = QColor(accent)
            glow.setAlphaF(0.22 * pulse)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(cx, cy), 13 * pulse, 13 * pulse)
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(cx, cy), 5.5, 5.5)
        elif self.state == "busy":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QColor(accent), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            span = 100 * 16
            start = int(-self._phase * 320) % (360 * 16)
            painter.drawArc(QRectF(cx - 8, cy - 8, 16, 16), start, span)
        elif self.state == "done":
            pen = QPen(accent, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                QPointF(cx - 7, cy), QPointF(cx - 2, cy + 5.5), QPointF(cx + 7.5, cy - 6)
            )
        else:  # error
            pen = QPen(accent, 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(cx - 6, cy - 6), QPointF(cx + 6, cy + 6))
            painter.drawLine(QPointF(cx + 6, cy - 6), QPointF(cx - 6, cy + 6))

    def _draw_waveform(self, painter):
        left, right = 46.0, self.width() - 58.0
        span = right - left
        bar_w = 2.6
        gap = (span - BARS * bar_w) / max(1, BARS - 1)
        mid = self.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        for i, level in enumerate(self.levels):
            shaped = min(1.0, level ** 0.55)
            h = 3.0 + shaped * 26.0
            x = left + i * (bar_w + gap)
            color = QColor(REC if shaped > 0.04 else MUTED)
            color.setAlphaF(0.35 + 0.65 * min(1.0, shaped * 2.2))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, mid - h / 2, bar_w, h), 1.3, 1.3)

    def _draw_time(self, painter):
        font = QFont(self.font())
        font.setPointSizeF(10.0)
        font.setFamilies(["monospace"])
        painter.setFont(font)
        painter.setPen(MUTED)
        mins, secs = divmod(int(self.seconds), 60)
        painter.drawText(
            QRectF(self.width() - 56, 0, 44, self.height()),
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
            f"{mins}:{secs:02d}",
        )

    def _draw_message(self, painter):
        painter.setFont(self._label_font())
        painter.setPen(TEXT if self.state != "error" else ERR)
        box = QRectF(46, 0, self.width() - 60, self.height())
        metrics = QFontMetrics(self._label_font())
        text = metrics.elidedText(self.message, Qt.TextElideMode.ElideRight, int(box.width()))
        painter.drawText(
            box, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), text
        )
