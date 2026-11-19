"""GUI (PySide6 / Qt) cho AutoSearch.

Da luong: moi proxy chay tren 1 thiet bi rieng (1 cap = 1 thread).

Chay:
    python gui.py

Import file nay khong mo cua so (cua so chi tao trong main()).
"""

import sys
import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import auto

QSS = """
QWidget#Root { background: #0f1116; }
QLabel#Title { font-size: 24px; font-weight: 700; color: #f3f5f9; }
QLabel#Subtitle { color: #7d869c; font-size: 12px; }
QFrame#Card { background: #171a21; border: 1px solid #262b36; border-radius: 12px; }
QLabel#FieldLabel { color: #9aa4bb; font-size: 12px; font-weight: 600; }
QLabel#Hint { color: #6b748c; font-size: 11px; }
QLabel#Plan { color: #93c5fd; font-size: 12px; font-weight: 600; }
QLabel#SectionTitle { color: #cbd3e3; font-size: 12px; font-weight: 700; letter-spacing: 1px; }

QLineEdit, QPlainTextEdit {
    background: #101319;
    border: 1px solid #2b3140;
    border-radius: 8px;
    padding: 8px 10px;
    color: #e8ebf2;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
}
QLineEdit:hover, QPlainTextEdit:hover { border: 1px solid #3a4356; }
QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #3b82f6; background: #0d1016; }

QListWidget {
    background: #101319;
    border: 1px solid #2b3140;
    border-radius: 8px;
    color: #e8ebf2;
    padding: 4px;
    outline: none;
}
QListWidget::item { padding: 5px 6px; border-radius: 6px; }
QListWidget::item:hover { background: #1b2130; }
QListWidget::item:selected { background: #1e293b; color: #ffffff; }
QListWidget::item:disabled { color: #5c6478; }
QListWidget::indicator { width: 15px; height: 15px; }
QListWidget::indicator:unchecked {
    border: 1px solid #3f4859; background: #0c0e13; border-radius: 4px;
}
QListWidget::indicator:checked {
    border: 1px solid #2563eb; background: #2563eb; border-radius: 4px;
    image: url(none);
}

QPushButton {
    background: #232936;
    color: #e8ebf2;
    border: 1px solid #2f3648;
    border-radius: 8px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover { background: #2b3242; border-color: #3c465c; }
QPushButton:pressed { background: #1d2230; }
QPushButton:disabled { color: #5c6478; background: #1b1f28; border-color: #242a36; }

QPushButton#Primary { background: #2563eb; border: 1px solid #2563eb; color: #ffffff; }
QPushButton#Primary:hover { background: #3b82f6; border-color: #3b82f6; }
QPushButton#Primary:pressed { background: #1d4ed8; }
QPushButton#Primary:disabled { background: #1e293b; border-color: #1e293b; color: #64748b; }

QPushButton#Danger { color: #fca5a5; border: 1px solid #4a2833; }
QPushButton#Danger:hover { background: #2a1a20; border-color: #71323f; }
QPushButton#Danger:disabled { color: #5c6478; border-color: #242a36; background: #1b1f28; }

QLabel#Status {
    color: #8b93a7;
    font-size: 12px;
    padding: 6px 14px;
    background: #171a21;
    border: 1px solid #262b36;
    border-radius: 12px;
}

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #333b4d; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #43506b; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal { height: 10px; margin: 2px; background: transparent; }
QScrollBar::handle:horizontal { background: #333b4d; border-radius: 5px; min-width: 24px; }
"""


