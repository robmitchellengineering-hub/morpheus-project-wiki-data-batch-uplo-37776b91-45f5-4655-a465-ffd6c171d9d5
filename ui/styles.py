GLOBAL_STYLESHEET = """
QWidget {
    background-color: #f8f9fa;
    color: #202122;
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 14px;
}

QMainWindow {
    background-color: #f8f9fa;
}

QMenuBar {
    background-color: #f8f9fa;
    border-bottom: 1px solid #c8ccd1;
    padding: 2px;
}

QMenuBar::item {
    spacing: 3px;
    padding: 4px 8px;
    background: transparent;
    border-radius: 2px;
}

QMenuBar::item:selected {
    background: #eaf3ff;
    color: #0645ad;
}

QMenu {
    background-color: #ffffff;
    border: 1px solid #c8ccd1;
}

QMenu::item {
    padding: 6px 20px;
}

QMenu::item:selected {
    background-color: #eaf3ff;
    color: #0645ad;
}

QListWidget {
    background-color: #ffffff;
    border: 1px solid #c8ccd1;
    border-radius: 2px;
    padding: 4px;
    outline: none;
}

QListWidget::item {
    padding: 6px;
    border-bottom: 1px solid #f0f0f0;
}

QListWidget::item:selected {
    background-color: #eaf3ff;
    color: #202122;
    border-left: 3px solid #0645ad;
}

QListWidget::item:hover {
    background-color: #f8f9fa;
}

QLabel {
    background: transparent;
    color: #202122;
}

QLabel#placeholder {
    font-size: 16px;
    color: #72777d;
}

QPushButton {
    background-color: #f8f9fa;
    border: 1px solid #a2a9b1;
    border-radius: 2px;
    padding: 6px 12px;
    color: #202122;
}

QPushButton:hover {
    background-color: #ffffff;
    border-color: #72777d;
}

QPushButton:pressed {
    background-color: #eaf3ff;
    border-color: #0645ad;
}

QPushButton:default {
    background-color: #eaf3ff;
    border-color: #0645ad;
    color: #0645ad;
    font-weight: bold;
}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #a2a9b1;
    border-radius: 2px;
    padding: 4px;
    selection-background-color: #0645ad;
    selection-color: #ffffff;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #0645ad;
    outline: none;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #a2a9b1;
}

QScrollBar:vertical {
    background: #f8f9fa;
    width: 12px;
    border: none;
}

QScrollBar::handle:vertical {
    background: #c8ccd1;
    min-height: 20px;
    border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
    background: #a2a9b1;
}

QScrollBar:horizontal {
    background: #f8f9fa;
    height: 12px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #c8ccd1;
    min-width: 20px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal:hover {
    background: #a2a9b1;
}

QToolTip {
    background-color: #ffffff;
    color: #202122;
    border: 1px solid #c8ccd1;
    padding: 4px;
}

QTableView {
    background-color: #ffffff;
    alternate-background-color: #f8f9fa;
    gridline-color: #c8ccd1;
    border: 1px solid #c8ccd1;
    border-radius: 2px;
    selection-background-color: #eaf3ff;
    selection-color: #202122;
}

QTableView::item {
    padding: 4px;
}

QTableView::item:selected {
    background-color: #eaf3ff;
    color: #202122;
    border: none;
}

QHeaderView::section {
    background-color: #0645ad;
    color: #ffffff;
    font-weight: bold;
    padding: 6px;
    border: none;
    border-right: 1px solid #2a62b3;
}

QHeaderView::section:last {
    border-right: none;
}

QTableCornerButton::section {
    background-color: #0645ad;
    border: none;
}
"""

global_stylesheet = GLOBAL_STYLESHEET
