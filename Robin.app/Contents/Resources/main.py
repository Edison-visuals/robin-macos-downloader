"""Robin — Mac 原生視窗下載器(pywebview + yt-dlp,無 HTTP server)。"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid

try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
except ImportError:
    pass

SUPPORT_DIR = os.path.expanduser("~/Library/Application Support/Robin")
CONFIG_PATH = os.path.join(SUPPORT_DIR, "config.json")
HISTORY_PATH = os.path.join(SUPPORT_DIR, "history.json")


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    try:
        os.makedirs(SUPPORT_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


# Finder 啟動的 app 沒有 Homebrew PATH,手動補上並尋找 ffmpeg
os.environ["PATH"] = os.environ.get("PATH", "") + ":/opt/homebrew/bin:/usr/local/bin:/opt/local/bin"


def _find_ffmpeg_dir():
    import shutil
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/local/bin/ffmpeg"):
        if os.path.exists(p):
            return os.path.dirname(p)
    w = shutil.which("ffmpeg")
    return os.path.dirname(w) if w else None


FFMPEG_DIR = _find_ffmpeg_dir()

# YouTube 各 client 行為不同(web 會要求 reload、ios 可能誤報 DRM),依序嘗試
CLIENT_TRIES = [
    None,  # yt-dlp 預設
    {"youtube": {"player_client": ["web_safari", "tv"]}},
    {"youtube": {"player_client": ["ios", "android"]}},
    {"youtube": {"player_client": ["web_embedded", "tv_embedded"]}},
]

VALID_BROWSERS = ("chrome", "safari", "firefox", "edge", "brave")
VALID_SOUNDS = ("Glass", "Ping", "Hero", "Submarine", "Pop", "Blow", "Funk")


def _notify(message, title="Robin", sound="Glass"):
    """通知 + 提示聲(sound=None 則只通知不出聲)。"""
    try:
        msg = str(message).replace("\\", "").replace('"', "'")[:80]
        script = f'display notification "{msg}" with title "{title}"'
        if sound:
            script += f' sound name "{sound}"'
        subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True)
    except Exception:
        pass


def _play_sound(name="Glass"):
    """獨立播放系統音效,確保即使通知被靜音也聽得到。"""
    def run():
        try:
            path = f"/System/Library/Sounds/{name}.aiff"
            if os.path.exists(path):
                subprocess.run(["afplay", path], timeout=10, capture_output=True)
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()


class Api:
    def __init__(self):
        self.tasks = {}
        self.jobs = {}        # 非同步解析工作
        self.good_args = {}   # url -> 成功的 extractor_args
        self.task_files = {}  # task_id -> 下載過程碰過的檔案路徑
        cfg = _load_json(CONFIG_PATH, {})
        d = cfg.get("download_dir")
        self.download_dir = d if (d and os.path.isdir(d)) else os.path.expanduser("~/Downloads")
        b = cfg.get("cookies_browser", "")
        self.cookies_browser = b if b in VALID_BROWSERS else ""
        s = cfg.get("sound", "Glass")
        self.sound = s if s in VALID_SOUNDS else ("" if s == "" else "Glass")
        self._pb_count = -1

    # ---------- 設定 ----------
    def _save_config(self):
        _save_json(CONFIG_PATH, {"download_dir": self.download_dir,
                                 "cookies_browser": self.cookies_browser,
                                 "sound": self.sound})

    def get_settings(self):
        try:
            import yt_dlp
            v = yt_dlp.version.__version__
        except Exception:
            v = "?"
        return {"download_dir": self.download_dir,
                "cookies_browser": self.cookies_browser,
                "sound": self.sound,
                "ytdlp_version": v,
                "ffmpeg": bool(FFMPEG_DIR)}

    def choose_folder(self):
        import webview
        try:
            res = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
            if res:
                path = res[0] if isinstance(res, (list, tuple)) else res
                if path and os.path.isdir(path):
                    self.download_dir = path
                    self._save_config()
        except Exception:
            pass
        return {"download_dir": self.download_dir}

    def set_cookies(self, browser):
        self.cookies_browser = browser if browser in VALID_BROWSERS else ""
        self._save_config()
        return {"cookies_browser": self.cookies_browser}

    def set_sound(self, name):
        self.sound = name if name in VALID_SOUNDS else ""
        self._save_config()
        if self.sound:
            _play_sound(self.sound)   # 選好立刻試聽
        return {"sound": self.sound}

    def test_sound(self):
        if self.sound:
            _play_sound(self.sound)
        return True

    def update_ytdlp(self):
        try:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "yt-dlp"],
                               timeout=180, capture_output=True, text=True)
            v = subprocess.run(
                [sys.executable, "-c", "import yt_dlp; print(yt_dlp.version.__version__)"],
                timeout=30, capture_output=True, text=True).stdout.strip()
            ok = r.returncode == 0
            return {"ok": ok, "version": v or "?",
                    "note": "已更新,重啟 Robin 後生效" if ok else (r.stderr or "更新失敗")[:120]}
        except Exception as e:
            return {"ok": False, "version": "?", "note": str(e)[:120]}

    # ---------- 歷史 ----------
    def get_history(self):
        return _load_json(HISTORY_PATH, [])

    def _add_history(self, title, mode, container, status):
        h = _load_json(HISTORY_PATH, [])
        h.insert(0, {"title": str(title)[:120], "mode": mode, "fmt": container,
                     "status": status, "time": time.strftime("%m/%d %H:%M")})
        _save_json(HISTORY_PATH, h[:50])

    # ---------- 剪貼簿偵測 ----------
    def get_clipboard_url(self):
        try:
            from AppKit import NSPasteboard
            pb = NSPasteboard.generalPasteboard()
            cc = pb.changeCount()
            if cc == self._pb_count:
                return {"url": None}
            self._pb_count = cc
            s = (pb.stringForType_("public.utf8-plain-text") or "").strip()
            if s.startswith(("http://", "https://")) and " " not in s and len(s) < 500:
                return {"url": s}
        except Exception:
            pass
        return {"url": None}

    # ---------- 共用 ----------
    def _common_opts(self):
        # 長影片/慢速來源:拉長 socket timeout 並多次重試,避免中途斷線
        opts = {
            "quiet": True,
            "socket_timeout": 60,
            "retries": 10,
            "fragment_retries": 10,
            "extractor_retries": 3,
        }
        if self.cookies_browser:
            opts["cookiesfrombrowser"] = (self.cookies_browser,)
        return opts

    # ---------- 解析(非同步,避免長影片阻塞 UI 橋接) ----------
    def info_start(self, url):
        job = uuid.uuid4().hex[:8]
        self.jobs[job] = {"state": "running", "started": time.time()}

        def work():
            try:
                res = self._info_sync(url)
            except Exception as e:
                res = {"error": f"無法解析:{e}"}
            j = self.jobs.get(job)
            if j is not None:
                j["state"] = "done"
                j["result"] = res

        threading.Thread(target=work, daemon=True).start()
        return {"job": job}

    def info_poll(self, job):
        j = self.jobs.get(job)
        if not j:
            return {"state": "unknown"}
        if j["state"] == "running":
            return {"state": "running", "elapsed": int(time.time() - j["started"])}
        self.jobs.pop(job, None)
        return {"state": "done", "result": j.get("result", {})}

    def info(self, url):
        return self._info_sync(url)

    def _info_sync(self, url):
        url = (url or "").strip()
        if not url:
            return {"error": "請輸入網址"}
        import yt_dlp
        last_err = None
        for ea in CLIENT_TRIES:
            opts = dict(self._common_opts(), skip_download=True,
                        extract_flat="in_playlist", playlist_items="1:100")
            if ea:
                opts["extractor_args"] = ea
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    d = ydl.extract_info(url, download=False)
                self.good_args[url] = ea
                if d.get("_type") == "playlist" and d.get("entries"):
                    entries = []
                    for e in d["entries"]:
                        if not e:
                            continue
                        u = e.get("url") or e.get("webpage_url") or ""
                        if u and not u.startswith("http"):
                            u = f"https://www.youtube.com/watch?v={u}"
                        if u:
                            entries.append({"url": u, "title": e.get("title") or u})
                    if len(entries) > 1:
                        return {"playlist": True, "title": d.get("title") or url,
                                "count": len(entries), "entries": entries}
                    if entries:  # 單支影片的「清單」,直接解析那支
                        url = entries[0]["url"]
                        continue
                heights = sorted(
                    {f.get("height") for f in d.get("formats", [])
                     if f.get("height") and f.get("vcodec") != "none"},
                    reverse=True,
                )
                return {
                    "title": d.get("title"),
                    "thumbnail": d.get("thumbnail"),
                    "duration": d.get("duration"),
                    "uploader": d.get("uploader"),
                    "heights": heights,
                }
            except Exception as e:
                last_err = e
        return {"error": f"無法解析:{last_err}"}

    # ---------- 下載 ----------
    def download(self, url, mode, container, quality, title):
        url = (url or "").strip()
        if not url:
            return {"error": "請輸入網址"}
        task_id = uuid.uuid4().hex[:8]
        self.tasks[task_id] = {"status": "starting", "percent": 0,
                               "paused": False, "cancel": False}

        # 影片+音訊分兩條流下載,合併計算整體進度,避免進度條跑兩三次
        expected_files = 2 if (mode == "video" and FFMPEG_DIR) else 1
        state = {"done_files": 0}

        def hook(d):
            t = self.tasks[task_id]
            fn = d.get("filename")
            if fn:
                self.task_files.setdefault(task_id, set()).add(fn)
            if t.get("cancel"):
                raise Exception("__cancelled__")
            while t.get("paused") and not t.get("cancel"):
                t["status"] = "paused"
                time.sleep(0.3)
            if t.get("cancel"):
                raise Exception("__cancelled__")
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                frac = (done / total) if total else 0
                overall = (state["done_files"] + frac) / expected_files * 100
                t.update(
                    status="downloading",
                    percent=round(min(overall, 99.9), 1) if total else None,
                    speed=d.get("speed"),
                    eta=d.get("eta"),
                )
            elif d["status"] == "finished":
                state["done_files"] += 1
                if state["done_files"] >= expected_files:
                    t.update(status="processing", percent=100)

        def pp_hook(d):
            # 轉檔各階段之間仍可終止(ffmpeg 執行中無法中斷)
            t = self.tasks[task_id]
            if t.get("cancel"):
                raise Exception("__cancelled__")
            if d.get("status") == "started":
                t.update(status="processing", percent=100)

        opts = dict(self._common_opts())
        opts.update({
            "outtmpl": os.path.join(self.download_dir, "%(title)s.%(ext)s"),
            "progress_hooks": [hook],
            "postprocessor_hooks": [pp_hook],
            "noplaylist": True,
            "overwrites": False,  # 同名檔案不覆蓋
        })
        ea = self.good_args.get(url)
        if ea:
            opts["extractor_args"] = ea
        if FFMPEG_DIR:
            opts["ffmpeg_location"] = FFMPEG_DIR

        if mode == "audio":
            if not FFMPEG_DIR:
                return {"error": "音訊轉檔需要 ffmpeg,請先在終端機執行:brew install ffmpeg"}
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": container,
                "preferredquality": "0",
            }]
        else:
            h = f"[height<={quality}]" if quality and quality != "best" else ""
            if FFMPEG_DIR:
                if container in ("mp4", "mov"):
                    # MP4/MOV 優先 H.264 + AAC,確保 QuickTime 可播
                    opts["format"] = (
                        f"bestvideo[vcodec^=avc1]{h}+bestaudio[ext=m4a]/"
                        f"bestvideo[vcodec^=avc1]{h}+bestaudio/"
                        f"bestvideo{h}+bestaudio/best{h}/best"
                    )
                else:
                    opts["format"] = f"bestvideo{h}+bestaudio/best{h}/best"
                opts["merge_output_format"] = container
            else:
                opts["format"] = f"best{h}[ext=mp4]/best{h}/best"

        def run():
            import yt_dlp
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                self.tasks[task_id].update(status="done", percent=100)
                self._add_history(title or url, mode, container, "done")
                if self.sound:
                    _play_sound(self.sound)
                _notify(f"下載完成:{title or url}", sound=None)
            except Exception as e:
                if self.tasks[task_id].get("cancel") or "__cancelled__" in str(e):
                    self._cleanup(task_id)
                    self.tasks[task_id].update(status="cancelled")
                else:
                    self.tasks[task_id].update(status="error", error=str(e))
                    self._add_history(title or url, mode, container, "error")
                    if self.sound:
                        _play_sound("Basso")   # 失敗用低沉音
                    _notify(f"下載失敗:{title or url}", sound=None)
            finally:
                self._schedule_prune(task_id)

        threading.Thread(target=run, daemon=True).start()
        return {"task_id": task_id}

    # ---------- 任務管理 ----------
    def progress(self, task_id):
        return self.tasks.get(task_id, {"status": "unknown"})

    def pause(self, task_id):
        t = self.tasks.get(task_id)
        if not t:
            return {"paused": False}
        t["paused"] = not t["paused"]
        if not t["paused"] and t["status"] == "paused":
            t["status"] = "downloading"
        return {"paused": t["paused"]}

    def cancel(self, task_id):
        t = self.tasks.get(task_id)
        if t:
            t["cancel"] = True
            t["paused"] = False
        return True

    def _schedule_prune(self, task_id):
        # 終態任務 10 分鐘後從記憶體移除,避免長時間累積
        def prune():
            self.tasks.pop(task_id, None)
            self.task_files.pop(task_id, None)
        t = threading.Timer(600, prune)
        t.daemon = True
        t.start()

    def _cleanup(self, task_id):
        """終止後移除殘留的暫存/半成品檔案。"""
        import glob
        for f in self.task_files.get(task_id, set()):
            if not f:
                continue
            candidates = {f, f + ".part", f + ".ytdl"}
            candidates.update(glob.glob(f + ".part-Frag*"))
            candidates.update(glob.glob(f + ".f*"))
            for p in candidates:
                try:
                    if os.path.isfile(p):
                        os.remove(p)
                except OSError:
                    pass
        self.task_files.pop(task_id, None)

    def open_downloads(self):
        subprocess.run(["open", self.download_dir])
        return True

    def quit_app(self):
        """完全結束 Robin:取消所有任務、清掉半成品,再強制退出行程。"""
        force_quit(self)
        return True


_status_refs = []


def force_quit(api=None, window=None):
    """乾淨地結束:取消任務 → 清半成品 → 關視窗 → 強制退出行程。

    pywebview / PyObjC 在某些情況下不會讓 Python 主行程自然結束,
    所以最後用 os._exit 保證不會殘留卡住的 python。
    """
    try:
        if api:
            for tid, t in list(api.tasks.items()):
                t["cancel"] = True
                t["paused"] = False
            time.sleep(0.4)
            for tid in list(api.task_files.keys()):
                try:
                    api._cleanup(tid)
                except Exception:
                    pass
    except Exception:
        pass

    def bail():
        os._exit(0)

    t = threading.Timer(1.2, bail)   # 保險:1.2 秒內沒退成功就強制結束
    t.daemon = True
    t.start()
    try:
        if window:
            window.destroy()
    except Exception:
        pass
    try:
        from AppKit import NSApp
        NSApp.terminate_(None)
    except Exception:
        pass


def _setup_status_item(window, api=None):
    """在選單列 (menu bar) 建立 Robin 圖示:開啟視窗 / 結束。"""
    try:
        from AppKit import (NSApp, NSImage, NSMenu, NSMenuItem, NSObject,
                            NSStatusBar, NSVariableStatusItemLength)

        class RobinStatus(NSObject):
            def openWin_(self, sender):
                window.show()
                NSApp.activateIgnoringOtherApps_(True)

            def quitApp_(self, sender):
                force_quit(api, window)

        delegate = RobinStatus.alloc().init()
        item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menubar.png")
        img = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if img:
            img.setSize_((18, 18))
            img.setTemplate_(True)
            item.button().setImage_(img)
        else:
            item.button().setTitle_("R")

        menu = NSMenu.alloc().init()
        mi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("開啟 Robin", "openWin:", "")
        mi.setTarget_(delegate)
        menu.addItem_(mi)
        menu.addItem_(NSMenuItem.separatorItem())
        qi = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("結束", "quitApp:", "q")
        qi.setTarget_(delegate)
        menu.addItem_(qi)
        item.setMenu_(menu)
        _status_refs.extend([delegate, item])
    except Exception:
        pass


if __name__ == "__main__":
    import webview

    api = Api()
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")
    window = webview.create_window(
        "Robin", html_path, js_api=api,
        width=1152, height=648,
        resizable=False, zoomable=False,
        background_color="#e2e8e9",
    )

    def on_closing():
        # 有下載進行中 → 收進選單列繼續跑;沒有 → 直接結束整個 app
        busy = any(t.get("status") in ("starting", "downloading", "paused", "processing")
                   for t in api.tasks.values())
        if busy:
            window.hide()
            return False
        force_quit(api, None)
        return True

    window.events.closing += on_closing

    def on_start():
        try:
            from PyObjCTools import AppHelper
            AppHelper.callAfter(_setup_status_item, window, api)
        except Exception:
            pass

    try:
        webview.start(on_start)
    finally:
        force_quit(api, None)
