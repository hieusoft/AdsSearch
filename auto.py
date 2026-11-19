"""AutoSearch: cau hinh proxy -> search Google -> bam ket qua duoc tai tro -> cuon trang.

Dung duoc 2 cach:
    - CLI : python auto.py
    - GUI : python gui.py

Da luong: moi proxy chay tren 1 thiet bi rieng, moi cap (proxy, thiet bi) la 1 thread.
"""

import json
import os
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

# Chon adb cho adbutils: uu tien ADBUTILS_ADB_PATH -> adb tren PATH (vd MuMu)
# -> cuoi cung la adb bundled cua adbutils. Phai set TRUOC khi import uiautomator2.
if not os.environ.get("ADBUTILS_ADB_PATH"):
    _adb_on_path = shutil.which("adb")
    if _adb_on_path:
        os.environ["ADBUTILS_ADB_PATH"] = _adb_on_path

import uiautomator2 as u2

try:
    import websocket  # websocket-client: pip install websocket-client
except ImportError:
    websocket = None


def app_dir():
    """Thu muc lam viec: canh file .py, hoac canh .exe khi da dong goi."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()
PROXY_FILE = BASE_DIR / "proxy.txt"

PROXY_APP = "com.scheler.superproxy"
CHROME_APP = "com.android.chrome"

DEFAULT_KEYWORD = "echo water"
SEARCH_URL = "https://www.google.com/search?q={}"

# Moi thiet bi can 1 port CDP rieng: 9222, 9223, 9224...
CDP_BASE_PORT = 9222
CDP_SOCKET = "localabstract:chrome_devtools_remote"

# --- Logger: CLI dung print, GUI thay bang callback ---
_log_fn = None


def set_logger(fn):
    """GUI goi ham nay de huong log ve Text widget."""
    global _log_fn
    _log_fn = fn


def log(msg):
    if _log_fn is not None:
        _log_fn(str(msg))
    else:
        print(msg, flush=True)


# --- Co dung khan cap (nut Dung tren GUI) ---
_STOP = threading.Event()


def reset_stop():
    _STOP.clear()


def stop_all():
    _STOP.set()


def should_stop():
    return _STOP.is_set()


class Aborted(Exception):
    """Nguoi dung bam Dung."""


# --- Proxy ---
def parse_proxy(line):
    """Tach 'ip:port:user:pass' -> tuple."""
    ip, port, username, password = line.strip().split(":", 3)
    return ip, port, username, password


def read_proxies():
    """Doc tat ca dong proxy hop le trong proxy.txt (bo dong trong va dong #)."""
    if not PROXY_FILE.exists():
        raise RuntimeError(f"khong thay file {PROXY_FILE}")
    result = []
    for line in PROXY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            result.append(line)
    if not result:
        raise RuntimeError("proxy.txt rong")
    return result


def read_proxy():
    """Doc dong proxy dau tien trong proxy.txt."""
    return read_proxies()[0]


def proxy_lines(text):
    """Tach text nhieu dong -> danh sach proxy hop le."""
    return [
        line.strip()
        for line in (text or "").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


# --- Thiet bi ---
def adb_exe():
    return os.environ.get("ADBUTILS_ADB_PATH", "adb")


def scan_devices():
    """Tra ve danh sach thiet bi Android dang ket noi: [(serial, state)]."""
    try:
        import adbutils

        return [(dev.serial, dev.get_state()) for dev in adbutils.adb.list()]
    except Exception:
        out = subprocess.run(
            [adb_exe(), "devices"], capture_output=True, text=True, timeout=15
        ).stdout
        result = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                result.append((parts[0], parts[1]))
        return result


# JS: tim khoi quang cao dua tren ATTRIBUTE HTML (khong phu thuoc ngon ngu),
# cuon no vao giua man hinh va tra ve toa do de bam.
# Google danh dau block quang cao bang: data-text-ad, #tads/#tadsb, data-pcu, data-rw
_SPONSORED_JS = r"""
(() => {
  const pick = (a) => {
    if (!a) return null;
    const raw = a.dataset.rw || (a.dataset.pcu || '').split(',')[0] || a.getAttribute('href');
    return raw ? new URL(raw, location.href).href : null;
  };
  const chains = [
    '[data-text-ad] a[data-rw]',
    '#tads a[data-rw]',
    '#tadsb a[data-rw]',
    '[data-text-ad] a[data-pcu]',
    '#tads a[data-pcu]',
    '#tadsb a[data-pcu]',
    'a[href*="/aclk"]',
    '[data-text-ad] a[href]',
  ];
  let a = null;
  let url = null;
  for (const sel of chains) {
    a = document.querySelector(sel);
    url = pick(a);
    if (url) break;
  }
  if (!url) return null;

  // Cuon quang cao ra giua man hinh
  a.scrollIntoView({block: 'center', inline: 'center'});
  const r = a.getBoundingClientRect();

  // Tim 1 diem nam trong the quang cao (hit-test) de bam chinh xac
  let hit = null;
  for (let py = 0.25; py <= 0.75 && !hit; py += 0.125) {
    for (let px = 0.2; px <= 0.8; px += 0.15) {
      const x = r.left + r.width * px;
      const y = r.top + r.height * py;
      const e = document.elementFromPoint(x, y);
      if (e && (e === a || a.contains(e))) {
        hit = [x, y];
        break;
      }
    }
  }
  return {
    url: url,
    rect: [r.left, r.top, r.width, r.height],
    hit: hit,
    dpr: window.devicePixelRatio || 1,
  };
})()
"""


class Job:
    """1 proxy tren 1 thiet bi, chay trong 1 thread. Moi job co port CDP rieng."""

    def __init__(self, serial, proxy_line, keyword=DEFAULT_KEYWORD, cdp_port=CDP_BASE_PORT):
        self.serial = serial
        self.proxy_line = proxy_line
        self.keyword = (keyword or DEFAULT_KEYWORD).strip()
        self.cdp_port = cdp_port
        self.d = None

        ip, port, _u, _p = parse_proxy(proxy_line)
        self.tag = f"[{serial or 'default'} | {ip}:{port}]"

    # ---------- log ----------
    def log(self, msg):
        log(f"{self.tag} {msg}")

    def _check_stop(self):
        if should_stop():
            raise Aborted()

    # ---------- ket noi ----------
    def connect(self, retries=5, delay=3):
        """Ket noi thiet bi, thu lai va reconnect adb neu bi offline."""
        last = None
        for i in range(1, retries + 1):
            self._check_stop()
            try:
                self.d = u2.connect(self.serial) if self.serial else u2.connect()
                self.d.wait_timeout = 20
                self.log("[connect] da ket noi")
                return self.d
            except Exception as e:
                last = e
                self.log(f"[connect] lan {i}/{retries} loi: {e}")
                subprocess.run(
                    [adb_exe(), "reconnect", "offline"], capture_output=True
                )
                time.sleep(delay)
        raise RuntimeError("Khong ket noi duoc thiet bi, kiem tra adb devices") from last

    # ---------- helper UI ----------
    @staticmethod
    def field(hint):
        return f'//android.widget.EditText[@hint="{hint}"]'

    def set_field(self, hint, value):
        self.d.xpath(self.field(hint)).set_text(value)

    def scroll_to_bottom(self, times=1):
        for _ in range(times):
            self.d.swipe(0.03, 0.7, 0.03, 0.2, 0.15)
            time.sleep(0.5)

    # ---------- CDP ----------
    def cdp_forward(self):
        """Port tren may tinh -> socket debug cua Chrome tren thiet bi nay."""
        local = f"tcp:{self.cdp_port}"
        # Xoa listener cu (co the do thiet bi khac giu) roi forward lai
        subprocess.run(
            [adb_exe(), "forward", "--remove", local], capture_output=True
        )
        try:
            self.d.adb_device.forward(local, CDP_SOCKET)
        except Exception as e:
            self.log(f"[cdp] forward port {self.cdp_port} loi: {e}")

    def cdp_pages(self):
        """Danh sach tab Chrome dang mo (chi tab 'page')."""
        self.cdp_forward()
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.cdp_port}/json/list", timeout=5
        ) as r:
            data = json.load(r)
        return [
            p for p in data if p.get("type") == "page" and p.get("webSocketDebuggerUrl")
        ]

    def search_page(self):
        pages = self.cdp_pages()
        return next(
            (p for p in pages if "google.com/search" in p.get("url", "")),
            pages[0] if pages else None,
        )

    def cdp_eval(self, ws_url, expression, timeout=20):
        """Chay 1 doan JS trong tab va tra ve gia tri (returnByValue)."""
        ws = websocket.create_connection(
            ws_url, timeout=timeout, suppress_origin=True
        )
        try:
            ws.send(json.dumps({
                "id": 1,
                "method": "Runtime.evaluate",
                "params": {"expression": expression, "returnByValue": True},
            }))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    return msg.get("result", {}).get("result", {}).get("value")
        finally:
            ws.close()

    def get_page_html(self):
        """Tra ve HTML that (outerHTML) cua tab Google Search dang mo."""
        page = self.search_page()
        if page is None:
            raise RuntimeError("Chrome khong co tab nao dang mo")
        return self.cdp_eval(page["webSocketDebuggerUrl"], "document.documentElement.outerHTML")

    def save_page_html(self, path=None):
        """Luu HTML trang hien tai ra file de debug."""
        path = path or str(BASE_DIR / f"page_{self.cdp_port}.html")
        html = self.get_page_html()
        Path(path).write_text(html, encoding="utf-8")
        self.log(f"[html] da luu {len(html)} ky tu vao {path}")
        return html

    def sponsored_target(self):
        """Tim quang cao trong HTML, cuon vao giua man hinh.

        Returns:
            dict {"url", "rect": [left, top, width, height], "hit", "dpr"} hoac None
        """
        page = self.search_page()
        if page is None:
            return None
        return self.cdp_eval(page["webSocketDebuggerUrl"], _SPONSORED_JS)

    def is_search_page(self):
        """Dang con o trang ket qua Google khong (doc location.href qua CDP).

        Khong dung url_bar vi Chrome tu an thanh dia chi khi cuon trang,
        va /json/list co the tra URL cu -> phai hoi truc tiep trang.
        """
        try:
            page = self.search_page()
            if page is None:
                return False
            href = self.cdp_eval(page["webSocketDebuggerUrl"], "location.href")
            return "/search?" in (href or "")
        except Exception:
            return False

    def page_scroll_y(self):
        """Vi tri cuon hien tai cua trang (px) qua CDP, None neu khong doc duoc."""
        try:
            page = self.search_page()
            if page is None:
                return None
            return self.cdp_eval(page["webSocketDebuggerUrl"], "window.scrollY")
        except Exception:
            return None

    # ---------- cac buoc ----------
    def setup_proxy(self):
        """Xoa du lieu Super Proxy, them proxy moi va bat."""
        server_ip, port, username, password = parse_proxy(self.proxy_line)

        self.log("[proxy] xoa du lieu Super Proxy")
        self.d.app_clear(PROXY_APP)
        time.sleep(1)

        self.log("[proxy] mo Super Proxy")
        self.d.app_start(PROXY_APP, stop=True)
        self.d.xpath('//*[@content-desc="Add proxy"]').click(timeout=10)

        self.d.xpath(f'{self.field("Protocol")}/android.widget.Button').click(timeout=5)
        self.d.xpath('//*[@content-desc="HTTP"]').click(timeout=5)
        time.sleep(0.5)

        self.set_field("Server", server_ip)
        self.set_field("Port", str(port))

        self.d.xpath(self.field("Authentication method")).click(timeout=5)
        self.d.xpath('//*[@content-desc="Username/Password"]').click(timeout=5)
        time.sleep(1)

        self.set_field("Username", username)
        self.set_field("Password", password)

        self.d.xpath("(//android.widget.Button)[2]").click(timeout=5)
        self.d.xpath('//*[@content-desc="Start"]').click(timeout=10)
        time.sleep(2)

        # Hop thoai xin quyen VPN cua Android (nut OK) - chi hien khi chua cap quyen
        acp = self.d.xpath('//*[@resource-id="android:id/button1"]')
        if acp.wait(3):
            acp.click()
            self.log("[proxy] da cap quyen VPN")
        time.sleep(2)

    def dismiss_chrome_popups(self):
        """Tat cac popup lan dau cua Chrome (dang nhap, accept & continue...)."""
        signin = self.d.xpath(
            '//*[@resource-id="com.android.chrome:id/signin_fre_dismiss_button"]'
        )
        if signin.wait(5):
            signin.click()
            time.sleep(2)

        ack = self.d.xpath('//*[@resource-id="com.android.chrome:id/ack_button"]')
        if ack.wait(3):
            ack.click()
            time.sleep(2)

    def search_on_chrome(self):
        """Xoa du lieu Chrome, mo Chrome va search keyword."""
        self.log("[chrome] xoa du lieu Chrome")
        self.d.app_clear(CHROME_APP)
        time.sleep(1)
        self.d.app_start(CHROME_APP)
        time.sleep(2)

        self.dismiss_chrome_popups()
        self._check_stop()

        # Bam vao o search tren trang chu Chrome
        search_box = self.d.xpath(
            '//*[@resource-id="com.android.chrome:id/search_box"]/android.widget.RelativeLayout[1]'
        )
        if search_box.wait(5):
            search_box.click()
            time.sleep(1)
            self.d.send_keys(self.keyword, clear=True)
            self.d.press("enter")
            time.sleep(3)
        else:
            # Khong thay o search -> mo thang URL search
            self.d.open_url(SEARCH_URL.format(quote(self.keyword)))
            time.sleep(3)

    def click_sponsored_result(self, timeout=20):
        """Cuon toi ket qua duoc tai tro (quang cao) roi bam - dua vao HTML, khong dua vao text."""
        if websocket is None:
            self.log("[ads] thieu websocket-client -> pip install websocket-client")
            return False

        target = None
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._check_stop()
            try:
                target = self.sponsored_target()
            except Exception as e:
                self.log(f"[ads] khong doc duoc html: {e}")
                target = None
            if target:
                break
            time.sleep(2)  # trang chua tai xong quang cao

        if not target:
            self.log("[ads] trang ket qua khong co quang cao (tag data-text-ad / #tads)")
            return False

        # JS tra ve toa do CSS px -> doi sang pixel thiet bi de bam
        left, top, width, height = target["rect"]
        if target.get("hit"):
            px, py = target["hit"]  # diem da hit-test la nam trong the quang cao
        else:
            px, py = left + width / 2, top + height / 2
        dpr = target.get("dpr") or 1
        x, y = int(px * dpr), int(py * dpr)

        self.log(f"[ads] quang cao: {target['url'][:80]}...")
        self.log(f"[ads] cuon toi ({x}, {y}) roi click")

        time.sleep(0.3)  # cho scroll on dinh
        self.d.click(x, y)
        time.sleep(5)

        # Khong roi khoi trang ket qua -> mo truc tiep link quang cao
        if self.is_search_page():
            self.log("[ads] click chua an, mo truc tiep link quang cao")
            self.d.open_url(target["url"])
            time.sleep(5)
        return True

    def random_swipe(self, directions=("up", "up", "up", "up", "up")):
        """Cuon trang bang cach VUOT LEN (ngon tay di tu duoi len tren).

        Mac dinh 5 lan (3 + 2). Vuot len khong bao gio lam Chrome reload trang;
        vuot xuong khi dang o dau trang se bi hieu la pull-to-refresh.
        Vi tri + thoi gian deu ngau nhien de gia lap nguoi dung.
        """
        done = 0
        for direction in directions:
            if should_stop():
                break
            # Dang o dau trang ma keo xuong = Chrome hieu la pull-to-refresh -> bo qua
            if direction == "down" and (self.page_scroll_y() or 0) < 200:
                continue
            x1 = random.uniform(0.25, 0.75)
            x2 = x1 + random.uniform(-0.05, 0.05)  # lech ngang nhe, tranh vuot canh man hinh
            if direction == "up":  # vuot len: ngon tay tu duoi len tren -> cuon xuong
                y1, y2 = random.uniform(0.70, 0.85), random.uniform(0.20, 0.35)
            else:  # vuot xuong: ngon tay tu tren xuong duoi -> cuon len
                y1, y2 = random.uniform(0.20, 0.35), random.uniform(0.70, 0.85)
            self.d.swipe(x1, y1, x2, y2, random.uniform(0.15, 0.4))
            done += 1
            time.sleep(random.uniform(0.8, 1.8))
        self.log(f"[swipe] da vuot {done} lan")

    # ---------- toan bo flow ----------
    def run(self):
        server_ip, port, _u, _p = parse_proxy(self.proxy_line)
        self.log(f"[run] keyword={self.keyword!r} proxy={server_ip}:{port}")

        self.connect()
        self._check_stop()
        self.setup_proxy()
        self._check_stop()
        self.search_on_chrome()
        self._check_stop()
        self.click_sponsored_result()
        self._check_stop()
        self.random_swipe()
        self.log("[done] hoan tat")
        return True