class Bridge(QObject):
    """Cau noi worker thread -> UI thread (Qt signal thread-safe)."""

    log = Signal(str)
    devices = Signal(list)
    job_done = Signal(str, bool, str)
    all_done = Signal(int, int)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle("AdsSearch - @HIEUSOFT")
        self.resize(940, 760)
        self.setMinimumSize(820, 620)

        self.running = False
        self._total = 0
        self._finished = 0

        self.bridge = Bridge()
        self.bridge.log.connect(self.append_log)
        self.bridge.devices.connect(self._on_devices)
        self.bridge.job_done.connect(self._on_job_done)
        self.bridge.all_done.connect(self._on_all_done)
        auto.set_logger(self.bridge.log.emit)

        self._build_ui()
        QTimer.singleShot(250, self.refresh_devices)

    # ---------------- UI ----------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

      
        card = QFrame()
        card.setObjectName("Card")
        grid = QGridLayout(card)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)

        # --- Thiet bi ---
        grid.addWidget(self._field_label("THIẾT BỊ"), 0, 0, Qt.AlignTop)
        self.device_list = QListWidget()
        self.device_list.setFixedHeight(112)
        self.device_list.itemChanged.connect(lambda _i: self._update_plan())
        grid.addWidget(self.device_list, 0, 1)

        side = QVBoxLayout()
        side.setSpacing(6)
        self.scan_btn = QPushButton("Quét thiết bị")
        self.scan_btn.setMinimumSize(150, 32)
        self.scan_btn.setCursor(Qt.PointingHandCursor)
        self.scan_btn.clicked.connect(self.refresh_devices)

        self.all_btn = QPushButton("Chọn tất cả")
        self.all_btn.setMinimumHeight(32)
        self.all_btn.setCursor(Qt.PointingHandCursor)
        self.all_btn.clicked.connect(lambda: self._check_all(True))

        self.none_btn = QPushButton("Bỏ chọn")
        self.none_btn.setMinimumHeight(32)
        self.none_btn.setCursor(Qt.PointingHandCursor)
        self.none_btn.clicked.connect(lambda: self._check_all(False))

        side.addWidget(self.scan_btn)
        side.addWidget(self.all_btn)
        side.addWidget(self.none_btn)
        side.addStretch(1)
        grid.addLayout(side, 0, 2)

        # --- Keyword ---
        grid.addWidget(self._field_label("KEYWORD"), 1, 0)
        self.keyword_edit = QLineEdit(auto.DEFAULT_KEYWORD)
        self.keyword_edit.setMinimumHeight(38)
        self.keyword_edit.setPlaceholderText("Từ khoá cần search trên Google")
        self.keyword_edit.returnPressed.connect(self.start)
        grid.addWidget(self.keyword_edit, 1, 1, 1, 2)

        # --- Proxy ---
        grid.addWidget(self._field_label("PROXY"), 2, 0, Qt.AlignTop)
        self.proxy_edit = QPlainTextEdit(self._safe_read_proxies())
        self.proxy_edit.setFixedHeight(104)
        self.proxy_edit.setPlaceholderText("Mỗi dòng 1 proxy: ip:port:user:pass")
        font = QFont("Consolas", 9)
        font.setStyleHint(QFont.Monospace)
        self.proxy_edit.setFont(font)
        self.proxy_edit.textChanged.connect(self._update_plan)
        grid.addWidget(self.proxy_edit, 2, 1, 1, 2)

        hint = QLabel(
            "Mỗi dòng 1 proxy (ip:port:user:pass). "
            "Proxy thứ i chạy trên thiết bị được tick thứ i — số luồng = min(số proxy, số thiết bị)."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        grid.addWidget(hint, 3, 1, 1, 2)

        self.plan_label = QLabel("")
        self.plan_label.setObjectName("Plan")
        grid.addWidget(self.plan_label, 4, 1, 1, 2)

        root.addWidget(card)

        # --- Thanh nut ---
        bar = QHBoxLayout()
        bar.setSpacing(10)

        self.run_btn = QPushButton("Chạy")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setMinimumSize(120, 40)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.start)

        self.stop_btn = QPushButton("Dừng")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.setMinimumSize(100, 40)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop)

        self.clear_btn = QPushButton("Xoá log")
        self.clear_btn.setMinimumHeight(40)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.clicked.connect(self.clear_log)

        self.status = QLabel("Sẵn sàng")
        self.status.setObjectName("Status")

        bar.addWidget(self.run_btn)
        bar.addWidget(self.stop_btn)
        bar.addWidget(self.clear_btn)
        bar.addStretch(1)
        bar.addWidget(self.status)
        root.addLayout(bar)

        # --- Log ---
        log_title = QLabel("LOG")
        log_title.setObjectName("SectionTitle")
        root.addWidget(log_title)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)
        log_font = QFont("Consolas", 9)
        log_font.setStyleHint(QFont.Monospace)
        self.log_view.setFont(log_font)
        root.addWidget(self.log_view, 1)

    @staticmethod
    def _field_label(text):
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        label.setFixedWidth(84)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        return label

    @staticmethod
    def _safe_read_proxies():
        try:
            return "\n".join(auto.read_proxies())
        except Exception:
            return ""

    # ---------------- Log / status ----------------
    def append_log(self, msg):
        self.log_view.appendPlainText(str(msg))

    def clear_log(self):
        self.log_view.clear()

    def _set_status(self, text, busy=False):
        self.status.setText(text)
        self.status.setStyleSheet("color: #93c5fd;" if busy else "")

    # ---------------- Ke hoach chay ----------------
    def _checked_serials(self):
        serials = []
        for i in range(self.device_list.count()):
            item = self.device_list.item(i)
            if item.checkState() == Qt.Checked and item.data(Qt.UserRole):
                serials.append(item.data(Qt.UserRole))
        return serials

    def _update_plan(self):
        proxies = auto.proxy_lines(self.proxy_edit.toPlainText())
        serials = self._checked_serials()
        n = min(len(proxies), len(serials))
        self.plan_label.setText(
            f"{len(proxies)} proxy  •  {len(serials)} thiết bị  →  {n} luồng song song"
        )

    # ---------------- Quet thiet bi ----------------
    def refresh_devices(self):
        if self.running:
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Đang quét...")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            devices = auto.scan_devices()
        except Exception as e:
            self.bridge.log.emit(f"[scan] lỗi: {e}")
            devices = []
        self.bridge.devices.emit(devices)

    def _on_devices(self, devices):
        checked = set(self._checked_serials())
        self.device_list.blockSignals(True)
        self.device_list.clear()
        for serial, state in devices:
            item = QListWidgetItem(f"{serial}    •  {state}")
            item.setData(Qt.UserRole, serial)
            if state == "device":
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                # giu lua chon cu, mac dinh tick het may online
                item.setCheckState(Qt.Checked if (not checked or serial in checked) else Qt.Unchecked)
            else:
                item.setFlags(Qt.NoItemFlags)
                item.setCheckState(Qt.Unchecked)
            self.device_list.addItem(item)
        self.device_list.blockSignals(False)

        online = sum(1 for _s, st in devices if st == "device")
        if online:
            self.append_log(f"[scan] tìm thấy {online} thiết bị sẵn sàng")
        else:
            self.append_log("[scan] không thấy thiết bị nào (kiểm tra adb devices)")

        self.scan_btn.setEnabled(not self.running)
        self.scan_btn.setText("Quét thiết bị")
        self._update_plan()

    def _check_all(self, state):
        self.device_list.blockSignals(True)
        for i in range(self.device_list.count()):
            item = self.device_list.item(i)
            if item.flags() & Qt.ItemIsUserCheckable:
                item.setCheckState(Qt.Checked if state else Qt.Unchecked)
        self.device_list.blockSignals(False)
        self._update_plan()

    # ---------------- Chay / dung ----------------
    def start(self):
        if self.running:
            return

        keyword = self.keyword_edit.text().strip()
        if not keyword:
            QMessageBox.warning(self, "Thiếu keyword", "Nhập keyword trước khi chạy.")
            return

        proxies = auto.proxy_lines(self.proxy_edit.toPlainText())
        if not proxies:
            QMessageBox.warning(self, "Thiếu proxy", "Nhập ít nhất 1 dòng proxy.")
            return

        bad = []
        for line in proxies:
            try:
                auto.parse_proxy(line)
            except Exception:
                bad.append(line)
        if bad:
            QMessageBox.critical(
                self,
                "Proxy sai định dạng",
                "Các dòng sau không đúng ip:port:user:pass:\n\n" + "\n".join(bad[:8]),
            )
            return

        serials = self._checked_serials()
        if not serials:
            QMessageBox.warning(self, "Chưa chọn thiết bị", "Tick ít nhất 1 thiết bị.")
            return

        n = min(len(proxies), len(serials))
        if len(proxies) != len(serials):
            ok = QMessageBox.question(
                self,
                "Số lượng lệch",
                f"Có {len(proxies)} proxy nhưng {len(serials)} thiết bị được chọn.\n"
                f"Sẽ chạy {n} luồng (1 proxy : 1 thiết bị).\n\nTiếp tục?",
            )
            if ok != QMessageBox.Yes:
                return

        self._total = n
        self._finished = 0
        self.running = True
        self._set_running(True)
        self._set_status(f"0/{n} luồng xong", busy=True)
        self.append_log("═" * 70)
        self.append_log(f"[gui] chạy {n} luồng, keyword={keyword!r}")

        threading.Thread(
            target=self._run_worker,
            args=(keyword, proxies[:n], serials[:n]),
            daemon=True,
        ).start()

    def _run_worker(self, keyword, proxies, serials):
        ok, total = 0, len(proxies)
        try:
            results = auto.run_jobs(
                keyword,
                proxies,
                serials,
                on_job_done=lambda tag, done_ok, err: self.bridge.job_done.emit(
                    tag, done_ok, err or ""
                ),
            )
            ok = sum(1 for v in results.values() if v)
            total = len(results) or total
        except Exception as e:
            self.bridge.log.emit(f"[gui] LỖI: {e}")
        finally:
            self.bridge.all_done.emit(ok, total)

    def _on_job_done(self, tag, ok, err):
        self._finished += 1
        state = "OK" if ok else ("DỪNG" if err == "da dung" else "LỖI")
        self.append_log(f"[gui] {tag} → {state}")
        if self.running:
            self._set_status(f"{self._finished}/{self._total} luồng xong", busy=True)

    def _on_all_done(self, ok, total):
        self.running = False
        self._set_running(False)
        self._set_status(f"Xong: {ok}/{total} thành công")
        self.append_log(f"[gui] kết thúc: {ok}/{total} luồng thành công")
        self._update_plan()

    def stop(self):
        if not self.running:
            return
        auto.stop_all()
        self.stop_btn.setEnabled(False)
        self._set_status("Đang dừng...", busy=True)
        self.append_log("[gui] yêu cầu dừng — chờ các luồng kết thúc")

    def _set_running(self, running):
        self.run_btn.setEnabled(not running)
        self.run_btn.setText("Đang chạy..." if running else "Chạy")
        self.stop_btn.setEnabled(running)
        self.scan_btn.setEnabled(not running)
        self.keyword_edit.setEnabled(not running)
        self.proxy_edit.setEnabled(not running)
        self.device_list.setEnabled(not running)
        self.all_btn.setEnabled(not running)
        self.none_btn.setEnabled(not running)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # nen tang de QSS dark hien thi on dinh
    app.setStyleSheet(QSS)

    icon_path = auto.BASE_DIR / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
