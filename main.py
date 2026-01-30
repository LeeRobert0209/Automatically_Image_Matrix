import sys
import os
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QListWidget, QLabel, 
                             QMessageBox, QAbstractItemView, QRadioButton, QButtonGroup,
                             QSlider, QGroupBox, QLineEdit, QTabWidget, QCheckBox)
from PyQt6.QtCore import Qt, QMimeData, QThread, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIntValidator, QIcon

from sorter import sort_files
from stitcher import stitch_images
from grid_preview import PreviewDialog
from slicer import slice_image, slice_grid_image

class StitcherThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, image_paths, output_dir, split_count, target_width, max_kb, mode='vertical', rows=2, cols=2, output_format='AUTO'):
        super().__init__()
        self.image_paths = image_paths
        self.output_dir = output_dir
        self.split_count = split_count
        self.target_width = target_width
        self.max_kb = max_kb
        self.mode = mode
        self.rows = rows
        self.cols = cols
        self.output_format = output_format

    def run(self):
        try:
            success, message = stitch_images(self.image_paths, self.output_dir, self.split_count, self.target_width, self.max_kb, self.mode, self.rows, self.cols, self.output_format)
            self.finished_signal.emit(success, message)
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class SlicerThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, image_paths, output_dir, count, smart_mode, target_width, max_kb, direction='horizontal', rows=None, cols=None, output_format='AUTO'):
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

    def run(self):
        success = True
        message = ""
        try:
            for img_path in self.image_paths:
                if self.direction == 'grid':
                    max_kb_val = self.max_kb if self.max_kb > 0 else None
                    s, m = slice_grid_image(img_path, self.output_dir, self.rows, self.cols, self.target_width, max_kb_val, self.output_format)
                else:
                    max_kb_val = self.max_kb if self.max_kb > 0 else None
                    s, m = slice_image(img_path, self.output_dir, self.count, self.smart_mode, self.target_width, max_kb_val, self.direction, self.output_format)
                
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
        
        self.stitch_thread = None
        self.slicer_thread = None

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

        # Global Enable Drag & Drop
        self.setAcceptDrops(True)

    def init_merge_tab(self):
        layout = QVBoxLayout(self.merge_tab)

        # Drop Label
        self.merge_drop_label = QLabel("请将图片拖拽到此处\n(支持 .jpg, .jpeg, .png, .psd)")
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
        limit_group = QGroupBox("图片大小限制 (KB)")
        limit_layout = QVBoxLayout()
        self.m_limit_label = QLabel("大小限制：200 KB (默认)")
        self.m_limit_slider = QSlider(Qt.Orientation.Horizontal)
        self.m_limit_slider.setMinimum(0)
        self.m_limit_slider.setMaximum(5) # 0, 1, 2, 3, 4, 5 -> Unlimited, 200, 400, 600, 800, 1000
        self.m_limit_slider.setValue(1) # Default 200KB
        self.m_limit_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.m_limit_slider.setTickInterval(1)
        self.m_limit_slider.valueChanged.connect(lambda v: self.update_limit_label(v, self.m_limit_label))
        
        limit_layout.addWidget(self.m_limit_label)
        limit_layout.addWidget(self.m_limit_slider)
        limit_group.setLayout(limit_layout)
        controls_layout.addWidget(limit_group)

        # Split Selection
        self.m_split_group = QGroupBox("分组拼接设置")
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

        # Buttons
        btn_layout = QHBoxLayout()
        self.m_clear_btn = QPushButton("清空")
        self.m_clear_btn.clicked.connect(self.clear_merge_list)
        btn_layout.addWidget(self.m_clear_btn)

        self.m_start_btn = QPushButton("开始拼接 (保存到桌面)")
        self.m_start_btn.clicked.connect(self.start_stitching)
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

        # 2. Limit (Reduced height usage)
        limit_layout = QHBoxLayout()
        self.s_limit_label = QLabel("限大小: 200K")
        self.s_limit_label.setFixedWidth(100)
        self.s_limit_slider = QSlider(Qt.Orientation.Horizontal)
        self.s_limit_slider.setMinimum(0)
        self.s_limit_slider.setMaximum(5)
        self.s_limit_slider.setValue(1)
        self.s_limit_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.s_limit_slider.setTickInterval(1)
        self.s_limit_slider.valueChanged.connect(lambda v: self.update_limit_label(v, self.s_limit_label))
        
        limit_layout.addWidget(self.s_limit_label)
        limit_layout.addWidget(self.s_limit_slider)
        controls_layout.addLayout(limit_layout)

        # 3. Settings Group
        slice_group = QGroupBox("切图模式 & 设置")
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

        # Buttons
        btn_layout = QHBoxLayout()
        self.s_clear_btn = QPushButton("清空")
        self.s_clear_btn.clicked.connect(self.clear_slice_list)
        btn_layout.addWidget(self.s_clear_btn)

        self.s_start_btn = QPushButton("开始切图 (保存到桌面)")
        self.s_start_btn.clicked.connect(self.start_slicing)
        self.s_start_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        btn_layout.addWidget(self.s_start_btn)

        layout.addLayout(btn_layout)
        
        # Setup Delete Functionality for Lists
        self.setup_list_actions(self.merge_list, self.delete_merge_items, self.rename_merge_items)
        self.setup_list_actions(self.slice_list, self.delete_slice_items, self.rename_slice_items)


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

    def setup_list_actions(self, list_widget, delete_slot, rename_slot):
        list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        list_widget.customContextMenuRequested.connect(lambda pos: self.show_context_menu(pos, list_widget, delete_slot, rename_slot))
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            if self.tabs.currentIndex() == 0 and self.merge_list.hasFocus():
                self.delete_merge_items()
            elif self.tabs.currentIndex() == 1 and self.slice_list.hasFocus():
                self.delete_slice_items()
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
            else:
                self.s_count_label.setText(f"切成：{val} 列 (每份宽度自动计算)")

    def update_limit_label(self, value, label_widget):
        kb_val = value * 200
        if value == 0:
            label_widget.setText("限大小: 不限")
        else:
            if kb_val >= 1000:
                label_widget.setText(f"限大小: 1 MB")
            else:
                label_widget.setText(f"限大小: {kb_val} KB")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        valid_extensions = ('.jpg', '.jpeg', '.png', '.psd')
        new_images = [f for f in files if f.lower().endswith(valid_extensions)]

        if not new_images:
            QMessageBox.warning(self, "无效文件", "请只拖入支持的图片文件 (.jpg, .png, .psd)")
            return

        current_index = self.tabs.currentIndex()
        if current_index == 0: # Merge Tab
            combined_set = set(self.merge_images + new_images)
            self.merge_images = sort_files(list(combined_set))
            self.update_merge_list()
            self.m_split_slider.setMaximum(max(1, len(self.merge_images)))
        else: # Slice Tab
            # For slicing, order matters less, just append
            for img in new_images:
                if img not in self.slice_images:
                    self.slice_images.append(img)
            self.update_slice_list()
            # Select the last added item effectively? Or just leave as is.

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
        limit_val = self.m_limit_slider.value() * 200 # 0 -> 0, 1 -> 200 ...
        
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
        
        self.stitch_thread = StitcherThread(self.merge_images, desktop_path, split_count, target_width, limit_val, mode, rows, cols, output_format)
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
        limit_val = self.s_limit_slider.value() * 200

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
        
        self.slicer_thread = SlicerThread(self.slice_images, desktop_path, count, smart_mode, target_width, limit_val, direction, rows, cols, output_format)
        self.slicer_thread.finished_signal.connect(self.on_slicing_finished)
        self.slicer_thread.start()

    def on_slicing_finished(self, success, message):
        self.s_start_btn.setEnabled(True)
        self.s_start_btn.setText("开始切图 (保存到桌面)")
        if success:
            QMessageBox.information(self, "完成", message)
        else:
            QMessageBox.warning(self, "注意", message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageMatrixApp()
    window.show()
    sys.exit(app.exec())