def run_jobs(keyword, proxies, serials, cdp_base_port=CDP_BASE_PORT, on_job_done=None):
    """Chay moi proxy tren 1 thiet bi rieng, song song 1 thread cho moi cap.

    Args:
        keyword: tu khoa Google.
        proxies: danh sach dong 'ip:port:user:pass'.
        serials: danh sach serial thiet bi (adb).
        cdp_base_port: port CDP cho thiet bi dau, cac thiet bi sau +1.
        on_job_done: callback(tag, ok, error) goi khi 1 job ket thuc.

    Returns:
        dict {tag: True/False}
    """
    reset_stop()
    proxies = [p for p in proxies if p.strip()]
    serials = [s for s in serials if s]
    if not proxies:
        raise ValueError("chua co proxy nao")
    if not serials:
        raise ValueError("chua chon thiet bi nao")

    pairs = list(zip(proxies, serials))
    if len(proxies) != len(serials):
        log(
            f"[run] {len(proxies)} proxy / {len(serials)} thiet bi "
            f"-> chay {len(pairs)} luong (1 proxy : 1 thiet bi)"
        )

    jobs = [
        Job(serial=serial, proxy_line=proxy_line, keyword=keyword,
            cdp_port=cdp_base_port + i)
        for i, (proxy_line, serial) in enumerate(pairs)
    ]

    results = {}
    lock = threading.Lock()

    def worker(job):
        ok, err = False, None
        try:
            job.run()
            ok = True
        except Aborted:
            err = "da dung"
            job.log("[stop] dung theo yeu cau")
        except Exception as e:
            err = str(e)
            job.log(f"[error] {e}")
        finally:
            with lock:
                results[job.tag] = ok
            if on_job_done is not None:
                try:
                    on_job_done(job.tag, ok, err)
                except Exception:
                    pass

    threads = [threading.Thread(target=worker, args=(job,), daemon=True) for job in jobs]
    log(f"[run] bat dau {len(threads)} luong, keyword={keyword!r}")
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok_count = sum(1 for v in results.values() if v)
    log(f"[run] ket thuc: {ok_count}/{len(results)} luong thanh cong")
    return results


# --- CLI 1 thiet bi (giu tuong thich) ---
def run(keyword=DEFAULT_KEYWORD, proxy_line=None, serial=None, cdp_port=CDP_BASE_PORT):
    """Chay 1 luong: proxy -> search -> click quang cao -> scroll."""
    reset_stop()
    line = (proxy_line or "").strip() or read_proxy()
    job = Job(serial=serial, proxy_line=line, keyword=keyword, cdp_port=cdp_port)
    job.run()
    return True


if __name__ == "__main__":
    run()
