import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import requests
except ImportError:
    requests = None

APP_NAME = "ZeraSophia Tracker"
DEFAULT_USERNAME = "ZeraSophia"
DEFAULT_INTERVAL = 30
CONFIG_FILE = "zeratracker_config.json"
LOG_FILE = "kick_bildirim.log"
BG = "#0b0b14"
CARD = "#151526"
CARD2 = "#1d1d32"
FG = "#ededf7"
MUTED = "#9696b7"
ACCENT = "#ff626d"
GREEN = "#35d07f"
YELLOW = "#ffc857"


def timestamp():
    return datetime.now().strftime("%H:%M:%S")


def read_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"username": DEFAULT_USERNAME, "interval": DEFAULT_INTERVAL, "sound": True}


def write_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def log_line(text):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line)


def fetch_channel(username):
    """Returns (channel_data, error_text)."""
    if requests is None:
        return None, "requests kütüphanesi kurulu değil."
    url = f"https://kick.com/api/v2/channels/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            return response.json(), None
        return None, f"Kick yanıtı: HTTP {response.status_code}"
    except requests.RequestException as exc:
        return None, f"Bağlantı hatası: {exc}"


def extract_live_info(data, username):
    live = data.get("livestream")
    if not live:
        return {"is_live": False, "username": username}
    category = live.get("categories") or live.get("category") or {}
    if isinstance(category, list):
        category = category[0] if category else {}
    return {
        "is_live": True,
        "username": username,
        "title": live.get("session_title") or live.get("title") or "Yayın başladı",
        "viewers": live.get("viewer_count", 0),
        "category": category.get("name", "Bilinmiyor") if isinstance(category, dict) else "Bilinmiyor",
        "url": f"https://kick.com/{username}",
        "channel_id": data.get("id") or (data.get("user") or {}).get("id"),
        "chatroom_id": (data.get("chatroom") or {}).get("id"),
    }


