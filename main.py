import sys
import os
import re
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QListWidget, QLabel, 
                             QMessageBox, QAbstractItemView, QRadioButton, QButtonGroup,
                             QSlider, QGroupBox, QLineEdit, QTabWidget, QCheckBox, QSizePolicy)
from PyQt6.QtCore import Qt, QMimeData, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIntValidator, QIcon

from sorter import sort_files
from stitcher import stitch_images
from grid_preview import PreviewDialog
from slicer import slice_image, slice_grid_image
from merger import merge_images_to_pdf
from converter import convert_pdf_to_images, convert_psd_to_images, convert_ppt_to_images
from PyQt6.QtGui import QPixmap, QCursor
from PyQt6.QtCore import QTimer, QPoint

class PreviewListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self.show_preview)
        self.hover_item = None
        self.preview_label = None
        
        self.itemEntered.connect(self.on_item_entered)
        # We need to detect when mouse leaves item to stop timer
        # itemEntered triggers when mouse MOVES onto an item.
        
    def on_item_entered(self, item):
        self.hide_preview() # Hide previous if any
        self.hover_item = item
        self.preview_timer.start(2000) # 2 seconds
        
    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        # If we moved, we might need to reset or check if we are still on same item?
        # itemEntered handles switching items.
        # But if we move OUT of an item to whitespace?
        item = self.itemAt(event.pos())
        if item != self.hover_item:
            self.hover_item = item
            self.hide_preview()
            self.preview_timer.stop()
            if item:
                self.preview_timer.start(2000)
    
    def leaveEvent(self, event):
        self.hide_preview()
        self.preview_timer.stop()
        self.hover_item = None
        super().leaveEvent(event)
        
    def show_preview(self):
        if not self.hover_item:
            return
            
        path = self.hover_item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            return
            
        # Create Popup
        if self.preview_label is None:
            self.preview_label = QLabel(self, windowFlags=Qt.WindowType.ToolTip)
            self.preview_label.setStyleSheet("border: 2px solid #333; background: white;")
            self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Load and scale image
        try:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(200, 200, Qt.AspectRatioMode.KeepAspectRatio)
                self.preview_label.setPixmap(scaled)
                self.preview_label.adjustSize()
                
                # Position near cursor
                pos = QCursor.pos()
                self.preview_label.move(pos.x() + 20, pos.y() + 20)
                self.preview_label.show()
        except Exception:
            pass

    def hide_preview(self):
        if self.preview_label:
            self.preview_label.hide()

class StitcherThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, image_paths, output_dir, split_count, target_width, max_kb, mode='vertical', rows=2, cols=2, output_format='AUTO', custom_name=None):
        super().__init__()
        self.image_paths = image_paths
        self.output_dir = output_dir
        self.split_count = split_count
        self.target_width = target_width
        self.max_kb = max_kb
        self.target_width = target_width
        self.max_kb = max_kb
        self.mode = mode
        self.rows = rows
        self.cols = cols
        self.output_format = output_format
        self.custom_name = custom_name

    def run(self):
        try:
            success, message = stitch_images(self.image_paths, self.output_dir, self.split_count, self.target_width, self.max_kb, self.mode, self.rows, self.cols, self.output_format, self.custom_name)
            self.finished_signal.emit(success, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class MergerThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, image_paths, output_path, max_kb):
        super().__init__()
        self.image_paths = image_paths
        self.output_path = output_path
        self.max_kb = max_kb

    def run(self):
        try:
            success, message = merge_images_to_pdf(self.image_paths, self.output_path, self.max_kb)
            self.finished_signal.emit(success, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class ConverterThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, file_paths, output_dir, output_format):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.output_format = output_format

    def run(self):
        success_count = 0
        fail_count = 0
        details = ""

        try:
            for path in self.file_paths:
                ext = os.path.splitext(path)[1].lower()
                res = False
                msg = ""
                
                if ext == '.pdf':
                    res, msg = convert_pdf_to_images(path, self.output_dir, self.output_format)
                elif ext == '.psd':
                    res, msg = convert_psd_to_images(path, self.output_dir, self.output_format)
                elif ext in ['.ppt', '.pptx']:
                    res, msg = convert_ppt_to_images(path, self.output_dir, self.output_format)
                else:
                    msg = "Unsupported format"
                
                if res:
                    success_count += 1
                    details += f"\n[成功] {os.path.basename(path)}: {msg}"
                else:
                    fail_count += 1
                    details += f"\n[失败] {os.path.basename(path)}: {msg}"

            final_msg = f"处理完成: 成功 {success_count} 个, 失败 {fail_count} 个。\n{details}"
            self.finished_signal.emit(fail_count == 0, final_msg)

        except Exception as e:
            self.finished_signal.emit(False, str(e))

class SlicerThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, image_paths, output_dir, count, smart_mode, target_width, max_kb, direction='horizontal', rows=None, cols=None, output_format='AUTO', custom_name=None):
        super().__init__()
        self.image_paths = image_paths
        self.output_dir = output_dir
        self.count = count
        self.smart_mode = smart_mode
        self.target_width = target_width
        self.max_kb = max_kb
        self.direction = direction
        self.rows = rows
        self.cols = cols
        self.output_format = output_format
        self.custom_name = custom_name

    def run(self):
        success = True
        message = ""
        try:
            for i, img_path in enumerate(self.image_paths):
                # Handle custom name for multiple files?
                # If custom name is "MyPic", multiple input files might conflict or need indexing.
                # Let's assume custom_name applies mainly to single file slicing or prefixing.
                # If multiple files, we probably should append index to folder name or similar.
                
                c_name = self.custom_name
                if c_name and len(self.image_paths) > 1:
                     c_name = f"{c_name}_{i+1}"
                     
                if self.direction == 'grid':
                    max_kb_val = self.max_kb if self.max_kb > 0 else None
                    s, m = slice_grid_image(img_path, self.output_dir, self.rows, self.cols, self.target_width, max_kb_val, self.output_format, c_name)
                else:
                    max_kb_val = self.max_kb if self.max_kb > 0 else None
                    s, m = slice_image(img_path, self.output_dir, self.count, self.smart_mode, self.target_width, max_kb_val, self.direction, self.output_format, c_name)
                
                if not s:
                    success = False
                    message += f"\nFailed {os.path.basename(img_path)}: {m}"
                else:
                    message += f"\nProcessed {os.path.basename(img_path)}: {m}"
            
            if success:
                message = "All images processed successfully!" + message
            else:
                message = "Some images failed." + message
                
            self.finished_signal.emit(success, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class ImageMatrixApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ImageMatrix (影像矩阵) - 拼图 & 切图工具")
        self.setGeometry(100, 100, 500, 600)
        
        # Data storage
        self.merge_images = []
        self.slice_images = []
        # Store full items in the widget for combine tab to support reordering
        # But we still need a list to track dropping? 
        # Actually for combine tab we update the widget directly with UserRole
        
        self.stitch_thread = None
        self.slicer_thread = None
        self.merger_thread = None
        self.converter_thread = None
        
        self.convert_files = []

        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Tabs
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Tab 1: Merge
        self.merge_tab = QWidget()
        self.init_merge_tab()
        self.tabs.addTab(self.merge_tab, "拼图 (Merge)")

        # Tab 2: Slice
        self.slice_tab = QWidget()
        self.init_slice_tab()
        self.tabs.addTab(self.slice_tab, "切图 (Slice)")

        # Tab 3: Combine
        self.combine_tab = QWidget()
        self.init_combine_tab()
        self.tabs.addTab(self.combine_tab, "合图 (Combine)")

        # Tab 4: Convert (Extract)
        self.convert_tab = QWidget()
        self.init_convert_tab()
        self.tabs.addTab(self.convert_tab, "导图 (Convert)")

        # Global Enable Drag & Drop
        self.setAcceptDrops(True)

    def init_merge_tab(self):
        layout = QVBoxLayout(self.merge_tab)

        # Drop Label
        self.merge_drop_label = QLabel("请将图片拖拽到此处\n(支持 .jpg, .jpeg, .png, .pdf)")
        self.merge_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.merge_drop_label.setStyleSheet(self._get_drop_style())
        layout.addWidget(self.merge_drop_label)

        # List Widget
        self.merge_list = QListWidget()
        self.merge_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.merge_list)

        # Controls
        controls_layout = QVBoxLayout()

        # Size Selection
        size_group = QGroupBox("导出宽度选择")
        size_group.setStyleSheet(self._get_group_style())
        size_layout = QHBoxLayout()
        
        self.m_radio_original = QRadioButton("原图")
        self.m_radio_750 = QRadioButton("750px")
        self.m_radio_1080 = QRadioButton("1080px")
        self.m_radio_original.setChecked(True)

        self.m_radio_custom = QRadioButton("自定义")
        self.m_custom_input = QLineEdit()
        self.m_custom_input.setPlaceholderText("宽度")
        self.m_custom_input.setValidator(QIntValidator(1, 20000))
        self.m_custom_input.setFixedWidth(60)
        self.m_custom_input.setEnabled(False)
        self.m_radio_custom.toggled.connect(lambda c: self.m_custom_input.setEnabled(c))
        
        m_size_btn_group = QButtonGroup(self.merge_tab)
        m_size_btn_group.addButton(self.m_radio_original)
        m_size_btn_group.addButton(self.m_radio_750)
        m_size_btn_group.addButton(self.m_radio_1080)
        m_size_btn_group.addButton(self.m_radio_custom)
        
        size_layout.addWidget(self.m_radio_original)
        size_layout.addWidget(self.m_radio_750)
        size_layout.addWidget(self.m_radio_1080)
        size_layout.addWidget(self.m_radio_custom)
        size_layout.addWidget(self.m_custom_input)
        size_group.setLayout(size_layout)
        controls_layout.addWidget(size_group)

        # Export Format Selection
        format_group = QGroupBox("导出格式")
        format_group.setStyleSheet(self._get_group_style())
        format_layout = QHBoxLayout()
        
        self.m_radio_fmt_auto = QRadioButton("自动 (默认)")
        self.m_radio_fmt_jpg = QRadioButton("JPG")
        self.m_radio_fmt_png = QRadioButton("PNG")
        self.m_radio_fmt_pdf = QRadioButton("PDF")
        self.m_radio_fmt_auto.setChecked(True)
        
        m_fmt_group = QButtonGroup(self.merge_tab)
        m_fmt_group.addButton(self.m_radio_fmt_auto)
        m_fmt_group.addButton(self.m_radio_fmt_jpg)
        m_fmt_group.addButton(self.m_radio_fmt_png)
        m_fmt_group.addButton(self.m_radio_fmt_pdf)
        
        format_layout.addWidget(self.m_radio_fmt_auto)
        format_layout.addWidget(self.m_radio_fmt_jpg)
        format_layout.addWidget(self.m_radio_fmt_png)
        format_layout.addWidget(self.m_radio_fmt_pdf)
        format_group.setLayout(format_layout)
        controls_layout.addWidget(format_group)

        # Mode Selection (New)
        mode_group = QGroupBox("拼接模式")
        mode_group.setStyleSheet(self._get_group_style())
        mode_layout = QVBoxLayout()
        
        mode_btn_layout = QHBoxLayout()
        self.m_radio_v = QRadioButton("垂直拼接 (默认)")
        self.m_radio_h = QRadioButton("水平拼接")
        self.m_radio_grid = QRadioButton("宫格拼接")
        self.m_radio_v.setChecked(True)
        
        m_mode_group = QButtonGroup(self.merge_tab)
        m_mode_group.addButton(self.m_radio_v)
        m_mode_group.addButton(self.m_radio_h)
        m_mode_group.addButton(self.m_radio_grid)
        
        mode_btn_layout.addWidget(self.m_radio_v)
        mode_btn_layout.addWidget(self.m_radio_h)
        mode_btn_layout.addWidget(self.m_radio_grid)
        mode_layout.addLayout(mode_btn_layout)
        
        # --- Grid UI for Merge ---
        self.m_grid_container = QWidget()
        self.m_grid_container.setVisible(False)
        grid_layout = QVBoxLayout(self.m_grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # Presets (Copied from Slice Tab Logic)
        presets_label = QLabel("快速预设:")
        grid_layout.addWidget(presets_label)
        
        # Row 1
        presets_layout = QHBoxLayout()
        presets = [("2x2", 2, 2), ("3x3", 3, 3), ("4x4", 4, 4), ("5x5", 5, 5)]
        for label, r, c in presets:
            btn = QPushButton(label)
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda checked, r=r, c=c: self.set_merge_grid_val(r, c))
            presets_layout.addWidget(btn)
        presets_layout.addStretch()
        grid_layout.addLayout(presets_layout)

        # Row 2
        presets_layout_2 = QHBoxLayout()
        presets2 = [("32x32", 32, 32), ("128x128", 128, 128), ("512x512", 512, 512), ("1024x1024", 1024, 1024)]
        for label, r, c in presets2:
            btn = QPushButton(label)
            width = 80 if "1024" in label else 65
            btn.setFixedWidth(width)
            btn.clicked.connect(lambda checked, r=r, c=c: self.set_merge_grid_val(r, c))
            presets_layout_2.addWidget(btn)
        presets_layout_2.addStretch()
        grid_layout.addLayout(presets_layout_2)

        # Custom Input
        custom_grid_layout = QHBoxLayout()
        custom_grid_layout.addWidget(QLabel("自定义:"))
        self.m_grid_rows = QLineEdit()
        self.m_grid_rows.setPlaceholderText("行")
        self.m_grid_rows.setValidator(QIntValidator(1, 5000))
        self.m_grid_cols = QLineEdit()
        self.m_grid_cols.setPlaceholderText("列")
        self.m_grid_cols.setValidator(QIntValidator(1, 5000))
        
        custom_grid_layout.addWidget(self.m_grid_rows)
        custom_grid_layout.addWidget(QLabel("x"))
        custom_grid_layout.addWidget(self.m_grid_cols)
        
        grid_layout.addLayout(custom_grid_layout)
        
        mode_layout.addWidget(self.m_grid_container)
        mode_group.setLayout(mode_layout)
        controls_layout.addWidget(mode_group)
        
        # Connect mode change
        self.m_radio_v.toggled.connect(self.update_merge_ui_text)
        self.m_radio_h.toggled.connect(self.update_merge_ui_text)
        self.m_radio_grid.toggled.connect(self.update_merge_ui_text)

        # File Size Limit Selection
        # File Size Limit Selection
        limit_group = QGroupBox("图片大小限制 (KB)")
        limit_group.setStyleSheet(self._get_group_style())
        limit_layout = QVBoxLayout()
        
        # New Limit UI with Radio Buttons
        self.m_radio_limit_preset = QRadioButton("预设: 150 KB")
        self.m_radio_limit_preset.setChecked(True)
        self.m_limit_slider = QSlider(Qt.Orientation.Horizontal)
        self.m_limit_slider.setMinimum(0)
        self.m_limit_slider.setMaximum(5) # 0:Unlimited, 1:150, 2:300, 3:500, 4:750, 5:1000
        self.m_limit_slider.setValue(1)
        self.m_limit_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.m_limit_slider.setTickInterval(1)
        self.m_limit_slider.valueChanged.connect(lambda v: self.update_limit_label(v, self.m_radio_limit_preset))
        
        # When slider interacts, auto-check preset radio
        self.m_limit_slider.sliderPressed.connect(lambda: self.m_radio_limit_preset.setChecked(True))
        
        self.m_radio_limit_custom = QRadioButton("自定义:")
        self.m_limit_custom_input = QLineEdit()
        self.m_limit_custom_input.setPlaceholderText("KB")
        self.m_limit_custom_input.setValidator(QIntValidator(1, 20000))
        self.m_limit_custom_input.setFixedWidth(60)
        self.m_limit_custom_input.setEnabled(False)
        self.m_radio_limit_custom.toggled.connect(lambda c: self.m_limit_custom_input.setEnabled(c))
        
        limit_btn_group = QButtonGroup(self.merge_tab)
        limit_btn_group.addButton(self.m_radio_limit_preset)
        limit_btn_group.addButton(self.m_radio_limit_custom)
        
        # Layout row 1: Radio + Slider
        row1 = QHBoxLayout()
        row1.addWidget(self.m_radio_limit_preset)
        row1.addWidget(self.m_limit_slider)
        
        # Layout row 2: Radio + Input
        row2 = QHBoxLayout()
        row2.addWidget(self.m_radio_limit_custom)
        row2.addWidget(self.m_limit_custom_input)
        row2.addStretch()
        
        limit_layout.addLayout(row1)
        limit_layout.addLayout(row2)
        limit_group.setLayout(limit_layout)
        controls_layout.addWidget(limit_group)

        # Split Selection
        self.m_split_group = QGroupBox("分组拼接设置")
        self.m_split_group.setStyleSheet(self._get_group_style())
        split_layout = QVBoxLayout()
        self.m_split_label = QLabel("拼接成：1 张长图")
        self.m_split_slider = QSlider(Qt.Orientation.Horizontal)
        self.m_split_slider.setMinimum(1)
        self.m_split_slider.setMaximum(1)
        self.m_split_slider.valueChanged.connect(lambda v: self.m_split_label.setText(f"拼接成：{v} 张图"))
        
        split_layout.addWidget(self.m_split_label)
        split_layout.addWidget(self.m_split_slider)
        self.m_split_group.setLayout(split_layout)
        controls_layout.addWidget(self.m_split_group)

        layout.addLayout(controls_layout)

        # Filename Input (New)
        name_group = QGroupBox("导出文件名 (选填)")
        name_group.setStyleSheet(self._get_group_style())
        name_layout = QHBoxLayout()
        self.m_name_input = QLineEdit()
        self.m_name_input.setPlaceholderText("默认为自动生成的日期时间戳")
        name_layout.addWidget(self.m_name_input)
        name_group.setLayout(name_layout)
        layout.addWidget(name_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.m_clear_btn = QPushButton("清空")
        self.m_clear_btn.clicked.connect(self.clear_merge_list)
        self.m_clear_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.m_clear_btn.setStyleSheet("padding: 10px;")
        btn_layout.addWidget(self.m_clear_btn)

        self.m_start_btn = QPushButton("开始拼接 (保存到桌面)")
        self.m_start_btn.clicked.connect(self.start_stitching)
        self.m_start_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.m_start_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px;")
        btn_layout.addWidget(self.m_start_btn)

        layout.addLayout(btn_layout)

    def init_slice_tab(self):
        layout = QVBoxLayout(self.slice_tab)

        # Drop Label
        self.slice_drop_label = QLabel("请将图片拖拽到此处")
        self.slice_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slice_drop_label.setStyleSheet(self._get_drop_style())
        layout.addWidget(self.slice_drop_label)

        # List Widget
        self.slice_list = QListWidget()
        layout.addWidget(self.slice_list)

        # Controls
        controls_layout = QVBoxLayout()

        # 1. Width Selection (Full Row)
        size_group = QGroupBox("导出宽度")
        size_group.setStyleSheet(self._get_group_style())
        size_layout = QHBoxLayout()
        
        self.s_radio_original = QRadioButton("原图")
        self.s_radio_custom = QRadioButton("指定")
        self.s_radio_original.setChecked(True)
        
        self.s_custom_input = QLineEdit()
        self.s_custom_input.setPlaceholderText("例如 750")
        self.s_custom_input.setValidator(QIntValidator(1, 20000))
        self.s_custom_input.setFixedWidth(60)
        self.s_custom_input.setEnabled(False)
        self.s_radio_custom.toggled.connect(lambda c: self.s_custom_input.setEnabled(c))

        s_size_btn_group = QButtonGroup(self.slice_tab)
        s_size_btn_group.addButton(self.s_radio_original)
        s_size_btn_group.addButton(self.s_radio_custom)

        size_layout.addWidget(self.s_radio_original)
        size_layout.addWidget(self.s_radio_custom)
        size_layout.addWidget(self.s_custom_input)
        size_layout.addStretch()
        size_group.setLayout(size_layout)
        controls_layout.addWidget(size_group)

        # 2. Export Format Selection (New)
        format_group = QGroupBox("导出格式")
        format_group.setStyleSheet(self._get_group_style())
        format_layout = QHBoxLayout()
        
        self.s_radio_fmt_auto = QRadioButton("自动 (默认)")
        self.s_radio_fmt_jpg = QRadioButton("JPG")
        self.s_radio_fmt_png = QRadioButton("PNG")
        self.s_radio_fmt_pdf = QRadioButton("PDF")
        self.s_radio_fmt_auto.setChecked(True)
        
        s_fmt_group = QButtonGroup(self.slice_tab)
        s_fmt_group.addButton(self.s_radio_fmt_auto)
        s_fmt_group.addButton(self.s_radio_fmt_jpg)
        s_fmt_group.addButton(self.s_radio_fmt_png)
        s_fmt_group.addButton(self.s_radio_fmt_pdf)
        
        format_layout.addWidget(self.s_radio_fmt_auto)
        format_layout.addWidget(self.s_radio_fmt_jpg)
        format_layout.addWidget(self.s_radio_fmt_png)
        format_layout.addWidget(self.s_radio_fmt_pdf)
        format_group.setLayout(format_layout)
        controls_layout.addWidget(format_group)

        # 2. Limit (Group Box style similar to Merge Tab)
        limit_group = QGroupBox("图片大小限制 (KB)")
        limit_group.setStyleSheet(self._get_group_style())
        limit_layout = QVBoxLayout()

        self.s_radio_limit_preset = QRadioButton("预设: 150 KB")
        self.s_radio_limit_preset.setChecked(True)
        self.s_limit_slider = QSlider(Qt.Orientation.Horizontal)
        self.s_limit_slider.setMinimum(0)
        self.s_limit_slider.setMaximum(5)
        self.s_limit_slider.setValue(1)
        self.s_limit_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.s_limit_slider.setTickInterval(1)
        self.s_limit_slider.valueChanged.connect(lambda v: self.update_limit_label(v, self.s_radio_limit_preset))
        self.s_limit_slider.sliderPressed.connect(lambda: self.s_radio_limit_preset.setChecked(True))

        self.s_radio_limit_custom = QRadioButton("自定义:")
        self.s_limit_custom_input = QLineEdit()
        self.s_limit_custom_input.setPlaceholderText("KB")
        self.s_limit_custom_input.setValidator(QIntValidator(1, 20000))
        self.s_limit_custom_input.setFixedWidth(60)
        self.s_limit_custom_input.setEnabled(False)
        self.s_radio_limit_custom.toggled.connect(lambda c: self.s_limit_custom_input.setEnabled(c))
        
        s_limit_btn_group = QButtonGroup(self.slice_tab)
        s_limit_btn_group.addButton(self.s_radio_limit_preset)
        s_limit_btn_group.addButton(self.s_radio_limit_custom)

        row1 = QHBoxLayout()
        row1.addWidget(self.s_radio_limit_preset)
        row1.addWidget(self.s_limit_slider)
        
        row2 = QHBoxLayout()
        row2.addWidget(self.s_radio_limit_custom)
        row2.addWidget(self.s_limit_custom_input)
        row2.addStretch()
        
        limit_layout.addLayout(row1)
        limit_layout.addLayout(row2)
        limit_group.setLayout(limit_layout)
        
        controls_layout.addWidget(limit_group)

        # 3. Settings Group
        slice_group = QGroupBox("切图模式 & 设置")
        slice_group.setStyleSheet(self._get_group_style())
        slice_inner_layout = QVBoxLayout()

        # Direction/Mode Selection
        dir_layout = QHBoxLayout()
        self.s_dir_label = QLabel("模式：")
        self.s_radio_h = QRadioButton("水平切")
        self.s_radio_v = QRadioButton("垂直切")
        self.s_radio_grid = QRadioButton("宫格 (Grid)")
        self.s_radio_h.setChecked(True)
        
        self.s_radio_h.toggled.connect(self.update_slice_ui_text)
        self.s_radio_v.toggled.connect(self.update_slice_ui_text)
        self.s_radio_grid.toggled.connect(self.update_slice_ui_text)
        
        dir_btn_group = QButtonGroup(self.slice_tab)
        dir_btn_group.addButton(self.s_radio_h)
        dir_btn_group.addButton(self.s_radio_v)
        dir_btn_group.addButton(self.s_radio_grid)
        
        dir_layout.addWidget(self.s_dir_label)
        dir_layout.addWidget(self.s_radio_h)
        dir_layout.addWidget(self.s_radio_v)
        dir_layout.addWidget(self.s_radio_grid)
        slice_inner_layout.addLayout(dir_layout)

        # --- Linear UI (Slider & Smart Check) ---
        self.s_linear_container = QWidget()
        linear_layout = QVBoxLayout(self.s_linear_container)
        linear_layout.setContentsMargins(0, 0, 0, 0)

        count_layout = QHBoxLayout()
        self.s_count_label = QLabel("切成：5 行")
        self.s_count_slider = QSlider(Qt.Orientation.Horizontal)
        self.s_count_slider.setMinimum(1)
        self.s_count_slider.setMaximum(50)
        self.s_count_slider.setValue(5)
        self.s_count_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.s_count_slider.setTickInterval(5)
        self.s_count_slider.valueChanged.connect(self.update_slice_ui_text)
        
        count_layout.addWidget(self.s_count_label)
        linear_layout.addLayout(count_layout)
        linear_layout.addWidget(self.s_count_slider)

        self.s_smart_check = QCheckBox("智能吸附 (避开内容)")
        self.s_smart_check.setChecked(True)
        linear_layout.addWidget(self.s_smart_check)
        
        slice_inner_layout.addWidget(self.s_linear_container)

        # --- Grid UI ---
        self.s_grid_container = QWidget()
        self.s_grid_container.setVisible(False)
        grid_layout = QVBoxLayout(self.s_grid_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        
        # Presets
        presets_label = QLabel("快速预设:")
        grid_layout.addWidget(presets_label)
        
        # Row 1: 2x2, 3x3, 4x4, 5x5
        presets_layout = QHBoxLayout()
        presets = [("2x2", 2, 2), ("3x3", 3, 3), ("4x4", 4, 4), ("5x5", 5, 5)]
        for label, r, c in presets:
            btn = QPushButton(label)
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda checked, r=r, c=c: self.set_grid_val(r, c))
            presets_layout.addWidget(btn)
        presets_layout.addStretch()
        grid_layout.addLayout(presets_layout)

        # Row 2: 32x32, 128x128, 512x512, 1024x1024
        presets_layout_2 = QHBoxLayout()
        presets2 = [("32x32", 32, 32), ("128x128", 128, 128), ("512x512", 512, 512), ("1024x1024", 1024, 1024)]
        for label, r, c in presets2:
            btn = QPushButton(label)
            # Adjust width slightly for longer text
            width = 80 if "1024" in label else 65
            btn.setFixedWidth(width)
            btn.clicked.connect(lambda checked, r=r, c=c: self.set_grid_val(r, c))
            presets_layout_2.addWidget(btn)
        presets_layout_2.addStretch()
        grid_layout.addLayout(presets_layout_2)

        # Custom Input
        custom_grid_layout = QHBoxLayout()
        custom_grid_layout.addWidget(QLabel("自定义:"))
        self.s_grid_rows = QLineEdit()
        self.s_grid_rows.setPlaceholderText("行(Rows)")
        self.s_grid_rows.setValidator(QIntValidator(1, 5000))
        self.s_grid_cols = QLineEdit()
        self.s_grid_cols.setPlaceholderText("列(Cols)")
        self.s_grid_cols.setValidator(QIntValidator(1, 5000))
        
        custom_grid_layout.addWidget(self.s_grid_rows)
        custom_grid_layout.addWidget(QLabel("x"))
        custom_grid_layout.addWidget(self.s_grid_cols)
        
        self.s_preview_btn = QPushButton("预览效果")
        self.s_preview_btn.clicked.connect(self.preview_grid)
        custom_grid_layout.addWidget(self.s_preview_btn)
        
        grid_layout.addLayout(custom_grid_layout)
        
        slice_inner_layout.addWidget(self.s_grid_container)

        slice_group.setLayout(slice_inner_layout)
        controls_layout.addWidget(slice_group)

        layout.addLayout(controls_layout)

        # Filename Input (New)
        name_group = QGroupBox("导出文件名 (选填)")
        name_group.setStyleSheet(self._get_group_style())
        name_layout = QHBoxLayout()
        self.s_name_input = QLineEdit()
        self.s_name_input.setPlaceholderText("默认为文件夹/原图名")
        name_layout.addWidget(self.s_name_input)
        name_group.setLayout(name_layout)
        layout.addWidget(name_group)

        # Buttons
        btn_layout = QHBoxLayout()
        self.s_clear_btn = QPushButton("清空")
        self.s_clear_btn.clicked.connect(self.clear_slice_list)
        self.s_clear_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.s_clear_btn.setStyleSheet("padding: 10px;")
        btn_layout.addWidget(self.s_clear_btn)

        self.s_start_btn = QPushButton("开始切图 (保存到桌面)")
        self.s_start_btn.clicked.connect(self.start_slicing)
        self.s_start_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.s_start_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        btn_layout.addWidget(self.s_start_btn)

        layout.addLayout(btn_layout)
        
        # Setup Delete Functionality for Lists
        self.setup_list_actions(self.merge_list, self.delete_merge_items, self.rename_merge_items)
        self.setup_list_actions(self.slice_list, self.delete_slice_items, self.rename_slice_items)

    def init_combine_tab(self):
        layout = QVBoxLayout(self.combine_tab)

        # Drop Label
        self.combine_drop_label = QLabel("请将文件或文件夹拖拽到此处\n(支持 .jpg, .png, .pdf)\n列表支持拖拽调整顺序")
        self.combine_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.combine_drop_label.setStyleSheet(self._get_drop_style())
        layout.addWidget(self.combine_drop_label)

        # List Widget
        self.combine_list = PreviewListWidget()
        self.combine_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.combine_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.combine_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.combine_list)

        # Controls
        controls_layout = QVBoxLayout()
        
        # Sorting Group (New)
        sort_group = QGroupBox("排序 (Sort)")
        sort_group.setStyleSheet(self._get_group_style())
        sort_layout = QHBoxLayout()
        
        btn_sort_name_asc = QPushButton("名称 A-Z")
        btn_sort_name_asc.clicked.connect(lambda: self.sort_combine_list('name', True))
        
        btn_sort_name_desc = QPushButton("名称 Z-A")
        btn_sort_name_desc.clicked.connect(lambda: self.sort_combine_list('name', False))
        
        btn_sort_size_asc = QPushButton("大小 小->大")
        btn_sort_size_asc.clicked.connect(lambda: self.sort_combine_list('size', True))
        
        btn_sort_size_desc = QPushButton("大小 大->小")
        btn_sort_size_desc.clicked.connect(lambda: self.sort_combine_list('size', False))
        
        sort_layout.addWidget(btn_sort_name_asc)
        sort_layout.addWidget(btn_sort_name_desc)
        sort_layout.addWidget(btn_sort_size_asc)
        sort_layout.addWidget(btn_sort_size_desc)
        
        sort_group.setLayout(sort_layout)
        controls_layout.addWidget(sort_group)
        
        # Limit Group
        limit_layout = QHBoxLayout()
        self.c_limit_label = QLabel("单页限制: 1 MB")
        self.c_limit_slider = QSlider(Qt.Orientation.Horizontal)
        self.c_limit_slider.setMinimum(0)
        self.c_limit_slider.setMaximum(5)
        self.c_limit_slider.setValue(1) # Default to index 1 -> 1MB? Or 0? Let's say 1
        self.c_limit_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.c_limit_slider.setTickInterval(1)
        self.c_limit_slider.valueChanged.connect(lambda v: self.update_limit_label_new(v, self.c_limit_label))
        
        limit_layout.addWidget(self.c_limit_label)
        limit_layout.addWidget(self.c_limit_slider)
        
        limit_group = QGroupBox("PDF大小限制 (Compress)")
        limit_group.setStyleSheet(self._get_group_style())
        limit_group.setLayout(limit_layout)
        controls_layout.addWidget(limit_group)

        # Filename Input
        name_group = QGroupBox("导出文件名 (选填)")
        name_group.setStyleSheet(self._get_group_style())
        name_layout = QHBoxLayout()
        self.c_name_input = QLineEdit()
        self.c_name_input.setPlaceholderText("默认为 combine_日期.pdf")
        name_layout.addWidget(self.c_name_input)
        name_group.setLayout(name_layout)
        controls_layout.addWidget(name_group)

        layout.addLayout(controls_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.c_clear_btn = QPushButton("清空")
        self.c_clear_btn.clicked.connect(self.clear_combine_list)
        self.c_clear_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.c_clear_btn.setStyleSheet("padding: 10px;")
        btn_layout.addWidget(self.c_clear_btn)

        self.c_start_btn = QPushButton("开始合并 (保存到桌面)")
        self.c_start_btn.clicked.connect(self.start_combining)
        self.c_start_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.c_start_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; padding: 10px;")
        btn_layout.addWidget(self.c_start_btn)

        layout.addLayout(btn_layout)
        
        self.setup_list_actions(self.combine_list, self.delete_combine_items, self.rename_combine_items)

    def init_convert_tab(self):
        layout = QVBoxLayout(self.convert_tab)
        
        # Drop Label
        self.convert_drop_label = QLabel("请将 PDF / PSD / PPT 文件拖拽到此处")
        self.convert_drop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.convert_drop_label.setStyleSheet(self._get_drop_style())
        layout.addWidget(self.convert_drop_label)
        
        # List
        self.convert_list = QListWidget()
        self.convert_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.convert_list)
        
        # Controls
        controls_layout = QVBoxLayout()
        
        # Format Selection
        format_group = QGroupBox("导出格式")
        format_group.setStyleSheet(self._get_group_style())
        format_layout = QHBoxLayout()
        
        self.cv_radio_jpg = QRadioButton("JPG (推荐)")
        self.cv_radio_png = QRadioButton("PNG")
        self.cv_radio_jpg.setChecked(True)
        
        cv_fmt_group = QButtonGroup(self.convert_tab)
        cv_fmt_group.addButton(self.cv_radio_jpg)
        cv_fmt_group.addButton(self.cv_radio_png)
        
        format_layout.addWidget(self.cv_radio_jpg)
        format_layout.addWidget(self.cv_radio_png)
        format_group.setLayout(format_layout)
        controls_layout.addWidget(format_group)
        
        layout.addLayout(controls_layout)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.cv_clear_btn = QPushButton("清空")
        self.cv_clear_btn.clicked.connect(self.clear_convert_list)
        self.cv_clear_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cv_clear_btn.setStyleSheet("padding: 10px;")
        btn_layout.addWidget(self.cv_clear_btn)

        self.cv_start_btn = QPushButton("开始转换 (保存到桌面)")
        self.cv_start_btn.clicked.connect(self.start_converting)
        self.cv_start_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cv_start_btn.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold; padding: 10px;")
        btn_layout.addWidget(self.cv_start_btn)
        
        layout.addLayout(btn_layout)
        
        self.setup_list_actions(self.convert_list, self.delete_convert_items, lambda: None)


    def _get_drop_style(self):
        return """
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 10px;
                padding: 15px;
                font-size: 14px;
                color: #555;
                background-color: #f0f0f0;
            }
        """

    def _get_group_style(self):
        return """
            QGroupBox {
                border: 1px solid #d0d0d0;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 3px;
                color: #555;
            }
        """

    def setup_list_actions(self, list_widget, delete_slot, rename_slot):
        list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, list_widget, delete_slot, rename_slot))
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            if self.tabs.currentIndex() == 0 and self.merge_list.hasFocus():
                self.delete_merge_items()
            elif self.tabs.currentIndex() == 1 and self.slice_list.hasFocus():
                self.delete_slice_items()
            elif self.tabs.currentIndex() == 2 and self.combine_list.hasFocus():
                self.delete_combine_items()
            elif self.tabs.currentIndex() == 3 and self.convert_list.hasFocus():
                self.delete_convert_items()
        super().keyPressEvent(event)

    def show_context_menu(self, pos, list_widget, delete_slot, rename_slot):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        
        rename_action = menu.addAction("重命名 (Rename)")
        rename_action.triggered.connect(rename_slot)
        
        delete_action = menu.addAction("删除 (Delete)")
        delete_action.triggered.connect(delete_slot)
        
        menu.exec(list_widget.mapToGlobal(pos))

    def delete_merge_items(self):
        self._delete_items(self.merge_list, self.merge_images)
        self.m_split_slider.setMaximum(max(1, len(self.merge_images)))

    def delete_slice_items(self):
        self._delete_items(self.slice_list, self.slice_images)

    def _delete_items(self, list_widget, data_list):
        items = list_widget.selectedItems()
        if not items:
            return
        
        # Build list of rows to delete to handle indices correctly
        rows_to_delete = sorted([list_widget.row(item) for item in items], reverse=True)
        
        for row in rows_to_delete:
            del data_list[row]
            list_widget.takeItem(row)

    def rename_merge_items(self):
        self._rename_items(self.merge_list, self.merge_images)

    def rename_slice_items(self):
        self._rename_items(self.slice_list, self.slice_images)

    def _rename_items(self, list_widget, data_list):
        items = list_widget.selectedItems()
        if not items:
            return

        from PyQt6.QtWidgets import QInputDialog
        
        # Single Item Rename
        if len(items) == 1:
            item = items[0]
            row = list_widget.row(item)
            old_path = data_list[row]
            old_name = os.path.basename(old_path)
            old_dir = os.path.dirname(old_path)
            name_only, ext = os.path.splitext(old_name)
            
            new_name_only, ok = QInputDialog.getText(self, "重命名", "请输入新文件名:", text=name_only)
            if ok and new_name_only:
                new_name = new_name_only + ext
                new_path = os.path.join(old_dir, new_name)
                
                try:
                    os.rename(old_path, new_path)
                    data_list[row] = new_path
                    item.setText(new_name)
                except OSError as e:
                    QMessageBox.warning(self, "错误", f"重命名失败: {e}")
        
        # Multiple Items Rename
        else:
            base_name, ok = QInputDialog.getText(self, "批量重命名", "请输入基础文件名 (自动添加序号):")
            if ok and base_name:
                # Sort items by row to maintain order
                rows = sorted([list_widget.row(item) for item in items])
                
                for i, row in enumerate(rows):
                    old_path = data_list[row]
                    old_dir = os.path.dirname(old_path)
                    _, ext = os.path.splitext(old_path)
                    
                    new_name = f"{base_name}_{i+1:03d}{ext}"
                    new_path = os.path.join(old_dir, new_name)
                    
                    try:
                        os.rename(old_path, new_path)
                        data_list[row] = new_path
                        list_widget.item(row).setText(new_name)
                    except OSError as e:
                         # Continue renaming others even if one fails? Or stop? 
                         # Usually stop to avoid mess, but warning is good.
                         QMessageBox.warning(self, "错误", f"文件 {os.path.basename(old_path)} 重命名失败: {e}")

    def set_grid_val(self, r, c):
        self.s_grid_rows.setText(str(r))
        self.s_grid_cols.setText(str(c))

    def update_slice_ui_text(self):
        val = self.s_count_slider.value()
        
        if self.s_radio_grid.isChecked():
            # Grid Mode
            self.s_linear_container.setVisible(False)
            self.s_grid_container.setVisible(True)
        else:
            # Linear Mode
            self.s_linear_container.setVisible(True)
            self.s_grid_container.setVisible(False)
            
            if self.s_radio_h.isChecked():
                self.s_count_label.setText(f"切成：{val} 行 (每份高度自动计算)")
    def _get_limit_mb(self, value):
        # 0: Unlimited
        # 1: 1 MB
        # 2: 5 MB
        # 3: 10 MB
        # 4: 20 MB
        # 5: 50 MB
        mapping = {0: 0, 1: 1, 2: 5, 3: 10, 4: 20, 5: 50}
        return mapping.get(value, 0)

    def update_limit_label_new(self, value, label_widget):
        mb = self._get_limit_mb(value)
        if mb == 0:
            label_widget.setText("单页限制: 不限 (Unlimited)")
        else:
            label_widget.setText(f"单页限制: {mb} MB")

    def update_limit_label(self, value, label_widget):
        # 0: Unlimited
        # 1: 150 KB
        # 2: 300 KB
        # 3: 500 KB
        # 4: 750 KB
        # 5: 1 MB (1000 KB)
        mapping = {
            0: 0,
            1: 150,
            2: 300,
            3: 500,
            4: 750,
            5: 1000
        }
        kb_val = mapping.get(value, 0)
        
        if kb_val == 0:
            label_widget.setText("预设: 无限制")
        else:
            if kb_val >= 1000:
                label_widget.setText(f"预设: {kb_val/1000:.1f} MB")
            else:
                label_widget.setText(f"预设: {kb_val} KB")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        
        current_index = self.tabs.currentIndex()
        
        # Define valid extensions based on tab
        if current_index == 3: # Convert Tab
             valid_extensions = ('.pdf', '.psd', '.ppt', '.pptx')
        else:
             valid_extensions = ('.jpg', '.jpeg', '.png', '.pdf')
        
        new_files = []
        for path in files:
            if os.path.isfile(path) and path.lower().endswith(valid_extensions):
                new_files.append(path)
            elif os.path.isdir(path):
                for root, _, filenames in os.walk(path):
                    for fname in filenames:
                        if fname.lower().endswith(valid_extensions):
                            new_files.append(os.path.join(root, fname))

        if not new_files:
            QMessageBox.warning(self, "无效文件", f"当前模式不支持该文件格式。\n仅支持: {valid_extensions}")
            return

        if current_index == 0: # Merge Tab
            combined_set = set(self.merge_images + new_files)
            self.merge_images = sort_files(list(combined_set))
            self.update_merge_list()
            self.m_split_slider.setMaximum(max(1, len(self.merge_images)))
        elif current_index == 1: # Slice Tab
            # For slicing, order matters less, just append
            for img in new_files:
                if img not in self.slice_images:
                    self.slice_images.append(img)
            self.update_slice_list()
        elif current_index == 2: # Combine Tab
            for img in new_files:
                # Add to widget directly
                from PyQt6.QtWidgets import QListWidgetItem
                item = QListWidgetItem(os.path.basename(img))
                item.setData(Qt.ItemDataRole.UserRole, img)
                self.combine_list.addItem(item)
        elif current_index == 3: # Convert Tab
             for f in new_files:
                 if f not in self.convert_files:
                     self.convert_files.append(f)
             self.update_convert_list()

    def update_merge_list(self):
        self.merge_list.clear()
        for path in self.merge_images:
            self.merge_list.addItem(os.path.basename(path))

    def update_slice_list(self):
        self.slice_list.clear()
        for path in self.slice_images:
            self.slice_list.addItem(os.path.basename(path))

    def clear_merge_list(self):
        self.merge_images = []
        self.merge_list.clear()
        self.m_split_slider.setMaximum(1)
        self.m_split_slider.setValue(1)

    def clear_slice_list(self):
        self.slice_images = []
        self.slice_list.clear()

    def clear_combine_list(self):
        self.combine_list.clear()

    def clear_convert_list(self):
        self.convert_files = []
        self.convert_list.clear()
        
    def update_convert_list(self):
        self.convert_list.clear()
        for path in self.convert_files:
             self.convert_list.addItem(os.path.basename(path))

    def delete_convert_items(self):
        self._delete_items(self.convert_list, self.convert_files)

    def delete_combine_items(self):
        items = self.combine_list.selectedItems()
        for item in items:
            self.combine_list.takeItem(self.combine_list.row(item))

    def rename_combine_items(self):
        # Rename logic for combine tab - just changes the display text, not the file?
        pass

    def sort_combine_list(self, key, ascending):
        count = self.combine_list.count()
        if count < 2:
            return
            
        items = []
        for i in range(count):
            items.append(self.combine_list.item(i))
            
        if key == 'name':
            items.sort(key=lambda x: x.text().lower(), reverse=not ascending)
        elif key == 'size':
            # Need to get file size from path
            def get_size(item):
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.exists(path):
                    return os.path.getsize(path)
                return 0
            items.sort(key=get_size, reverse=not ascending)
        
        # Actually simplest way is takeItem and insert
        for item in items:
            self.combine_list.takeItem(self.combine_list.row(item))
            
        for item in items:
            self.combine_list.addItem(item)

    def sort_combine_list(self, key, ascending):
        count = self.combine_list.count()
        if count < 2:
            return
            
        items = []
        for i in range(count):
            items.append(self.combine_list.item(i))
            
        if key == 'name':
            # Natural Sort Key
            def natural_key(item):
                text = item.text().lower()
                return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', text)]
            
            items.sort(key=natural_key, reverse=not ascending)
        elif key == 'size':
            # Need to get file size from path
            def get_size(item):
                path = item.data(Qt.ItemDataRole.UserRole)
                if path and os.path.exists(path):
                    return os.path.getsize(path)
                return 0
            items.sort(key=get_size, reverse=not ascending)
            
        # Re-populate
        # self.combine_list.clear() # Clear deletes items? Yes.
        # Taking items out might be safer
        
        # Actually simplest way is takeItem and insert
        for item in items:
            self.combine_list.takeItem(self.combine_list.row(item))
            
        for item in items:
            self.combine_list.addItem(item)

    # --- Actions ---

    # --- Helper Methods for Splitting ---
    def set_merge_grid_val(self, r, c):
        self.m_grid_rows.setText(str(r))
        self.m_grid_cols.setText(str(c))

    def update_merge_ui_text(self):
        if self.m_radio_grid.isChecked():
            self.m_grid_container.setVisible(True)
            self.m_split_group.setVisible(False) # Hide split count for Grid? Or keep? Usually grid implies 1 image unless multi-page grid.
            self.m_split_group.setTitle("分组拼接设置 (宫格模式下暂不支持分组)")
            self.m_split_slider.setEnabled(False)
        else:
            self.m_grid_container.setVisible(False)
            self.m_split_group.setVisible(True)
            self.m_split_group.setTitle("分组拼接设置")
            self.m_split_slider.setEnabled(True)

    def start_stitching(self):
        if not self.merge_images:
            QMessageBox.warning(self, "提示", "请先添加图片！")
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        
        # Get settings
        split_count = self.m_split_slider.value()
        
        target_width = None
        if self.m_radio_750.isChecked():
            target_width = 750
        elif self.m_radio_1080.isChecked():
            target_width = 1080
        elif self.m_radio_custom.isChecked():
            try:
                val_text = self.m_custom_input.text().strip()
                if not val_text: raise ValueError
                target_width = int(val_text)
            except ValueError:
                QMessageBox.warning(self, "输入错误", "请输入有效的宽度！")
                return

        # Get Limit
        limit_val = 0
        if self.m_radio_limit_custom.isChecked():
            try:
                c_val = int(self.m_limit_custom_input.text().strip())
                if c_val <= 0: raise ValueError
                limit_val = c_val
            except ValueError:
                 QMessageBox.warning(self, "输入错误", "请输入有效的限制大小(KB)！")
                 return
        else:
            # Slider mapping
            slider_val = self.m_limit_slider.value()
            mapping = {0: 0, 1: 150, 2: 300, 3: 500, 4: 750, 5: 1000}
            limit_val = mapping.get(slider_val, 0)
        
        # Get Mode
        mode = 'vertical'
        rows = None
        cols = None
        
        if self.m_radio_h.isChecked():
            mode = 'horizontal'
        elif self.m_radio_grid.isChecked():
            mode = 'grid'
            try:
                rows = int(self.m_grid_rows.text())
                cols = int(self.m_grid_cols.text())
                if rows <= 0 or cols <= 0:
                     raise ValueError
            except ValueError:
                QMessageBox.warning(self, "错误", "宫格模式请输入有效的行数和列数！")
                return

                return

        # Get Format
        output_format = 'AUTO'
        if self.m_radio_fmt_jpg.isChecked(): output_format = 'JPG'
        elif self.m_radio_fmt_png.isChecked(): output_format = 'PNG'
        elif self.m_radio_fmt_pdf.isChecked(): output_format = 'PDF'

        self.m_start_btn.setEnabled(False)
        self.m_start_btn.setText("正在拼接... ")
        
        custom_name = self.m_name_input.text().strip()
        
        self.stitch_thread = StitcherThread(self.merge_images, desktop_path, split_count, target_width, limit_val, mode, rows, cols, output_format, custom_name)
        self.stitch_thread.finished_signal.connect(self.on_stitching_finished)
        self.stitch_thread.start()

    def on_stitching_finished(self, success, message):
        self.m_start_btn.setEnabled(True)
        self.m_start_btn.setText("开始拼接 (保存到桌面)")
        if success:
            QMessageBox.information(self, "成功", f"{message}\n已保存到桌面。")
        else:
            QMessageBox.critical(self, "错误", f"拼接失败：\n{message}")

    def preview_grid(self):
        if not self.slice_images:
            QMessageBox.warning(self, "提示", "请先拖入一张图片进行预览。")
            return
            
        # Fix: Use currently selected row, or default to 0 if none or multi-select (take first)
        selected_row = self.slice_list.currentRow()
        if selected_row < 0:
            if len(self.slice_images) > 0:
                selected_row = 0
            else:
                 return # Should be caught by check above
        
        img_path = self.slice_images[selected_row]
        
        try:
            r = int(self.s_grid_rows.text())
            c = int(self.s_grid_cols.text())
        except ValueError:
             QMessageBox.warning(self, "提示", "请输入有效的行和列数值。")
             return
             
        dlg = PreviewDialog(img_path, r, c, self)
        dlg.exec()

    def start_slicing(self):
        if not self.slice_images:
            QMessageBox.warning(self, "提示", "请先添加要切分的图片！")
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        
        # Settings
        count = self.s_count_slider.value()
        smart_mode = self.s_smart_check.isChecked()
        
        target_width = None
        if self.s_radio_custom.isChecked():
            val_text = self.s_custom_input.text().strip()
            if not val_text:
                # User left it empty, use default placeholder value
                target_width = 750
            else:
                try:
                    target_width = int(val_text)
                except ValueError:
                    QMessageBox.warning(self, "输入错误", "请输入有效的宽度！")
                    return

        # Get Format
        output_format = 'AUTO'
        if self.s_radio_fmt_jpg.isChecked(): output_format = 'JPG'
        elif self.s_radio_fmt_png.isChecked(): output_format = 'PNG'
        elif self.s_radio_fmt_pdf.isChecked(): output_format = 'PDF'

        # Get Limit
        limit_val = 0
        if self.s_radio_limit_custom.isChecked():
             try:
                c_val = int(self.s_limit_custom_input.text().strip())
                if c_val <= 0: raise ValueError
                limit_val = c_val
             except ValueError:
                 QMessageBox.warning(self, "输入错误", "请输入有效的限制大小(KB)！")
                 return
        else:
            slider_val = self.s_limit_slider.value()
            mapping = {0: 0, 1: 150, 2: 300, 3: 500, 4: 750, 5: 1000}
            limit_val = mapping.get(slider_val, 0)

        # Get Direction/Mode
        direction = 'horizontal'
        rows = None
        cols = None
        
        if self.s_radio_v.isChecked():
            direction = 'vertical'
        elif self.s_radio_grid.isChecked():
            direction = 'grid'
            try:
                rows = int(self.s_grid_rows.text())
                cols = int(self.s_grid_cols.text())
                if rows <= 0 or cols <= 0:
                    raise ValueError("行数和列数必须大于0")
            except ValueError:
                 QMessageBox.warning(self, "错误", "请设置正确的行数和列数！")
                 return

        self.s_start_btn.setEnabled(False)
        self.s_start_btn.setText("正在切图... ")
        
        custom_name = self.s_name_input.text().strip()

        self.slicer_thread = SlicerThread(self.slice_images, desktop_path, count, smart_mode, target_width, limit_val, direction, rows, cols, output_format, custom_name)
        self.slicer_thread.finished_signal.connect(self.on_slicing_finished)
        self.slicer_thread.start()

    def on_slicing_finished(self, success, message):
        self.s_start_btn.setEnabled(True)
        self.s_start_btn.setText("开始切图 (保存到桌面)")
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "注意", message)

    def start_combining(self):
        if self.combine_list.count() == 0:
            QMessageBox.warning(self, "提示", "请先添加图片！")
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        
        # Get Items in Order
        paths = []
        for i in range(self.combine_list.count()):
            item = self.combine_list.item(i)
            # Retrieve path from tool tip or data? We set UserRole in dropEvent
            path = item.data(Qt.ItemDataRole.UserRole) 
            if path:
                paths.append(path)
        
        if not paths:
             QMessageBox.warning(self, "提示", "列表为空或数据异常。")
             return
             
        # Settings
        limit_mb = self._get_limit_mb(self.c_limit_slider.value())
        limit_val = limit_mb * 1024 # Convert to KB
        
        custom_name = self.c_name_input.text().strip()
        if not custom_name:
             from datetime import datetime
             timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
             custom_name = f"combine_{timestamp}.pdf"
        
        if not custom_name.lower().endswith(".pdf"):
            custom_name += ".pdf"
            
        output_file_path = os.path.join(desktop_path, custom_name)
        
        # Check overwrite logic
        counter = 1
        base_name, ext = os.path.splitext(custom_name)
        while os.path.exists(output_file_path):
            output_file_path = os.path.join(desktop_path, f"{base_name}_{counter}{ext}")
            counter += 1

        self.c_start_btn.setEnabled(False)
        self.c_start_btn.setText("正在合并... ")
        
        self.merger_thread = MergerThread(paths, output_file_path, limit_val)
        self.merger_thread.finished_signal.connect(self.on_combining_finished)
        self.merger_thread.start()

    def on_combining_finished(self, success, message):
        self.c_start_btn.setEnabled(True)
        self.c_start_btn.setText("开始合并 (保存到桌面)")
        if success:
            QMessageBox.information(self, "成功", f"{message}")
        else:
            QMessageBox.critical(self, "错误", f"合并失败：\n{message}")

    def start_converting(self):
        if not self.convert_files:
            QMessageBox.warning(self, "提示", "请先添加文件！")
            return

        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        
        fmt = 'jpg'
        if self.cv_radio_png.isChecked():
            fmt = 'png'
            
        self.cv_start_btn.setEnabled(False)
        self.cv_start_btn.setText("正在转换...")

        self.converter_thread = ConverterThread(self.convert_files, desktop_path, fmt)
        self.converter_thread.finished_signal.connect(self.on_converting_finished)
        self.converter_thread.start()

    def on_converting_finished(self, success, message):
        self.cv_start_btn.setEnabled(True)
        self.cv_start_btn.setText("开始转换 (保存到桌面)")
        if success:
             QMessageBox.information(self, "完成", message)
        else:
             QMessageBox.warning(self, "注意", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageMatrixApp()
    window.show()
    sys.exit(app.exec())
