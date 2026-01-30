import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QScrollArea, QWidget, QFrame)
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QImage
from PyQt6.QtCore import Qt, QPoint
from PIL import Image, ImageDraw

class MagnifierWidget(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(200, 200)
        self.setStyleSheet("border: 2px solid white; background-color: black;")
        self.setVisible(False)
        self.setWindowFlags(Qt.WindowType.ToolTip) # Make it float above like a tooltip

class PreviewLabel(QLabel):
    def __init__(self, original_image_path, rows, cols, parent=None):
        super().__init__(parent)
        self.original_image_path = original_image_path
        self.rows = rows
        self.cols = cols
        
        # Load original image for magnifier reference
        self.pil_image = Image.open(self.original_image_path)
        self.orig_w, self.orig_h = self.pil_image.size
        
        # Create thumbnail roughly 600px width
        self.target_display_width = 600
        display_ratio = self.orig_h / self.orig_w
        self.display_h = int(self.target_display_width * display_ratio)
        
        # Create thumbnail image
        self.thumb = self.pil_image.copy()
        self.thumb.thumbnail((self.target_display_width, self.target_display_width * 10)) # Constraint mainly by width
        
        # Actual size of thumbnail might be slightly different than calculated if aspect ratio preserved
        self.display_w, self.display_h = self.thumb.size
        
        # Convert PIL to QPixmap
        data = self.thumb.convert("RGBA").tobytes("raw", "RGBA")
        qim = QImage(data, self.display_w, self.display_h, QImage.Format.Format_RGBA8888)
        self.pixmap_base = QPixmap.fromImage(qim)
        
        self.setPixmap(self.pixmap_base)
        self.setMouseTracking(True)
        
        # Magnifier
        self.magnifier = MagnifierWidget(self)
        
        # Calculate grid lines (on the display image)
        self.h_lines = [] # y coordinates
        self.v_lines = [] # x coordinates
        
        step_y = self.display_h / self.rows
        for i in range(1, self.rows):
            self.h_lines.append(int(i * step_y))
            
        step_x = self.display_w / self.cols
        for i in range(1, self.cols):
            self.v_lines.append(int(i * step_x))
            
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        pen = QPen(QColor(255, 0, 0, 180), 2) # Red semi-transparent
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        
        # Draw Horizontal Lines
        for y in self.h_lines:
            painter.drawLine(0, y, self.width(), y)
            
        # Draw Vertical Lines
        for x in self.v_lines:
            painter.drawLine(x, 0, x, self.height())
            
    def mouseMoveEvent(self, event):
        pos = event.pos()
        x, y = pos.x(), pos.y()
        
        # Check if near lines (threshold 10px)
        near_h = any(abs(y - ly) < 10 for ly in self.h_lines)
        near_v = any(abs(x - lx) < 10 for lx in self.v_lines)
        
        if near_h or near_v:
            self.show_magnifier(x, y)
        else:
            self.magnifier.setVisible(False)
            
        super().mouseMoveEvent(event)
        
    def show_magnifier(self, view_x, view_y):
        # Map view coordinate to original coordinate
        # Scale factor
        scale_x = self.orig_w / self.display_w
        scale_y = self.orig_h / self.display_h
        
        orig_x = int(view_x * scale_x)
        orig_y = int(view_y * scale_y)
        
        # Crop 100x100 from original (to show as 200x200? The user said "200x200 pixel window showing 1:1 details")
        # 1:1 details means 1 pixel on screen = 1 pixel on image.
        # So we crop 200x200 from original.
        
        crop_size = 200
        left = max(0, orig_x - crop_size // 2)
        top = max(0, orig_y - crop_size // 2)
        right = min(self.orig_w, left + crop_size)
        bottom = min(self.orig_h, top + crop_size)
        
        # Adjust if out of bounds
        if right - left < crop_size:
            left = max(0, right - crop_size)
        if bottom - top < crop_size:
            top = max(0, bottom - crop_size)
            
        try:
            crop = self.pil_image.crop((left, top, left + crop_size, top + crop_size))
            
            # Convert to QPixmap
            c_data = crop.convert("RGBA").tobytes("raw", "RGBA")
            c_qim = QImage(c_data, crop.width, crop.height, QImage.Format.Format_RGBA8888)
            c_pix = QPixmap.fromImage(c_qim)
            
            self.magnifier.setPixmap(c_pix)
            self.magnifier.setVisible(True)
            self.magnifier.move(view_x + 15, view_y + 15) # Offset a bit
            self.magnifier.raise_()
        except Exception:
            self.magnifier.setVisible(False)

class PreviewDialog(QDialog):
    def __init__(self, image_path, rows, cols, parent=None):
        super().__init__(parent)
        self.setWindowTitle("切图预览 (悬停红色切分线查看细节)")
        # Sizing: minimal width to fit the 600px image + padding
        self.resize(650, 700)
        
        layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)
        
        container = QWidget()
        scroll.setWidget(container)
        
        c_layout = QVBoxLayout(container)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        try:
            self.preview_label = PreviewLabel(image_path, rows, cols)
            c_layout.addWidget(self.preview_label)
        except Exception as e:
            err_label = QLabel(f"无法加载预览: {str(e)}")
            c_layout.addWidget(err_label)