class ChatWindow:
    def __init__(self, root, get_username):
        self.root = root
        self.get_username = get_username
        self.window = None
        self.text = None
        self.status_var = None
        self.messages = queue.Queue()
        self.thread = None
        self.stop_event = threading.Event()
        self.chat_identity = None
        self.message_count = 0
        self._drain_scheduled = False

    def open(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return
        self.window = tk.Toplevel(self.root)
        self.window.title("ZeraSophia Tracker — Canlı Sohbet")
        self.window.geometry("480x650")
        self.window.minsize(330, 350)
        self.window.configure(bg=BG)
        self.window.protocol("WM_DELETE_WINDOW", self.window.withdraw)

        header = tk.Frame(self.window, bg=CARD, padx=14, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="💬 CANLI SOHBET", bg=CARD, fg=FG,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.status_var = tk.StringVar(value="Bağlantı bekleniyor…")
        tk.Label(header, textvariable=self.status_var, bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))

        body = tk.Frame(self.window, bg=BG, padx=10, pady=10)
        body.pack(fill="both", expand=True)
        self.text = tk.Text(
            body, bg="#10101b", fg=FG, insertbackground=FG,
            font=("Segoe UI", 10), wrap="word", relief="flat",
            padx=10, pady=8, state="disabled"
        )
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.tag_configure("time", foreground="#777795")
        self.text.tag_configure("name", foreground="#78c8ff", font=("Segoe UI", 10, "bold"))
        self.text.tag_configure("message", foreground=FG)
        self.text.tag_configure("system", foreground=YELLOW)

        footer = tk.Frame(self.window, bg=BG, padx=10, pady=8)
        footer.pack(fill="x")
        tk.Button(footer, text="Mesajları Temizle", command=self.clear,
                  bg=CARD2, fg=FG, relief="flat", padx=12, pady=7).pack(side="left")
        tk.Button(footer, text="Kick Kanalını Aç",
                  command=lambda: webbrowser.open(f"https://kick.com/{self.get_username()}"),
                  bg="#26734d", fg="white", relief="flat", padx=12, pady=7).pack(side="right")

        self._append_system("Sohbet penceresi hazır. Canlı yayın sırasında mesajlar burada görünür.")
        self._drain_scheduled = True
        self.root.after(150, self._drain_queue)
        self.start_connection()

    def clear(self):
        if self.text and self.text.winfo_exists():
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.configure(state="disabled")

    def _append_system(self, message):
        self.messages.put(("system", message, ""))

    def _drain_queue(self):
        self._drain_scheduled = False
        if not self.window or not self.window.winfo_exists():
            return
        try:
            while True:
                kind, first, second = self.messages.get_nowait()
                if kind == "status":
                    if self.status_var:
                        self.status_var.set(first)
                elif self.text and self.text.winfo_exists():
                    self.text.configure(state="normal")
                    if kind == "system":
                        self.text.insert("end", f"[{timestamp()}] {first}\n", "system")
                    else:
                        self.text.insert("end", f"[{timestamp()}] ", "time")
                        self.text.insert("end", f"{first}: ", "name")
                        self.text.insert("end", f"{second}\n", "message")
                    # Keep the window responsive and avoid unbounded memory use.
                    line_count = int(self.text.index("end-1c").split(".")[0])
                    if line_count > 1200:
                        self.text.delete("1.0", "201.0")
                    self.text.see("end")
                    self.text.configure(state="disabled")
        except queue.Empty:
            pass
        self._drain_scheduled = True
        self.root.after(150, self._drain_queue)

    def start_connection(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._chat_thread, daemon=True)
        self.thread.start()

    def _chat_thread(self):
        try:
            import kicksdk.aio
        except ImportError:
            self.messages.put(("status",
                "Sohbet paketi eksik. Kurulum: pip install \"kicksdk-py[aio]\"", ""))
            self.messages.put(("system",
                'Canlı sohbet için terminalde: pip install "kicksdk-py[aio]"', ""))
            return

        async def runner():
            last_identity = None
            while not self.stop_event.is_set():
                username = self.get_username().strip()
                data, error = await asyncio.to_thread(fetch_channel, username)
                if not data:
                    self.messages.put(("status", f"Kanal bilgisi alınamadı: {error or 'bilinmeyen hata'}", ""))
                    await asyncio.sleep(15)
                    continue

                channel_id = data.get("id") or (data.get("user") or {}).get("id")
                chatroom_id = (data.get("chatroom") or {}).get("id")
                if not channel_id or not chatroom_id:
                    self.messages.put(("status", "Sohbet odası bulunamadı; kanal çevrimdışı olabilir.", ""))
                    await asyncio.sleep(20)
                    continue

                identity = (str(chatroom_id), str(channel_id))
                if identity != last_identity:
                    self.messages.put(("system", f"Kick sohbetine bağlanılıyor: {username}", ""))
                    last_identity = identity

                self.messages.put(("status", f"Bağlantı hazırlanıyor • {username}", ""))
                try:
                    async with kicksdk.aio.connect_chat(int(chatroom_id), int(channel_id)) as chat:
                        self.messages.put(("status", f"Canlı sohbet bağlantısı etkin • {username}", ""))
                        self.messages.put(("system", "Sohbet bağlantısı kuruldu.", ""))
                        async for item in chat:
                            if self.stop_event.is_set():
                                break
                            event = item.get("event", item)
                            if not isinstance(event, dict):
                                continue
                            if event.get("type") == "chat_message":
                                sender = event.get("sender") or {}
                                name = sender.get("username") or sender.get("slug") or "Kullanıcı"
                                content = event.get("content") or ""
                                if content:
                                    self.messages.put(("message", str(name), str(content)))
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    self.messages.put(("status", f"Sohbet yeniden bağlanacak: {str(exc)[:100]}", ""))
                    self.messages.put(("system", f"Sohbet bağlantısı kesildi; yeniden denenecek. ({str(exc)[:100]})", ""))
                    await asyncio.sleep(5)

        try:
            asyncio.run(runner())
        except Exception as exc:
            self.messages.put(("status", f"Sohbet hatası: {str(exc)[:120]}", ""))

    def shutdown(self):
        self.stop_event.set()
        try:
            if self.window and self.window.winfo_exists():
                self.window.destroy()
        except tk.TclError:
            pass


class TrackerApp:
    def __init__(self):
        self.config = read_config()
        self.username = str(self.config.get("username") or DEFAULT_USERNAME)
        try:
            self.interval = max(10, int(self.config.get("interval", DEFAULT_INTERVAL)))
        except (ValueError, TypeError):
            self.interval = DEFAULT_INTERVAL
        self.sound_enabled = bool(self.config.get("sound", True))
        self.running = True
        self.is_live = False
        self.last_check = "Henüz kontrol edilmedi"
        self.check_count = 0
        self.live_count = 0
        self.last_title = ""
        self.last_error = None
        self.events = queue.Queue()
        self.poll_thread = None
        self.last_notified_stream = None

        self.root = tk.Tk()
        self.root.title(APP_NAME + " v8.0")
        self.root.geometry("760x620")
        self.root.minsize(560, 470)
        self.root.configure(bg=BG)
        # Sohbet penceresi, arayüz butonu oluşturulmadan önce hazırlanmalı.
        self.chat = ChatWindow(self.root, lambda: self.username)
        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(200, self._process_events)
        self.start_polling()

    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TProgressbar", troughcolor=CARD2, background=ACCENT)

        header = tk.Frame(self.root, bg=BG, padx=22, pady=18)
        header.pack(fill="x")
        title_line = tk.Frame(header, bg=BG)
        title_line.pack(fill="x")
        tk.Label(title_line, text="🎮 ZeraSophia Tracker", bg=BG, fg=FG,
                 font=("Segoe UI", 21, "bold")).pack(side="left")
        tk.Label(title_line, text="v8.0", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 10, "bold")).pack(side="right", padx=4)
        tk.Label(header, text="KICK YAYIN TAKİP MERKEZİ", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(4, 0))

        controls = tk.Frame(self.root, bg=BG, padx=22)
        controls.pack(fill="x", pady=(0, 12))
        tk.Button(controls, text="⚙ Ayarlar", command=self.open_settings,
                  bg=CARD2, fg=FG, relief="flat", padx=14, pady=8).pack(side="left")
        tk.Button(controls, text="💬 Sohbet Penceresi", command=self.chat.open,
                  bg=CARD2, fg=FG, relief="flat", padx=14, pady=8).pack(side="left", padx=8)
        tk.Button(controls, text="🔄 Şimdi Kontrol Et", command=self.manual_check,
                  bg="#343451", fg=FG, relief="flat", padx=14, pady=8).pack(side="right")

        self.status_card = tk.Frame(self.root, bg=CARD, padx=18, pady=16)
        self.status_card.pack(fill="x", padx=22, pady=(0, 12))
        self.status_title = tk.Label(self.status_card, text="⚪ Yayın durumu bekleniyor",
                                     bg=CARD, fg=MUTED, font=("Segoe UI", 16, "bold"))
        self.status_title.pack(anchor="w")
        self.status_sub = tk.Label(self.status_card, text="İlk kanal kontrolü yapılıyor…",
                                   bg=CARD, fg=MUTED, font=("Segoe UI", 10), wraplength=680, justify="left")
        self.status_sub.pack(anchor="w", pady=(5, 0))
        action_row = tk.Frame(self.status_card, bg=CARD)
        action_row.pack(fill="x", pady=(14, 0))
        self.watch_button = tk.Button(action_row, text="▶ Yayını Aç", command=self.open_stream,
                                      bg=GREEN, fg="#07140d", relief="flat",
                                      font=("Segoe UI", 11, "bold"), padx=18, pady=9,
                                      state="disabled")
        self.watch_button.pack(side="left")
        tk.Button(action_row, text="Kanalı Tarayıcıda Aç",
                  command=lambda: webbrowser.open(f"https://kick.com/{self.username}"),
                  bg=CARD2, fg=FG, relief="flat", padx=14, pady=9).pack(side="left", padx=8)

        stats = tk.Frame(self.root, bg=BG, padx=22)
        stats.pack(fill="x", pady=(0, 12))
        self.check_stat = self._stat_card(stats, "KONTROL", "0")
        self.live_stat = self._stat_card(stats, "YAYIN ALGILANDI", "0")
        self.interval_stat = self._stat_card(stats, "KONTROL ARALIĞI", f"{self.interval} sn")

        log_card = tk.Frame(self.root, bg=CARD, padx=14, pady=10)
        log_card.pack(fill="both", expand=True, padx=22, pady=(0, 18))
        log_header = tk.Frame(log_card, bg=CARD)
        log_header.pack(fill="x")
        tk.Label(log_header, text="📋 Aktivite Günlüğü", bg=CARD, fg=FG,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(log_header, text="Temizle", command=self.clear_log, bg=CARD2,
                  fg=MUTED, relief="flat", padx=8, pady=3).pack(side="right")
        self.log_box = tk.Text(log_card, height=8, bg="#10101b", fg="#b8c7e6",
                               insertbackground=FG, font=("Consolas", 9),
                               relief="flat", wrap="word", state="disabled")
        self.log_box.pack(fill="both", expand=True, pady=(8, 0))
        self.log_box.tag_configure("error", foreground="#ff7777")
        self.log_box.tag_configure("success", foreground=GREEN)
        self.add_log("Uygulama başlatıldı.")
        self.add_log(f"Takip edilen kanal: {self.username}")

    def _stat_card(self, parent, label, value):
        card = tk.Frame(parent, bg=CARD, padx=12, pady=12)
        card.pack(side="left", fill="both", expand=True, padx=(0, 8))
        tk.Label(card, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w")
        value_label = tk.Label(card, text=value, bg=CARD, fg=ACCENT, font=("Segoe UI", 17, "bold"))
        value_label.pack(anchor="w", pady=(5, 0))
        return value_label

    def add_log(self, text, tag=None):
        if not hasattr(self, "log_box"):
            log_line(text)
            return
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{timestamp()}] {text}\n", tag or ())
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > 300:
            self.log_box.delete("1.0", "51.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        log_line(text)

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.add_log("Günlük temizlendi.")

    def start_polling(self):
        if self.poll_thread and self.poll_thread.is_alive():
            return
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _poll_loop(self):
        while self.running:
            data, error = fetch_channel(self.username)
            if data:
                info = extract_live_info(data, self.username)
                self.events.put(("status", info))
            else:
                self.events.put(("error", error or "Kanal bilgisi alınamadı"))
            # Sleep in short increments so closing the app does not wait long.
            for _ in range(max(10, self.interval) * 10):
                if not self.running:
                    break
                time.sleep(0.1)

    def _process_events(self):
        if not self.running:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "status":
                    self.check_count += 1
                    self.last_check = timestamp()
                    info = payload
                    now_live = bool(info.get("is_live"))
                    if now_live:
                        self.status_title.config(text="🔴 CANLI YAYINDA", fg=ACCENT)
                        title = info.get("title", "Yayın başladı")
                        viewers = info.get("viewers", 0)
                        category = info.get("category", "Bilinmiyor")
                        self.status_sub.config(
                            text=f"{title}\n👁 {viewers} izleyici  •  📂 {category}  •  Son kontrol: {self.last_check}",
                            fg=FG
                        )
                        self.watch_button.config(state="normal")
                        stream_key = (info.get("title"), info.get("channel_id"))
                        if not self.is_live or stream_key != self.last_notified_stream:
                            self.live_count += 1
                            self.last_notified_stream = stream_key
                            self.add_log(f"🔴 Yayın algılandı: {title}", "success")
                            self.notify_live(info)
                        self.last_title = title
                    else:
                        self.status_title.config(text="⚪ YAYINDA DEĞİL", fg=MUTED)
                        self.status_sub.config(text=f"{self.username} kanalında yayın bekleniyor. Son kontrol: {self.last_check}", fg=MUTED)
                        self.watch_button.config(state="disabled")
                        if self.is_live:
                            self.add_log("Yayın sona erdi.")
                    self.is_live = now_live
                    self.check_stat.config(text=str(self.check_count))
                    self.live_stat.config(text=str(self.live_count))
                    self.interval_stat.config(text=f"{self.interval} sn")
                elif kind == "error":
                    self.last_check = timestamp()
                    self.status_title.config(text="🟠 KANALA BAĞLANILAMADI", fg=YELLOW)
                    self.status_sub.config(text=f"{payload}\nSon deneme: {self.last_check}", fg=MUTED)
                    self.add_log(f"Kontrol hatası: {payload}", "error")
        except queue.Empty:
            pass
        self.root.after(250, self._process_events)

    def notify_live(self, info):
        if self.sound_enabled:
            try:
                import winsound
                # Run a short, non-blocking alert tone.
                threading.Thread(target=lambda: winsound.Beep(1000, 220), daemon=True).start()
            except Exception:
                try:
                    self.root.bell()
                except tk.TclError:
                    pass
        try:
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass
        title = info.get("title", "Yayın başladı")
        viewers = info.get("viewers", 0)
        popup = tk.Toplevel(self.root)
        popup.title("🔴 Kick yayını başladı")
        popup.geometry("420x220")
        popup.minsize(350, 200)
        popup.configure(bg=CARD)
        popup.attributes("-topmost", True)
        tk.Label(popup, text="🔴 YAYIN BAŞLADI!", bg=CARD, fg=ACCENT,
                 font=("Segoe UI", 17, "bold")).pack(pady=(18, 8))
        tk.Label(popup, text=title[:100], bg=CARD, fg=FG,
                 font=("Segoe UI", 10), wraplength=370).pack(padx=18)
        tk.Label(popup, text=f"👁 {viewers} izleyici", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 10)).pack(pady=8)
        buttons = tk.Frame(popup, bg=CARD)
        buttons.pack(fill="x", padx=18, pady=10)
        tk.Button(buttons, text="▶ YAYINI AÇ", command=lambda: (webbrowser.open(info["url"]), popup.destroy()),
                  bg=GREEN, fg="#07140d", relief="flat", font=("Segoe UI", 10, "bold"),
                  padx=15, pady=8).pack(side="left", expand=True, fill="x", padx=(0, 5))
        tk.Button(buttons, text="Sonra", command=popup.destroy, bg=CARD2, fg=FG,
                  relief="flat", padx=15, pady=8).pack(side="left", expand=True, fill="x", padx=(5, 0))
        popup.after(120000, lambda: popup.destroy() if popup.winfo_exists() else None)

    def open_stream(self):
        webbrowser.open(f"https://kick.com/{self.username}")

    def manual_check(self):
        self.add_log("Manuel kontrol istendi.")
        threading.Thread(target=self._single_check, daemon=True).start()

    def _single_check(self):
        data, error = fetch_channel(self.username)
        if data:
            self.events.put(("status", extract_live_info(data, self.username)))
        else:
            self.events.put(("error", error or "Kanal bilgisi alınamadı"))

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("ZeraSophia Tracker — Ayarlar")
        win.geometry("400x330")
        win.resizable(False, False)
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text="AYARLAR", bg=BG, fg=FG,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=22, pady=(18, 12))
        tk.Label(win, text="Kick kullanıcı adı", bg=BG, fg=MUTED).pack(anchor="w", padx=22)
        username_var = tk.StringVar(value=self.username)
        tk.Entry(win, textvariable=username_var, bg=CARD, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 11)).pack(fill="x", padx=22, pady=(5, 12), ipady=6)

        tk.Label(win, text="Kontrol aralığı (10–300 saniye)", bg=BG, fg=MUTED).pack(anchor="w", padx=22)
        interval_var = tk.StringVar(value=str(self.interval))
        tk.Entry(win, textvariable=interval_var, bg=CARD, fg=FG, insertbackground=FG,
                 relief="flat", font=("Segoe UI", 11)).pack(fill="x", padx=22, pady=(5, 12), ipady=6)

        sound_var = tk.BooleanVar(value=self.sound_enabled)
        tk.Checkbutton(win, text="Sesli bildirim", variable=sound_var, bg=BG, fg=FG,
                       selectcolor=CARD, activebackground=BG, activeforeground=FG).pack(anchor="w", padx=20)

        def save():
            username = username_var.get().strip().lstrip("@")
            if not username or any(c.isspace() for c in username) or "/" in username:
                messagebox.showerror("Hata", "Geçerli bir Kick kullanıcı adı yaz.", parent=win)
                return
            try:
                interval = int(interval_var.get().strip())
                if not 10 <= interval <= 300:
                    raise ValueError
            except ValueError:
                messagebox.showerror("Hata", "Kontrol aralığı 10 ile 300 arasında tam sayı olmalı.", parent=win)
                return
            changed = username.lower() != self.username.lower()
            self.username = username
            self.interval = interval
            self.sound_enabled = sound_var.get()
            write_config({"username": self.username, "interval": self.interval, "sound": self.sound_enabled})
            self.interval_stat.config(text=f"{self.interval} sn")
            self.add_log(f"Ayarlar kaydedildi. Kanal: {self.username}, aralık: {self.interval} sn")
            if changed:
                self.is_live = False
                self.last_notified_stream = None
                self.add_log("Kanal değişti; yeni kanal kontrol ediliyor.")
                self.manual_check()
            win.destroy()

        tk.Button(win, text="💾 Kaydet", command=save, bg=ACCENT, fg="white",
                  relief="flat", font=("Segoe UI", 11, "bold"), padx=18, pady=9).pack(pady=16)

    def close(self):
        if not messagebox.askyesno("Çıkış", "ZeraSophia Tracker kapatılsın mı?"):
            return
        self.running = False
        try:
            if hasattr(self, "chat"):
                self.chat.shutdown()
        except Exception:
            pass
        write_config({"username": self.username, "interval": self.interval, "sound": self.sound_enabled})
        self.root.destroy()


def main():
    if requests is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Eksik paket",
            "requests kurulu değil.\nKomut İstemi'nde şu komutu çalıştır:\n\npy -m pip install requests"
        )
        return
    app = TrackerApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
