"""Load activity-analysis JSONL files and display bidirectional visibility pies."""
from dataclasses import dataclass
import json
import math
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QSizePolicy, QVBoxLayout, QWidget)


@dataclass(frozen=True)
class VisibilityDuration:
    visible_s: float
    invisible_s: float
    excluded_invalid_s: float

    @property
    def usable_s(self):
        return self.visible_s + self.invisible_s


@dataclass(frozen=True)
class VisibilityReport:
    a_sees_b: VisibilityDuration
    b_sees_a: VisibilityDuration
    segment_count: int


def _duration(record, key, line_number):
    direction = record.get(key)
    if not isinstance(direction, dict):
        raise ValueError(f'Line {line_number}: missing {key}.')
    values = []
    for field in ('visible_duration_s', 'usable_duration_s', 'excluded_invalid_duration_s'):
        value = direction.get(field)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f'Line {line_number}: invalid {key}.{field}.')
        values.append(float(value))
    visible, usable, excluded = values
    if visible > usable + 1e-9:
        raise ValueError(f'Line {line_number}: visible duration exceeds usable duration.')
    return visible, max(0., usable-visible), excluded


def load_visibility_report(path):
    """Aggregate visibility durations from an activity-eyeglow-v1 JSONL file."""
    path = Path(path)
    totals = {key: [0., 0., 0.] for key in
              ('a_sees_b_eyeglow', 'b_sees_a_eyeglow')}
    metadata_seen = False
    segment_count = 0
    try:
        stream = path.open(encoding='utf-8')
    except OSError as exc:
        raise ValueError(f'Could not open {path.name}: {exc}') from exc
    with stream:
        for line_number, line in enumerate(stream, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Line {line_number}: invalid JSON.') from exc
            if not isinstance(record, dict):
                raise ValueError(f'Line {line_number}: expected a JSON object.')
            record_type = record.get('record_type')
            if line_number == 1:
                if (record_type != 'metadata' or record.get('schema_version') != 1
                        or record.get('analysis_version') != 'activity-eyeglow-v1'):
                    raise ValueError('This is not a supported activity-analysis JSONL file.')
                metadata_seen = True
                continue
            if record_type != 'segment':
                raise ValueError(f'Line {line_number}: expected a segment record.')
            for key in totals:
                values = _duration(record, key, line_number)
                totals[key] = [a+b for a, b in zip(totals[key], values)]
            segment_count += 1
    if not metadata_seen:
        raise ValueError('The selected file is empty.')
    if not segment_count:
        raise ValueError('The analysis contains no activity segments.')
    def result(key):
        return VisibilityDuration(*totals[key])
    return VisibilityReport(result('a_sees_b_eyeglow'), result('b_sees_a_eyeglow'),
                            segment_count)


def _seconds(value):
    return f'{value:,.2f} s'


class PieChart(QWidget):
    VISIBLE = QColor('#24a148')
    INVISIBLE = QColor('#9da3ae')

    def __init__(self, title, subject, duration, parent=None):
        super().__init__(parent)
        self.title = title
        self.subject = subject
        self.duration = duration
        self.setMinimumSize(260, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(title)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(self.palette().color(self.foregroundRole()))
        title_rect = QRectF(8, 8, self.width()-16, 28)
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.title)
        font.setBold(False)
        painter.setFont(font)

        diameter = min(self.width()-48, self.height()-140, 190)
        pie = QRectF((self.width()-diameter)/2, 45, diameter, diameter)
        usable = self.duration.usable_s
        painter.setPen(QPen(self.palette().color(self.foregroundRole()), 1))
        if usable:
            visible_span = round(5760 * self.duration.visible_s / usable)
            painter.setBrush(self.VISIBLE)
            painter.drawPie(pie, 90*16, -visible_span)
            painter.setBrush(self.INVISIBLE)
            painter.drawPie(pie, 90*16-visible_span, -(5760-visible_span))
            percent = 100*self.duration.visible_s/usable
            painter.drawText(pie, Qt.AlignmentFlag.AlignCenter, f'{percent:.1f}%\nvisible')
        else:
            painter.setBrush(self.INVISIBLE)
            painter.drawEllipse(pie)
            painter.drawText(pie, Qt.AlignmentFlag.AlignCenter, 'No usable\ndata')

        y = pie.bottom() + 18
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.VISIBLE)
        painter.drawRect(18, int(y), 14, 14)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(40, int(y)-2, self.width()-48, 20,
                         Qt.AlignmentFlag.AlignVCenter,
                         f"Visible: {_seconds(self.duration.visible_s)}")
        y += 24
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.INVISIBLE)
        painter.drawRect(18, int(y), 14, 14)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.drawText(40, int(y)-2, self.width()-48, 20,
                         Qt.AlignmentFlag.AlignVCenter,
                         f"Invisible: {_seconds(self.duration.invisible_s)}")
        y += 28
        painter.drawText(18, int(y), self.width()-36, 36,
                         Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                         f"Excluded invalid/untrackable time: "
                         f"{_seconds(self.duration.excluded_invalid_s)}")


class VisibilityReportDialog(QDialog):
    def __init__(self, report, filename, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Analyze visibility')
        self.setModal(True)
        self.resize(650, 430)
        layout = QVBoxLayout(self)
        heading = QLabel(f'{Path(filename).name} · {report.segment_count} activity segments')
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(heading)
        charts = QHBoxLayout()
        self.chart_a = PieChart("Person A: B's EyeGlow", 'A', report.a_sees_b, self)
        self.chart_b = PieChart("Person B: A's EyeGlow", 'B', report.b_sees_a, self)
        charts.addWidget(self.chart_a)
        charts.addWidget(self.chart_b)
        layout.addLayout(charts, 1)
        note = QLabel('Invisible time includes usable analyzed time with no visible eye glow. '
                      'Invalid or untrackable time is excluded from both pie charts.')
        note.setWordWrap(True)
        note.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
