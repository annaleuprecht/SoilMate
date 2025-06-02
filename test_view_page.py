from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from pyqtgraph import PlotWidget, plot
import pyqtgraph as pg
from PyQt5.QtCore import QTimer
import time

class TestViewPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        self.setLayout(layout)

        self.graph_label = QLabel("Live Graph: Time vs. Pore Pressure")
        layout.addWidget(self.graph_label)

        self.start_time = time.time()
        self.times = []
        self.pressures = []

        self.graph = PlotWidget()
        self.graph.setLabel('left', 'Pore Pressure', units='kPa')
        self.graph.setLabel('bottom', 'Time', units='s')
        self.plot = self.graph.plot(pen=pg.mkPen('b', width=2))
        layout.addWidget(self.graph)

        self.timer = QTimer()
        self.timer.timeout.connect(self.simulate_idle_plot)
        self.timer.start(1000)  # Update every second with dummy data

    def simulate_idle_plot(self):
        if len(self.times) == 0 or self.times[-1] - self.times[0] < 10:
            elapsed = time.time() - self.start_time
            self.times.append(elapsed)
            self.pressures.append(0)  # Flatline idle plot
            self.plot.setData(self.times, self.pressures)

    def update_plot(self, reading):
        if not isinstance(reading, dict):
            return
        elapsed = time.time() - self.start_time
        self.times.append(elapsed)
        self.pressures.append(reading.get('pore_pressure', 0))
        self.plot.setData(self.times, self.pressures)
