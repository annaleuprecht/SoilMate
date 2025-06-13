from PyQt5.QtCore import QTimer
import time
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QHBoxLayout, QStackedLayout, QLabel, QComboBox, QPushButton, QTabWidget, QGridLayout, QSizePolicy, QScrollArea
)
from pyqtgraph import PlotWidget
import pyqtgraph as pg
import math

class GraphWidget(QWidget):
    def __init__(self, parent, x_options, y_options, shared_data):
        super().__init__()
        self.parent = parent
        self.shared_data = shared_data

        self.current_x = "Time since test start"
        self.current_y = "Pore Pressure"
        self.times = []
        self.values = []

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        self.setLayout(layout)
        self.setMinimumWidth(400)   # optional, to help with alignment

        # Initial size for grid view, will be overridden in switch_view_mode
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # --- Control Row ---
        controls = QHBoxLayout()
        controls.setSpacing(10)

        self.x_combo = QComboBox()
        self.x_combo.addItems(x_options)
        self.x_combo.setCurrentText(self.current_x)
        self.x_combo.currentTextChanged.connect(self.set_x_axis)

        self.y_combo = QComboBox()
        self.y_combo.addItems(y_options)
        self.y_combo.setCurrentText(self.current_y)
        self.y_combo.currentTextChanged.connect(self.set_y_axis)

        controls.addWidget(QLabel("X:"))
        controls.addWidget(self.x_combo)
        controls.addSpacing(20)
        controls.addWidget(QLabel("Y:"))
        controls.addWidget(self.y_combo)
        controls.addStretch()

        # ✕ button
        remove_btn = QPushButton("❌")
        remove_btn.setFixedSize(36, 36)
        remove_btn.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #d0d0d0;
                border-color: #999;
            }
        """)
        remove_btn.clicked.connect(lambda: self.parent.remove_graph(self))
        controls.addWidget(remove_btn)

        layout.addLayout(controls)

        # --- Graph ---
        self.graph = PlotWidget()
        self.graph.showGrid(x=True, y=True)
        self.plot = self.graph.plot(pen=pg.mkPen('g', width=2))
        layout.addWidget(self.graph)

        self.set_labels()

    def set_x_axis(self, text):
        self.current_x = text
        self.set_labels()

    def set_y_axis(self, text):
        self.current_y = text
        self.set_labels()

    def set_labels(self):
        self.graph.setLabel("bottom", self.current_x, units="s" if "time" in self.current_x.lower() else "")
        self.graph.setLabel("left", self.current_y, units="kPa" if "pressure" in self.current_y.lower() else "")

    def update(self, elapsed_time, reading):
        self.y_data_key = self.current_y.lower().replace(" ", "_")

        # --- Y Axis ---
        self.values.append(reading.get(self.y_data_key, 0))

        # --- X Axis ---
        if self.current_x == "Time since test start":
            x_val = elapsed_time
        elif self.current_x == "Time since stage start":
            x_val = reading.get("time_since_stage_start", 0)
        elif self.current_x == "√(Time since stage start)":
            raw = reading.get("time_since_stage_start", 0)
            x_val = math.sqrt(raw) if raw >= 0 else 0
        elif self.current_x == "log₁₀(Time since stage start)":
            raw = reading.get("time_since_stage_start", 0)
            x_val = math.log10(raw) if raw > 0 else 0
        elif self.current_x == "Axial Displacement":
            x_val = reading.get("axial_displacement", 0)
        elif self.current_x == "Axial Strain":
            disp = reading.get("axial_displacement", 0)
            height = reading.get("initial_height_mm", 1)
            x_val = disp / height
        else:
            x_val = elapsed_time

        self.times.append(x_val)
        self.plot.setData(self.times, self.values)

class TestViewPage(QWidget):
    def __init__(self):
        super().__init__()
        self.start_time = time.time()
        self.graphs = []

        self.shared_data = {}
        self.x_axis_options = [
            "Time since test start",
            "Time since stage start",
            "√(Time since stage start)",
            "log₁₀(Time since stage start)",
            "Axial Displacement",
            "Axial Strain"
        ]

        self.y_axis_options = [
            "Pore Pressure", "Axial Displacement", "Axial Load",
            "Local Axial 1 (mV)", "Local Axial 2 (mV)", "Local Radial (mV)"
        ]

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- Header ---
        title = QLabel("Test View")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        main_layout.addWidget(title)

        subtitle = QLabel("Use the dropdown below to switch view mode and press '+ Add Graph' to start plotting live data.")
        subtitle.setStyleSheet("color: gray; margin-bottom: 12px;")
        main_layout.addWidget(subtitle)

        # Create controls before styling
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Grid View", "Tabbed View"])
        self.view_mode_combo.currentTextChanged.connect(self.switch_view_mode)

        self.add_graph_button = QPushButton("+ Add Graph")
        self.add_graph_button.clicked.connect(self.add_graph)

        self.reset_layout_button = QPushButton("🔄 Reset Layout")
        self.reset_layout_button.clicked.connect(self.reposition_grid_graphs)

        # --- Styled Top Control Section ---
        control_frame = QFrame()
        control_frame.setStyleSheet("""
            QFrame {
                background-color: #f9f9f9;
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 6px;
            }
        """)
        control_layout = QHBoxLayout(control_frame)
        control_layout.addWidget(QLabel("View Mode:"))
        control_layout.addWidget(self.view_mode_combo)
        control_layout.addStretch()
        control_layout.addWidget(self.add_graph_button)
        control_layout.addWidget(self.reset_layout_button)

        main_layout.addWidget(control_frame)

        # Grid view scrollable container
        self.graph_grid_widget = QWidget()
        self.graph_grid_layout = QGridLayout(self.graph_grid_widget)
        self.graph_grid_layout.setSpacing(20)

        self.grid_scroll_area = QScrollArea()
        self.grid_scroll_area.setWidgetResizable(True)
        self.grid_scroll_area.setWidget(self.graph_grid_widget)

        # Tab view
        self.graph_tab_widget = QTabWidget()
        self.graph_tab_widget.hide()
        
        self.grid_scroll_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graph_tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.stacked_layout = QStackedLayout()
        self.stacked_layout.addWidget(self.grid_scroll_area)
        self.stacked_layout.addWidget(self.graph_tab_widget)
        main_layout.addLayout(self.stacked_layout, stretch=1)

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all_graphs)
        self.timer.start(1000)

    def reposition_grid_graphs(self):
        # Clear layout
        while self.graph_grid_layout.count():
            item = self.graph_grid_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Ensure equal spacing
        self.graph_grid_layout.setColumnStretch(0, 1)
        self.graph_grid_layout.setColumnStretch(1, 1)

        # Add graphs
        i = 0
        total = len(self.graphs)
        while i < total:
            row = i // 2
            if i == total - 1 and total % 2 == 1:
                self.graph_grid_layout.addWidget(self.graphs[i], row, 0, 1, 2)
                i += 1
            else:
                self.graph_grid_layout.addWidget(self.graphs[i], row, 0)
                self.graph_grid_layout.addWidget(self.graphs[i + 1], row, 1)
                i += 2

    def add_graph(self):
        graph = GraphWidget(
            parent=self,
            x_options=self.x_axis_options,
            y_options=self.y_axis_options,
            shared_data=self.shared_data
        )
        self.graphs.append(graph)

        if self.view_mode_combo.currentText() == "Grid View":
            graph.setParent(self.graph_grid_widget)
            graph.show()  # 🔥 This is key
            self.reposition_grid_graphs()
        else:
            graph.setParent(self.graph_tab_widget)
            graph.show()  # 🔥 Needed here too
            self.graph_tab_widget.addTab(graph, f"Graph {len(self.graphs)}")

    def remove_graph(self, graph):
        if graph in self.graphs:
            self.graphs.remove(graph)
            graph.setParent(None)
            graph.deleteLater()

            if self.view_mode_combo.currentText() == "Grid View":
                self.reposition_grid_graphs()
            else:
                self.graph_tab_widget.clear()
                for i, g in enumerate(self.graphs):
                    self.graph_tab_widget.addTab(g, f"Graph {i+1}")

    def display_graph(self, graph):
        # Always remove from both layouts first to avoid duplication glitches
        graph.setParent(None)

        if self.view_mode_combo.currentText() == "Grid View":
            graph.setParent(self.graph_grid_widget)
            self.reposition_grid_graphs()
        else:
            graph.setParent(self.graph_tab_widget)
            self.graph_tab_widget.addTab(graph, f"Graph {len(self.graphs)}")


    def update_plot(self, reading):
        elapsed = time.time() - self.start_time
        for graph in self.graphs:
            graph.update(elapsed, reading)

    def update_all_graphs(self):
        elapsed = time.time() - self.start_time
        for graph in self.graphs:
            graph.update(elapsed, self.shared_data)

    def switch_view_mode(self, mode):
        if mode == "Grid View":
            self.stacked_layout.setCurrentWidget(self.grid_scroll_area)

            self.graph_tab_widget.clear()

            for graph in self.graphs:
                graph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                graph.setFixedHeight(250)
                graph.setParent(self.graph_grid_widget)  # 👈 Reparent to the grid
                graph.show()                             # 👈 Ensure visibility

            self.reposition_grid_graphs()

        else:  # Tabbed View
            self.stacked_layout.setCurrentWidget(self.graph_tab_widget)

            self.graph_tab_widget.clear()

            for graph in self.graphs:
                graph.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                graph.setMinimumHeight(400)
                graph.setParent(self.graph_tab_widget)  # 👈 Reparent to tab widget
                graph.show()                            # 👈 Ensure visibility
                self.graph_tab_widget.addTab(graph, f"Graph {self.graphs.index(graph)+1}")

