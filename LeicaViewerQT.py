"""PyQt6 Leica Image Viewer

Lightweight viewer for Leica LIF/XLEF/LOF images with:
- Folder browser and image list
- Image panel with optional sliders for T/Z/S
- Channel toggle buttons (overlay rendering)
- Compact metadata (dimensions + voxel size)
- Log window

Notes:
- Uses numpy.memmap to read a single slice efficiently.
- Default selection: Z=center, T=0, S=0, all channels ON.
- Color mixing reuses LUT names when available; falls back to a default cycle.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from dataclasses import dataclass
from typing import List

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTextEdit, QSplitter, QSizePolicy, QDialog, QDialogButtonBox, QTextBrowser,
    QTreeWidget, QTreeWidgetItem, QStyle, QSlider, QToolButton, QScrollArea,
    QFrame
)
from PyQt6.QtGui import QIcon, QPixmap, QPalette, QColor, QImage
from PyQt6.QtCore import Qt

import numpy as np
import cv2
from datetime import datetime

# Internal helpers
from ci_leica_converters_helpers import read_leica_file, get_image_metadata, get_image_metadata_LOF
from CreatePreview import adjust_image_contrast, convert_color_name_to_rgb

ROOT_DIR = "L:/Archief/active/cellular_imaging/OMERO_test" 

def apply_dark_theme(app: QApplication) -> None:
    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(32, 32, 32))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Base, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(60, 60, 60))
    palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))
    app.setPalette(palette)


@dataclass
class ImageItem:
    name: str
    uuid: str
    meta: dict


class LeicaViewerApp(QMainWindow):
    VERSION = "0.1.0"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Leica Image Viewer v{self.VERSION}")
        icon_path = Path(__file__).with_name('images').joinpath('app-icon.png')
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1200, 800)
        self.current_dir = ROOT_DIR if os.path.isdir(ROOT_DIR) else os.getcwd()

        self.current_file: str | None = None
        self.selected_image: ImageItem | None = None
        self.last_image_meta_json: str | None = None

        # current indices and channel toggles
        self.idx_z = 0
        self.idx_t = 0
        self.idx_s = 0
        self.channel_toggles: List[QToolButton] = []

        central = QWidget(self)
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        # Top bar: root + browse + help
        top = QHBoxLayout()
        self.btn_browse_root = QPushButton("Browse…")
        self.btn_browse_root.setFixedWidth(100)
        self.btn_browse_root.clicked.connect(self.choose_root)
        self.lbl_root = QLabel(f"Root: {self.current_dir}")
        self.btn_help = QPushButton("Help")
        self.btn_help.setFixedWidth(90)
        self.btn_help.clicked.connect(self.show_help)
        top.addWidget(self.btn_browse_root)
        top.addWidget(self.lbl_root)
        top.addStretch(1)
        top.addWidget(self.btn_help)
        outer.addLayout(top)

        # Split: left (fs + images) | right (viewer + controls + meta + log)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_folders = QLabel("Folders and Leica files:")
        left_layout.addWidget(self.lbl_folders)
        self.tree_fs = QTreeWidget(); self.tree_fs.setHeaderHidden(True)
        self.tree_fs.itemExpanded.connect(self.on_fs_item_expanded)
        self.tree_fs.itemDoubleClicked.connect(self.on_fs_item_double_clicked)
        self.tree_fs.itemSelectionChanged.connect(self.on_fs_selection_changed)
        left_layout.addWidget(self.tree_fs, 2)
        # Images list below folder tree (no label)
        self.tree_images = QTreeWidget(); self.tree_images.setHeaderHidden(True)
        self.tree_images.itemSelectionChanged.connect(self.on_image_selection_changed)
        self.tree_images.itemExpanded.connect(self.on_tree_item_expanded)
        left_layout.addWidget(self.tree_images, 2)
        # Small preview and metadata under images list
        self.left_preview = QLabel("Preview")
        self.left_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.left_preview.setFixedHeight(120)
        self.left_preview.setFrameShape(QFrame.Shape.StyledPanel)
        left_layout.addWidget(self.left_preview)
        self.left_meta = QLabel("")
        self.left_meta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.left_meta.setWordWrap(True)
        self.left_meta.setFixedHeight(40)
        self.left_meta.setFrameShape(QFrame.Shape.NoFrame)
        left_layout.addWidget(self.left_meta)
        splitter.addWidget(left)

        # Right panel
        right = QWidget(); right_layout = QVBoxLayout(right); right_layout.setContentsMargins(0, 0, 0, 0)
        # Zoom bar
        zoom_row = QHBoxLayout()
        zoom_lbl = QLabel("Zoom")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 1000)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        self.zoom_value_lbl = QLabel("100%")
        self.btn_zoom_fit = QPushButton("Fit")
        self.btn_zoom_100 = QPushButton("100%")
        self.btn_zoom_fit.clicked.connect(lambda: self._apply_zoom(self.zoom_slider.minimum()))
        self.btn_zoom_100.clicked.connect(lambda: self._apply_zoom(100))
        zoom_row.addWidget(zoom_lbl)
        zoom_row.addWidget(self.zoom_slider, 1)
        zoom_row.addWidget(self.zoom_value_lbl)
        zoom_row.addWidget(self.btn_zoom_fit)
        zoom_row.addWidget(self.btn_zoom_100)
        right_layout.addLayout(zoom_row)

        # Image area with vertical Z slider on the left and pannable image on the right
        image_row = QHBoxLayout()
        zpanel = QVBoxLayout()
        self.z_title = QLabel("Z")
        self.z_slider_vert = QSlider(Qt.Orientation.Vertical)
        self.z_slider_vert.setEnabled(False)
        self.z_slider_vert.valueChanged.connect(self.on_slider_changed)
        self.z_value_lbl = QLabel("0")
        self.z_value_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        zpanel.addWidget(self.z_title, 0)
        zpanel.addWidget(self.z_slider_vert, 1)
        zpanel.addWidget(self.z_value_lbl, 0)
        zpanel_wrap = QWidget(); zpanel_wrap.setLayout(zpanel)
        image_row.addWidget(zpanel_wrap, 0)

        # Scrollable image label (zoom/pan)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(False)
        self.image_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label = QLabel("Image will appear here")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.image_label.setMinimumSize(320, 240)
        self.image_scroll.setWidget(self.image_label)
        # Install event filters for wheel zoom and drag pan
        self.image_scroll.viewport().installEventFilter(self)
        self.image_label.installEventFilter(self)
        self._dragging = False
        self._last_pos = None
        self._zoom_factor = 1.0
        image_row.addWidget(self.image_scroll, 1)
        right_layout.addLayout(image_row, 5)

        # Controls: channel toggles + sliders
        controls = QWidget(); controls_layout = QVBoxLayout(controls); controls_layout.setContentsMargins(0, 0, 0, 0)
        # Channel toggles row (scrollable if many)
        self.chan_area = QScrollArea(); self.chan_area.setWidgetResizable(True)
        self.chan_widget = QWidget(); self.chan_row = QHBoxLayout(self.chan_widget)
        self.chan_row.setContentsMargins(6, 6, 6, 6)
        self.chan_row.addStretch(1)
        self.chan_area.setWidget(self.chan_widget)
        controls_layout.addWidget(self.chan_area)
        # Horizontal sliders for T and S only (Z is vertical now)
        self.slider_t = self._make_slider("T", 0, 0, self.on_slider_changed)
        self.slider_s = self._make_slider("S", 0, 0, self.on_slider_changed)
        controls_layout.addWidget(self.slider_t[0])
        controls_layout.addWidget(self.slider_s[0])
        right_layout.addWidget(controls)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        outer.addWidget(splitter, 1)

        # Init
        self.populate_fs_root()

        # Optional stylesheet
        css_file = Path(__file__).parent / "styles" / "darktheme.css"
        if css_file.exists():
            try:
                css = css_file.read_text(encoding='utf-8')
                css = css.replace('$$IMAGES_DIR$$', (Path(__file__).parent / 'images').as_posix())
                self.setStyleSheet(css)
            except Exception:
                pass

    # ---------- UI helpers ----------
    def _make_slider(self, name: str, minv: int, maxv: int, cb):
        w = QWidget(); layout = QHBoxLayout(w); layout.setContentsMargins(6, 0, 6, 0)
        lbl = QLabel(f"{name}:")
        s = QSlider(Qt.Orientation.Horizontal)
        s.setMinimum(minv); s.setMaximum(maxv); s.setSingleStep(1); s.setPageStep(1)
        s.setEnabled(False)
        s.valueChanged.connect(cb)
        val_lbl = QLabel("0")
        layout.addWidget(lbl); layout.addWidget(s, 1); layout.addWidget(val_lbl)
        return w, s, val_lbl

    def append_log(self, text: str):
    # Log pane removed; keep as no-op
        pass

    # ---------- Filesystem tree ----------
    def icon_folder(self) -> QIcon:
        p = Path(__file__).with_name("images").joinpath("folder.svg")
        return QIcon(str(p)) if p.exists() else self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    def icon_image(self) -> QIcon:
        p = Path(__file__).with_name("images").joinpath("image.svg")
        return QIcon(str(p)) if p.exists() else self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def icon_for_file(self, ext: str) -> QIcon:
        ext = ext.lower().lstrip('.')
        mapping = {'lif': "file-lif.svg", 'xlef': "file-xlef.svg", 'lof': "file-lof.svg"}
        p = Path(__file__).with_name("images").joinpath(mapping.get(ext, "file.svg"))
        return QIcon(str(p)) if p.exists() else self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

    def populate_fs_root(self):
        self.tree_fs.clear()
        root_item = QTreeWidgetItem([self.current_dir])
        root_item.setIcon(0, self.icon_folder())
        root_item.setData(0, Qt.ItemDataRole.UserRole, self.current_dir)
        root_item.addChild(QTreeWidgetItem(["…"]))
        self.tree_fs.addTopLevelItem(root_item)
        self.tree_fs.expandItem(root_item)

    def on_fs_item_expanded(self, item: QTreeWidgetItem):
        if item.childCount() == 1 and item.child(0).text(0) == "…":
            self._populate_fs_children(item)

    def _populate_fs_children(self, parent_item: QTreeWidgetItem):
        if parent_item.childCount() == 1 and parent_item.child(0).text(0) == "…":
            parent_item.removeChild(parent_item.child(0))
        parent_path = parent_item.data(0, Qt.ItemDataRole.UserRole)
        if not parent_path or not os.path.isdir(parent_path):
            return
        try:
            entries = sorted(os.listdir(parent_path))
        except Exception:
            return
        has_xlef = any(os.path.splitext(n)[1].lower() == ".xlef" for n in entries)
        for name in entries:
            low = name.lower()
            if ("metadata" in low or "_pmd_" in low or "_histo" in low or
                "_environmetalgraph" in low or low.endswith(".lifext") or
                low in ("iomanagerconfiguation", "iomanagerconfiguration")):
                continue
            full = os.path.join(parent_path, name)
            ext = os.path.splitext(name)[1].lower()
            if os.path.isdir(full):
                item = QTreeWidgetItem([name])
                item.setIcon(0, self.icon_folder())
                item.setData(0, Qt.ItemDataRole.UserRole, full)
                item.addChild(QTreeWidgetItem(["…"]))
                parent_item.addChild(item)
            else:
                if has_xlef and ext not in (".xlef",):
                    continue
                if ext in (".lif", ".xlef", ".lof"):
                    item = QTreeWidgetItem([name])
                    item.setIcon(0, self.icon_for_file(ext))
                    item.setData(0, Qt.ItemDataRole.UserRole, full)
                    parent_item.addChild(item)

    def on_fs_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        if os.path.isdir(path):
            self.current_dir = os.path.normpath(path)
            self.lbl_root.setText(f"Root: {self.current_dir}")
            self.populate_fs_root()
            self.tree_images.clear(); self._clear_image()
        else:
            self.load_file_images(path)

    def on_fs_selection_changed(self):
        items = self.tree_fs.selectedItems()
        if not items:
            return
        path = items[0].data(0, Qt.ItemDataRole.UserRole)
        if os.path.isfile(path):
            self.load_file_images(path)

    def load_file_images(self, filepath: str):
        self.current_file = filepath
        self.tree_images.clear(); self._clear_image()
        ext = os.path.splitext(filepath)[1].lower()
        try:
            if ext in (".lif", ".xlef"):
                meta_json = read_leica_file(filepath)
                root_item = QTreeWidgetItem([os.path.basename(filepath)])
                root_item.setData(0, Qt.ItemDataRole.UserRole + 1, "root")
                root_item.setData(0, Qt.ItemDataRole.UserRole + 2, filepath)
                root_item.setData(0, Qt.ItemDataRole.UserRole + 4, meta_json)
                root_item.setIcon(0, self.icon_for_file(ext))
                self.tree_images.addTopLevelItem(root_item)
                self.populate_children(root_item, meta_json)
                self.tree_images.expandItem(root_item)
            elif ext == ".lof":
                root_item = QTreeWidgetItem([os.path.basename(filepath)])
                root_item.setData(0, Qt.ItemDataRole.UserRole + 1, "root")
                root_item.setData(0, Qt.ItemDataRole.UserRole + 2, filepath)
                root_item.setIcon(0, self.icon_for_file(ext))
                img_item = QTreeWidgetItem([os.path.basename(filepath)])
                img_item.setData(0, Qt.ItemDataRole.UserRole + 1, "image")
                img_item.setData(0, Qt.ItemDataRole.UserRole + 2, filepath)
                img_item.setData(0, Qt.ItemDataRole.UserRole + 3, "__LOF__")
                img_item.setIcon(0, self.icon_image())
                root_item.addChild(img_item)
                self.tree_images.addTopLevelItem(root_item)
                self.tree_images.expandItem(root_item)
            else:
                self.append_log(f"Unsupported file type: {ext}")
        except Exception as e:
            self.append_log(f"Failed to read file metadata: {e}")

    def populate_children(self, parent_item: QTreeWidgetItem, folder_meta_json: str):
        try:
            meta = json.loads(folder_meta_json)
        except Exception:
            return
        for ch in meta.get("children", []):
            name = ch.get("name", "") or ch.get("ElementName", "")
            low = name.lower()
            if ("metadata" in low or "_pmd_" in low or "_histo" in low or
                "_environmetalgraph" in low or low.endswith(".lifext") or
                low in ("iomanagerconfiguation", "iomanagerconfiguration")):
                continue
            uuid = ch.get("uuid") or ""
            ctype = (ch.get("type") or "").lower()
            item = QTreeWidgetItem([name])
            if ctype in ("folder", "file"):
                item.setData(0, Qt.ItemDataRole.UserRole + 1, "folder")
                item.setIcon(0, self.icon_folder())
                item.addChild(QTreeWidgetItem(["…"]))
            else:
                item.setData(0, Qt.ItemDataRole.UserRole + 1, "image")
                item.setIcon(0, self.icon_image())
            item.setData(0, Qt.ItemDataRole.UserRole + 2, self.current_file)
            item.setData(0, Qt.ItemDataRole.UserRole + 3, uuid)
            parent_item.addChild(item)

    def on_tree_item_expanded(self, item: QTreeWidgetItem):
        kind = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if kind != "folder":
            return
        if item.childCount() == 1 and item.child(0).text(0) == "…":
            file_path = item.data(0, Qt.ItemDataRole.UserRole + 2)
            uuid = item.data(0, Qt.ItemDataRole.UserRole + 3)
            try:
                meta_json = read_leica_file(file_path, folder_uuid=uuid)
                item.setData(0, Qt.ItemDataRole.UserRole + 4, meta_json)
                item.removeChild(item.child(0))
                self.populate_children(item, meta_json)
            except Exception as e:
                self.append_log(f"Error expanding folder: {e}")

    # ---------- Image selection ----------
    def on_image_selection_changed(self):
        items = self.tree_images.selectedItems()
        if not items or not self.current_file:
            self.selected_image = None
            self._clear_image()
            return
        item = items[0]
        if item.data(0, Qt.ItemDataRole.UserRole + 1) != "image":
            self.selected_image = None
            self._clear_image()
            return

        name = item.text(0)
        uuid = item.data(0, Qt.ItemDataRole.UserRole + 3)
        ext = os.path.splitext(self.current_file)[1].lower()

        # Find folder metadata from ancestor or root
        folder_meta = None
        ancestor = item.parent()
        while ancestor is not None and folder_meta is None:
            folder_meta = ancestor.data(0, Qt.ItemDataRole.UserRole + 4)
            ancestor = ancestor.parent()

        try:
            if ext == ".lof" or uuid == "__LOF__":
                meta = json.loads(read_leica_file(self.current_file))
            elif ext == ".xlef":
                image_metadata_f = json.loads(get_image_metadata(folder_meta, uuid))
                lof_like = json.loads(get_image_metadata_LOF(folder_meta, uuid))
                if "save_child_name" in image_metadata_f:
                    lof_like["save_child_name"] = image_metadata_f["save_child_name"]
                meta = lof_like
            else:  # .lif
                meta = json.loads(read_leica_file(self.current_file, image_uuid=uuid))

            # Default indices and channel toggles
            self._init_indices_and_channels(meta)
            self.selected_image = ImageItem(name=name, uuid=uuid, meta=meta)
            self.last_image_meta_json = json.dumps(meta, indent=2)
            # Update left metadata and small preview
            self.left_meta.setText(self._format_meta_summary(meta))
            self._render_small_preview(meta)
            self._render_view()
            # After first render, set zoom to fit
            self._update_zoom_min()
            self._apply_zoom(self.zoom_slider.minimum())
        except Exception as e:
            self.append_log(f"Preview error: {e}")
            self._clear_image()

    # ---------- Controls ----------
    def _init_indices_and_channels(self, meta: dict):
        xs = int(meta.get("xs", 1) or 1)
        ys = int(meta.get("ys", 1) or 1)
        zs = int(meta.get("zs", 1) or 1)
        ts = int(meta.get("ts", 1) or 1)
        tiles = int(meta.get("tiles", 1) or 1)
        isrgb = bool(meta.get("isrgb", False))
        channels = 3 if isrgb else int(meta.get("channels", 1) or 1)

        # Init indices: Z=center, T=0, S=0
        self.idx_z = zs // 2 if zs > 0 else 0
        self.idx_t = 0
        self.idx_s = 0

        # Configure sliders
        # Z (vertical)
        self.z_slider_vert.blockSignals(True)
        self.z_slider_vert.setMinimum(0); self.z_slider_vert.setMaximum(max(0, zs - 1))
        self.z_slider_vert.setValue(self.idx_z)
        self.z_slider_vert.setEnabled(zs > 1)
        self.z_title.setVisible(zs > 1)
        self.z_slider_vert.setVisible(zs > 1)
        self.z_value_lbl.setVisible(zs > 1)
        self.z_value_lbl.setText(str(self.idx_z))
        self.z_slider_vert.blockSignals(False)
        # T
        t_w, t_s, t_val = self.slider_t
        t_s.blockSignals(True)
        t_s.setMinimum(0); t_s.setMaximum(max(0, ts - 1))
        t_s.setValue(self.idx_t)
        t_s.setEnabled(ts > 1)
        t_w.setVisible(ts > 1)
        t_val.setText(str(self.idx_t))
        t_s.blockSignals(False)
        # S (tiles)
        s_w, s_s, s_val = self.slider_s
        s_s.blockSignals(True)
        s_s.setMinimum(0); s_s.setMaximum(max(0, tiles - 1))
        s_s.setValue(self.idx_s)
        s_s.setEnabled(tiles > 1)
        s_w.setVisible(tiles > 1)
        s_val.setText(str(self.idx_s))
        s_s.blockSignals(False)

        # Channel toggle buttons
        # Clear existing
        for i in reversed(range(self.chan_row.count())):
            item = self.chan_row.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()
        self.channel_toggles = []

        for c in range(channels):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setText(f"C{c+1}")
            btn.clicked.connect(self.on_channels_changed)
            # Color cue with clear off-state (darker) and on-state (full color)
            r, g, b = self._channel_color(meta, c)
            btn.setStyleSheet(self._channel_button_stylesheet(r, g, b))
            self.chan_row.insertWidget(c, btn)
            self.channel_toggles.append(btn)
        self.chan_row.addStretch(1)

    def _channel_button_stylesheet(self, r: int, g: int, b: int) -> str:
        # Much darker color when unchecked
        dr = max(0, int(r * 0.25))
        dg = max(0, int(g * 0.25))
        db = max(0, int(b * 0.25))
        # Choose readable text colors
        def luminance(rr, gg, bb):
            return 0.299 * rr + 0.587 * gg + 0.114 * bb
        on_text = "#000" if luminance(r, g, b) > 160 else "#fff"
        off_text = "#bbb"
        return (
            "QToolButton {"
            f" background-color: rgb({dr}, {dg}, {db});"
            f" color: {off_text};"
            " border: 1px solid #555; border-radius: 4px; padding: 2px 6px;"
            "}"
            " QToolButton:checked {"
            f" background-color: rgb({r}, {g}, {b});"
            f" color: {on_text};"
            " border: 1px solid #aaa;"
            "}"
        )

    def on_slider_changed(self, value: int):  # noqa: ARG002
        if not self.selected_image:
            return
        # Update labels
        self.z_value_lbl.setText(str(self.z_slider_vert.value()))
        self.slider_t[2].setText(str(self.slider_t[1].value()))
        self.slider_s[2].setText(str(self.slider_s[1].value()))
        self.idx_z = self.z_slider_vert.value()
        self.idx_t = self.slider_t[1].value()
        self.idx_s = self.slider_s[1].value()
        self._render_view()

    def on_channels_changed(self):
        if not self.selected_image:
            return
        self._render_view()

    # ---------- Rendering ----------
    def _clear_image(self):
        self._pixmap = None  # type: ignore[attr-defined]
        self._pixmap_raw = None  # type: ignore[attr-defined]
        self.image_label.setPixmap(QPixmap())
        self.image_label.setText("Image will appear here")

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        try:
            self._update_zoom_min()
            self._update_image_view()
            # Keep centered when in Fit
            if self.zoom_slider.value() == self.zoom_slider.minimum():
                try:
                    hbar = self.image_scroll.horizontalScrollBar()
                    vbar = self.image_scroll.verticalScrollBar()
                    hbar.setValue((hbar.maximum() + hbar.minimum()) // 2)
                    vbar.setValue((vbar.maximum() + vbar.minimum()) // 2)
                except Exception:
                    pass
        except Exception:
            pass

    def _render_view(self):
        try:
            meta = self.selected_image.meta if self.selected_image else None
            if not meta:
                return
            # Render at full image resolution for pixel-accurate zoom (1.0 -> 100%)
            ys = int(meta.get("ys", 1) or 1)
            img = self._render_numpy_image(meta, self.idx_z, self.idx_t, self.idx_s, self._channel_mask(), ys)
            if img is None:
                self._clear_image(); return
            # Convert BGR uint8 to QPixmap
            if img.dtype != np.uint8:
                img8 = (img / 256).astype(np.uint8)
            else:
                img8 = img
            # BGR->RGB for Qt
            rgb = cv2.cvtColor(img8, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape
            qimg = QImage(rgb.data, w, h, 3*w, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            self._pixmap_raw = pix
            self._update_zoom_min()  # recompute fit minimum
            self._update_image_view()
        except Exception as e:
            self.append_log(f"Render error: {e}")

    def _update_image_view(self):
        try:
            if getattr(self, "_pixmap_raw", None):
                pix = self._pixmap_raw
                factor = max(0.1, self._zoom_factor)
                new_w = int(pix.width() * factor)
                new_h = int(pix.height() * factor)
                mode = Qt.TransformationMode.FastTransformation if int(self.zoom_slider.value()) >= 1000 else Qt.TransformationMode.SmoothTransformation
                scaled = pix.scaled(new_w, new_h, Qt.AspectRatioMode.KeepAspectRatio, mode)
                self._pixmap = scaled
                self.image_label.setPixmap(scaled)
                self.image_label.resize(scaled.size())
        except Exception:
            pass

    def on_zoom_changed(self, value: int):
        self._apply_zoom(value)

    def _apply_zoom(self, percent: int, anchor_in_viewport=None):
        try:
            percent = int(max(self.zoom_slider.minimum(), min(self.zoom_slider.maximum(), percent)))
            old_factor = max(0.001, self._zoom_factor)
            vp = self.image_scroll.viewport()
            if anchor_in_viewport is None:
                anchor_in_viewport = vp.rect().center()
            hbar = self.image_scroll.horizontalScrollBar()
            vbar = self.image_scroll.verticalScrollBar()
            content_anchor_x = hbar.value() + anchor_in_viewport.x()
            content_anchor_y = vbar.value() + anchor_in_viewport.y()

            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(percent)
            self.zoom_slider.blockSignals(False)
            self._zoom_factor = float(percent) / 100.0
            self.zoom_value_lbl.setText(f"{percent}%")

            self._update_image_view()

            ratio = self._zoom_factor / old_factor
            new_anchor_x = int(content_anchor_x * ratio)
            new_anchor_y = int(content_anchor_y * ratio)
            hbar.setValue(max(0, new_anchor_x - anchor_in_viewport.x()))
            vbar.setValue(max(0, new_anchor_y - anchor_in_viewport.y()))
            # If fit zoom selected, center content explicitly
            if percent == self.zoom_slider.minimum():
                try:
                    hbar.setValue((hbar.maximum() + hbar.minimum()) // 2)
                    vbar.setValue((vbar.maximum() + vbar.minimum()) // 2)
                except Exception:
                    pass
        except Exception:
            pass

    def _update_zoom_min(self):
        try:
            if getattr(self, "_pixmap_raw", None):
                pix = self._pixmap_raw
                vp = self.image_scroll.viewport()
                if pix.width() <= 0 or pix.height() <= 0 or vp.width() <= 0 or vp.height() <= 0:
                    return
                fit_w = vp.width() / float(pix.width())
                fit_h = vp.height() / float(pix.height())
                fit = min(fit_w, fit_h)
                min_percent = max(10, int(round(min(fit, 1.0) * 100)))
                old_min, old_max = self.zoom_slider.minimum(), self.zoom_slider.maximum()
                if min_percent != old_min or old_max != 1000:
                    cur = self.zoom_slider.value()
                    self.zoom_slider.blockSignals(True)
                    self.zoom_slider.setRange(min_percent, 1000)
                    if cur < min_percent:
                        self.zoom_slider.setValue(min_percent)
                        self._zoom_factor = min_percent / 100.0
                        self.zoom_value_lbl.setText(f"{min_percent}%")
                    self.zoom_slider.blockSignals(False)
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802
        # Zoom with wheel, pan with drag
        from PyQt6.QtCore import QEvent
        if obj in (self.image_label, self.image_scroll.viewport()):
            if event.type() == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                step = 5 if delta > 0 else -5
                new_val = self.zoom_slider.value() + step
                self._apply_zoom(int(new_val), anchor_in_viewport=event.position().toPoint())
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._dragging = True
                # Use viewport coordinates for consistent scroll bars movement
                self._last_pos = event.position().toPoint()
                self.image_scroll.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            if event.type() == QEvent.Type.MouseMove and self._dragging and self._last_pos is not None:
                pos = event.position().toPoint()
                dx = pos.x() - self._last_pos.x()
                dy = pos.y() - self._last_pos.y()
                hbar = self.image_scroll.horizontalScrollBar()
                vbar = self.image_scroll.verticalScrollBar()
                hbar.setValue(hbar.value() - dx)
                vbar.setValue(vbar.value() - dy)
                self._last_pos = pos
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                self._dragging = False
                self._last_pos = None
                self.image_scroll.viewport().setCursor(Qt.CursorShape.ArrowCursor)
                return True
        return super().eventFilter(obj, event)

    def _render_small_preview(self, meta: dict):
        try:
            img = self._render_numpy_image(meta, meta.get('zs', 1)//2 if meta.get('zs', 1) else 0, 0, 0, self._channel_mask(), 100)
            if img is None:
                self.left_preview.clear(); self.left_preview.setText("Preview"); return
            if img.dtype != np.uint8:
                img8 = (img / 256).astype(np.uint8)
            else:
                img8 = img
            rgb = cv2.cvtColor(img8, cv2.COLOR_BGR2RGB)
            h, w, _ = rgb.shape
            qimg = QImage(rgb.data, w, h, 3*w, QImage.Format.Format_RGB888)
            pix = QPixmap.fromImage(qimg)
            self.left_preview.setPixmap(pix.scaled(self.left_preview.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except Exception:
            self.left_preview.setText("Preview error")

    def _channel_mask(self) -> List[bool]:
        return [btn.isChecked() for btn in self.channel_toggles] if self.channel_toggles else []

    def _channel_color(self, meta: dict, idx: int) -> tuple[int, int, int]:
        try:
            lut_list = meta.get("lutname")
            if isinstance(lut_list, list) and idx < len(lut_list):
                return convert_color_name_to_rgb(lut_list[idx])
        except Exception:
            pass
        default_cycle = [(0,255,0),(255,0,255),(0,255,255),(255,255,0),(255,0,0),(0,0,255),(255,255,255)]
        return default_cycle[idx % len(default_cycle)]

    def _render_numpy_image(self, metadata: dict, z: int, t: int, s: int, channel_mask: List[bool], preview_height: int):
        # Normalize metadata (string -> dict OK)
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        filetype = metadata.get("filetype")
        if filetype not in (".lif", ".xlef", ".lof"):
            return None
        if filetype == ".lif":
            fileName = metadata.get("LIFFile") or metadata.get("LOFFilePath")
            basePos = int(metadata.get("Position", 0) or 0)
        else:
            fileName = metadata.get("LOFFilePath")
            basePos = 62
        if not fileName or not os.path.exists(fileName):
            return None

        xs = int(metadata.get("xs", 1) or 1)
        ys = int(metadata.get("ys", 1) or 1)
        zs = int(metadata.get("zs", 1) or 1)
        ts = int(metadata.get("ts", 1) or 1)
        tiles = int(metadata.get("tiles", 1) or 1)
        isrgb = bool(metadata.get("isrgb", False))
        channels = 3 if isrgb else int(metadata.get("channels", 1) or 1)

        # Bounds check
        z = max(0, min(z, max(0, zs-1)))
        t = max(0, min(t, max(0, ts-1)))
        s = max(0, min(s, max(0, tiles-1)))

        # channel resolution handling
        res = metadata.get("channelResolution", 8)
        if isinstance(res, list) and res:
            b0 = int(res[0] or 8)
        else:
            try:
                b0 = int(res)
            except Exception:
                b0 = 8
        dtype, bytes_per_pixel, max_pixel_value = (np.uint8, 1, 255) if b0 <= 8 else (np.uint16, 2, 65535)

        # Offsets
        channelbytesinc = metadata.get("channelbytesinc") or [0] * channels
        zbytesinc = int(metadata.get("zbytesinc", 0) or 0)
        tbytesinc = int(metadata.get("tbytesinc", 0) or 0)
        tilesbytesinc = int(metadata.get("tilesbytesinc", 0) or 0)
        base = basePos + t * tbytesinc + s * tilesbytesinc + z * zbytesinc

        # Resize parameters
        tscale = float(preview_height) / float(ys)
        ysize = int(preview_height)
        xsize = max(1, int(round(xs * tscale)))

        if isrgb:
            shape = (ys, xs, 3)
            arr = np.memmap(fileName, dtype=dtype, mode="r", offset=base, shape=shape, order="C")
            selected = cv2.resize(arr, (xsize, ysize), interpolation=cv2.INTER_AREA)
            # Apply mask per channel (R,G,B). Our array is assumed BGR as in CreatePreview path to cv2.imwrite.
            mask = channel_mask if channel_mask else [True, True, True]
            # Build a BGR mask vector
            bgr_mask = np.array([1 if mask[2] else 0, 1 if mask[1] else 0, 1 if mask[0] else 0], dtype=np.float32)
            out = (selected.astype(np.float32) * bgr_mask.reshape((1,1,3)))
            out = np.clip(out, 0, max_pixel_value).astype(dtype)
            out = adjust_image_contrast(out, max_pixel_value)
            return out

        # Multichannel overlay
        acc = np.zeros((ysize, xsize, 3), dtype=np.float32)
        if not channel_mask or len(channel_mask) < channels:
            channel_mask = [True] * channels
        for c in range(channels):
            if not channel_mask[c]:
                continue
            c_off = base + int(channelbytesinc[c] if c < len(channelbytesinc) and channelbytesinc[c] is not None else 0)
            slice_shape = (ys, xs)
            mmap_array = np.memmap(fileName, dtype=dtype, mode="r", offset=c_off, shape=slice_shape, order="C")
            plane = cv2.resize(mmap_array, (xsize, ysize), interpolation=cv2.INTER_AREA)
            r, g, b = self._channel_color(metadata, c)  # RGB
            acc[:, :, 0] += plane * (b / 255.0)  # B
            acc[:, :, 1] += plane * (g / 255.0)  # G
            acc[:, :, 2] += plane * (r / 255.0)  # R
        acc = np.clip(acc, 0, max_pixel_value).astype(dtype)
        acc = adjust_image_contrast(acc, max_pixel_value)
        return acc

    # ---------- Metadata ----------
    def _format_meta_summary(self, meta: dict) -> str:
        def pick(*keys, default=None):
            for k in keys:
                if k in meta and meta[k] is not None:
                    return meta[k]
            return default
        xs = pick('xs'); ys = pick('ys'); zs = pick('zs'); ts = pick('ts'); cs = pick('channels'); ss = pick('tiles')
        if xs is None or ys is None:
            dims = meta.get('dimensions') or {}
            xs = xs if xs is not None else dims.get('x')
            ys = ys if ys is not None else dims.get('y')
            zs = zs if zs is not None else dims.get('z')
            ts = ts if ts is not None else dims.get('t')
            cs = cs if cs is not None else dims.get('c')
            ss = ss if ss is not None else dims.get('s')
        dims_parts = []
        if xs and ys: dims_parts.append(f"{xs}×{ys}")
        if zs: dims_parts.append(f"Z={zs}")
        if ts: dims_parts.append(f"T={ts}")
        if cs: dims_parts.append(f"C={cs}")
        if ss: dims_parts.append(f"S={ss}")
        vx = pick('xres2'); vy = pick('yres2'); vz = pick('zres2'); vunit = pick('resunit2', default='µm')
        def fmt2(v):
            try:
                return f"{float(v):.2f}"
            except Exception:
                return str(v)
        scale_parts = []
        if vx: scale_parts.append(f"X={fmt2(vx)} {vunit}")
        if vy: scale_parts.append(f"Y={fmt2(vy)} {vunit}")
        if vz: scale_parts.append(f"Z={fmt2(vz)} {vunit}")
        lines = [
            f"Dimensions: {'  '.join(dims_parts) if dims_parts else '(n/a)'}",
            f"Voxel size: {', '.join(scale_parts) if scale_parts else '(n/a)'}",
        ]
        return "\n".join(lines)

    # ---------- Misc ----------
    def choose_root(self):
        from PyQt6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Choose root folder", self.current_dir)
        if d:
            self.current_dir = os.path.normpath(d)
            self.lbl_root.setText(f"Root: {self.current_dir}")
            self.populate_fs_root()
            self.tree_images.clear(); self._clear_image()

    def show_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Leica Viewer — Help")
        v = QVBoxLayout(dlg)
        browser = QTextBrowser(dlg); browser.setOpenExternalLinks(True)
        try:
            html_path = Path(__file__).with_name("ConvertLeicaQTHelp.html")
            if html_path.exists():
                browser.setHtml(html_path.read_text(encoding='utf-8'))
            else:
                browser.setHtml("<h2>Help file not found</h2><p>Expected ConvertLeicaQTHelp.html next to the application.</p>")
        except Exception as e:
            browser.setHtml(f"<h2>Error loading help</h2><pre>{e}</pre>")
        v.addWidget(browser)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dlg)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        dlg.resize(900, 700)
        dlg.exec()


def main() -> None:
    app = QApplication(sys.argv)
    apply_dark_theme(app)
    win = LeicaViewerApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":  # pragma: no cover
    main()
