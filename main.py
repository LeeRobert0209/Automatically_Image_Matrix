import sys
import os
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QListWidget, QLabel, 
                             QMessageBox, QAbstractItemView, QRadioButton, QButtonGroup,
                             QSlider, QGroupBox, QLineEdit)
from PyQt6.QtCore import Qt, QMimeData, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIntValidator

from sorter import sort_files
from stitcher import stitch_images

class StitcherThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, image_paths, output_dir, split_count, target_width):
        super().__init__()
        self.image_paths = image_paths
        self.output_dir = output_dir
        self.split_count = split_count
        self.target_width = target_width

    def run(self):
        try:
            success, message = stitch_images(self.image_paths, self.output_dir, self.split_count, self.target_width)
            self.finished_signal.emit(success, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class ImageStitcherApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("自动图片拼接工具 (Image Stitcher)")
        self.setGeometry(100, 100, 600, 650)
        self.image_paths = []
        self.stitch_thread = None

        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Drop Area Label
        self.drop_label = QLabel("请将图片拖拽到此处\n(支持 .jpg, .jpeg, .png)")
        self.drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                padding: 20px;
                font-size: 16px;
                color: #555;
                background-color: #f9f9f9;
            }
        """)
        layout.addWidget(self.drop_label)

        # List Widget
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.list_widget)

        # --- Controls Area ---
        controls_layout = QVBoxLayout()
        
        # 1. Size Selection
        size_group = QGroupBox("导出宽度选择")
        size_layout = QHBoxLayout()
        
        self.radio_original = QRadioButton("原图尺寸 (默认)")
        self.radio_750 = QRadioButton("宽度 750px")
        self.radio_1080 = QRadioButton("宽度 1080px")
        
        self.radio_original.setChecked(True)

        self.radio_custom = QRadioButton("自定义")
        self.custom_width_input = QLineEdit()
        self.custom_width_input.setPlaceholderText("输入宽度")
        self.custom_width_input.setValidator(QIntValidator(1, 20000)) # Limit to reasonable width
        self.custom_width_input.setFixedWidth(80)
        self.custom_width_input.setEnabled(False) # Default disabled
        
        # Connect signal to enable/disable input
        self.radio_custom.toggled.connect(lambda checked: self.custom_width_input.setEnabled(checked))
        
        self.size_btn_group = QButtonGroup()
        self.size_btn_group.addButton(self.radio_original)
        self.size_btn_group.addButton(self.radio_750)
        self.size_btn_group.addButton(self.radio_1080)
        self.size_btn_group.addButton(self.radio_custom)
        
        size_layout.addWidget(self.radio_original)
        size_layout.addWidget(self.radio_750)
        size_layout.addWidget(self.radio_1080)
        size_layout.addWidget(self.radio_custom)
        size_layout.addWidget(self.custom_width_input)
        size_group.setLayout(size_layout)
        controls_layout.addWidget(size_group)

        # 2. Split Slider
        split_group = QGroupBox("分组拼接设置")
        split_layout = QVBoxLayout()
        
        self.split_label = QLabel("拼接成：1 张长图")
        self.split_slider = QSlider(Qt.Orientation.Horizontal)
        self.split_slider.setMinimum(1)
        self.split_slider.setMaximum(1) # Will update dynamically
        self.split_slider.setValue(1)
        self.split_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.split_slider.setTickInterval(1)
        self.split_slider.valueChanged.connect(self.update_split_label)
        
        split_layout.addWidget(self.split_label)
        split_layout.addWidget(self.split_slider)
        split_group.setLayout(split_layout)
        controls_layout.addWidget(split_group)

        layout.addLayout(controls_layout)

        # Buttons Layout
        btn_layout = QHBoxLayout()
        
        self.clear_btn = QPushButton("清空列表")
        self.clear_btn.clicked.connect(self.clear_list)
        btn_layout.addWidget(self.clear_btn)

        self.stitch_btn = QPushButton("开始拼接并保存到桌面")
        self.stitch_btn.clicked.connect(self.start_stitching)
        self.stitch_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        btn_layout.addWidget(self.stitch_btn)

        layout.addLayout(btn_layout)

        # Enable Drag & Drop
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        valid_extensions = ('.jpg', '.jpeg', '.png')
        new_images = [f for f in files if f.lower().endswith(valid_extensions)]

        if new_images:
            # Combine with existing, remove duplicates, and sort
            combined_set = set(self.image_paths + new_images)
            # Re-sort everything
            self.image_paths = sort_files(list(combined_set))
            self.update_list_widget()
            
            # Update slider maximum
            count = len(self.image_paths)
            self.split_slider.setMaximum(max(1, count))
            
        else:
            QMessageBox.warning(self, "无效文件", "请只拖入图片文件 (.jpg, .png)")

    def update_list_widget(self):
        self.list_widget.clear()
        for path in self.image_paths:
            self.list_widget.addItem(os.path.basename(path))

    def update_split_label(self, value):
        self.split_label.setText(f"拼接成：{value} 张图")

    def clear_list(self):
        self.image_paths = []
        self.list_widget.clear()
        self.split_slider.setMaximum(1)
        self.split_slider.setValue(1)

    def start_stitching(self):
        if not self.image_paths:
            QMessageBox.warning(self, "提示", "请先添加图片！")
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        
        # Get settings
        split_count = self.split_slider.value()
        
        target_width = None
        if self.radio_750.isChecked():
            target_width = 750
        elif self.radio_1080.isChecked():
            target_width = 1080
        elif self.radio_custom.isChecked():
            try:
                val_text = self.custom_width_input.text().strip()
                if not val_text:
                    raise ValueError("Empty input")
                target_width = int(val_text)
                if target_width <= 0:
                    raise ValueError("Width must be positive")
            except ValueError:
                QMessageBox.warning(self, "输入错误", "请输入有效的数字宽度（像素）！")
                return

        self.stitch_btn.setEnabled(False)
        self.stitch_btn.setText("正在拼接... (请稍候)")
        
        # Start Thread
        self.stitch_thread = StitcherThread(self.image_paths, desktop_path, split_count, target_width)
        self.stitch_thread.finished_signal.connect(lambda s, m: self.on_stitching_finished(s, m))
        self.stitch_thread.start()

    def on_stitching_finished(self, success, message):
        self.stitch_btn.setEnabled(True)
        self.stitch_btn.setText("开始拼接并保存到桌面")

        if success:
            QMessageBox.information(self, "成功", f"{message}\n已保存到桌面。")
        else:
            QMessageBox.critical(self, "错误", f"拼接失败：\n{message}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageStitcherApp()
    window.show()
    sys.exit(app.exec())
