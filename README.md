# AdsSearch

Tool tự động hoá Android: cấu hình proxy trong **Super Proxy**, search Google trên **Chrome**,
bấm vào **kết quả được tài trợ (quảng cáo)** rồi cuộn trang như người dùng thật.

Hỗ trợ **đa luồng: mỗi proxy chạy trên 1 thiết bị riêng, song song**.

## Tính năng

- Quét & chọn nhiều thiết bị Android (adb), mỗi thiết bị 1 luồng.
- Đọc danh sách proxy từng dòng: `ip:port:user:pass`.
- Xoá dữ liệu Super Proxy → thêm proxy HTTP (kèm user/pass) → Start → cấp quyền VPN.
- Xoá dữ liệu Chrome → search keyword → nhận diện **quảng cáo bằng attribute HTML**
  (`data-text-ad`, `#tads`, `#tadsb`, `data-pcu`, `data-rw`, `/aclk`) nên **không phụ thuộc ngôn ngữ**
  ("Được tài trợ" / "Sponsored" đều được).
- Cuộn quảng cáo vào giữa màn hình, hit-test rồi tap đúng toạ độ; nếu vẫn ở trang kết quả thì mở trực tiếp link.
- Vuốt lên 5 lần (3 + 2) với vị trí/thời gian random — không bao giờ chạm pull-to-refresh.
- GUI PySide6 (dark theme), log realtime, có nút Dừng.

## Yêu cầu

- Windows + Python 3.10+
- Android SDK platform-tools (adb) trên PATH, hoặc dùng adb đi kèm adbutils
- Thiết bị/emulator bật USB debugging

```bash
pip install -r requirements.txt
```

## Cài đặt & chạy

```bash
# 1. Tạo file proxy.txt cạnh auto.py (mỗi dòng 1 proxy)
copy proxy.txt.example proxy.txt

# 2. Chạy GUI
python gui.py

# hoặc chạy CLI 1 thiết bị
python auto.py
```

### proxy.txt

```
ip:port:user:pass
ip:port:user:pass
```

Dòng trống và dòng bắt đầu bằng `#` sẽ bị bỏ qua. **Không commit file này** (đã có trong `.gitignore`).

## Đóng gói EXE

```bat
build.bat
```

Kết quả: `output\AutoSearch\AutoSearch.exe` (onedir). Zip **cả thư mục** `output\AutoSearch` để phát hành.
`proxy.txt` và `icon.ico` nằm cạnh EXE; rebuild không ghi đè `proxy.txt` đã có.

Quy trình trong `build.bat`:

1. Cài `pyinstaller` + `pyarmor`
2. `pyarmor gen` obfuscate `gui.py`, `auto.py` (lỗi thì fallback dùng source gốc)
3. PyInstaller `--onedir --noconsole --windowed --contents-directory lib`
4. Copy `icon.ico`, `proxy.txt` ra cạnh EXE

## Cấu trúc

| File | Mô tả |
|---|---|
| `gui.py` | GUI PySide6, đa luồng, log qua Qt signal |
| `auto.py` | Toàn bộ logic: proxy, Chrome, CDP, click quảng cáo, vuốt |
| `build.bat` | Script đóng gói EXE |
| `icon.ico` | Icon app |
| `proxy.txt` | Danh sách proxy (không commit) |

## Ghi chú kỹ thuật

- Đọc HTML thật của tab Chrome qua **Chrome DevTools Protocol** (`chrome_devtools_remote` → `tcp:9222+`).
- Mỗi thiết bị dùng 1 port CDP riêng (9222, 9223, ...) nên chạy song song không đụng nhau.
- `/json/list` trả URL cũ sau khi điều hướng → luôn hỏi `location.href` qua CDP.
- Đường dẫn dữ liệu dùng `sys.frozen` để đọc `proxy.txt` cạnh `.exe` sau khi đóng gói.
