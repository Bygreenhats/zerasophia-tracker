#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ZeraSophia - Ultimate Kick Yayın Takip Sistemi
Versiyon: 7.0 (Tam Ekran Merkez + Ses Düzeltme)
"""

import requests
import time
import json
import os
import threading
import subprocess
import sys
import sqlite3
import webbrowser
import platform
from datetime import datetime, timedelta
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox, font

# ============================================================
# KONFIGÜRASYON
# ============================================================
KICK_USERNAME = "ZeraSophia"
CHECK_INTERVAL = 30
LOG_FILE = "kick_bildirim.log"
APP_NAME = "ZeraSophia Tracker"
DB_FILE = "zeratracker.db"
CONFIG_FILE = "zeratracker_config.json"

# ============================================================
# TEMA YÖNETİMİ
# ============================================================
THEMES = {
    'dark': {
        'bg': '#0a0a14', 'card': '#141425', 'card2': '#1a1a35',
        'text': '#e8e8f0', 'sub': '#8888bb', 'accent': '#ff6b6b',
        'accent2': '#ff4444', 'success': '#2ecc71', 'danger': '#e74c3c',
        'input': '#1a1a30', 'border': '#2a2a50', 'hover': '#2a2a45',
        'gradient': ['#0a0a14', '#141425']
    },
    'light': {
        'bg': '#f0f2f8', 'card': '#ffffff', 'card2': '#f5f6fa',
        'text': '#1a1a2e', 'sub': '#666688', 'accent': '#e74c3c',
        'accent2': '#c0392b', 'success': '#27ae60', 'danger': '#c0392b',
        'input': '#ffffff', 'border': '#e0e0e8', 'hover': '#f0f0f5',
        'gradient': ['#f0f2f8', '#e8eaf0']
    },
    'purple': {
        'bg': '#12082a', 'card': '#1f0f3a', 'card2': '#2a1a4a',
        'text': '#e8d8ff', 'sub': '#a888cc', 'accent': '#a855f7',
        'accent2': '#7c3aed', 'success': '#2ecc71', 'danger': '#e74c3c',
        'input': '#1f0f3a', 'border': '#3a2a5a', 'hover': '#2a1a4a',
        'gradient': ['#12082a', '#1f0f3a']
    },
    'matrix': {
        'bg': '#000a00', 'card': '#0a1a0a', 'card2': '#0f2a0f',
        'text': '#00ff41', 'sub': '#00cc33', 'accent': '#00ff41',
        'accent2': '#00cc33', 'success': '#00ff41', 'danger': '#ff0044',
        'input': '#0a1a0a', 'border': '#1a3a1a', 'hover': '#0f2a0f',
        'gradient': ['#000a00', '#0a1a0a']
    }
}

# ============================================================
# VERİTABANI
# ============================================================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
    
    def create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS streams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT, title TEXT, viewers INTEGER,
                category TEXT, start_time TEXT, end_time TEXT, duration INTEGER
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stream_id INTEGER, sent_time TEXT, method TEXT
            )
        ''')
        self.conn.commit()
    
    def add_stream(self, username, title, viewers, category):
        self.cursor.execute('''
            INSERT INTO streams (username, title, viewers, category, start_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, title, viewers, category, datetime.now().isoformat()))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def end_stream(self, stream_id):
        self.cursor.execute('''
            UPDATE streams SET end_time = ?,
            duration = (strftime('%s', end_time) - strftime('%s', start_time))
            WHERE id = ?
        ''', (datetime.now().isoformat(), stream_id))
        self.conn.commit()
    
    def get_history(self, limit=50):
        self.cursor.execute('SELECT * FROM streams ORDER BY start_time DESC LIMIT ?', (limit,))
        return self.cursor.fetchall()
    
    def get_stats(self):
        self.cursor.execute('SELECT COUNT(*) FROM streams')
        total = self.cursor.fetchone()[0] or 0
        self.cursor.execute('SELECT AVG(viewers) FROM streams WHERE viewers > 0')
        avg = self.cursor.fetchone()[0] or 0
        self.cursor.execute('SELECT MAX(viewers) FROM streams')
        max_v = self.cursor.fetchone()[0] or 0
        return {'total': total, 'avg_viewers': round(avg, 0), 'max_viewers': max_v}
    
    def close(self):
        self.conn.close()

# ============================================================
# SES YÖNETİMİ (DÜZELTİLMİŞ)
# ============================================================
class SoundManager:
    def __init__(self):
        self.enabled = True
        self.initialized = True
        log_message("🔊 Ses sistemi başlatıldı")
    
    def play(self, sound_type='notification'):
        """Ses çal - Windows için winsound, diğerleri için terminal"""
        if not self.enabled:
            return
        
        try:
            if platform.system() == "Windows":
                import winsound
                if sound_type == 'notification':
                    winsound.Beep(800, 300)   # 800Hz, 300ms
                elif sound_type == 'live_start':
                    winsound.Beep(1000, 400)
                    time.sleep(0.1)
                    winsound.Beep(1200, 400)
                    time.sleep(0.1)
                    winsound.Beep(1500, 500)
            else:
                # Linux/macOS için terminal zili
                print('\a')
        except Exception as e:
            log_message(f"⚠️ Ses hatası: {e}")

# ============================================================
# İSTATİSTİK
# ============================================================
class Statistics:
    def __init__(self):
        self.total_checks = 0
        self.total_notifications = 0
        self.total_live_time = 0
        self.last_live_start = None
        self.viewer_history = deque(maxlen=100)
        self.db = Database()
    
    def add_check(self):
        self.total_checks += 1
    
    def add_notification(self, viewers, stream_id=None):
        self.total_notifications += 1
        self.viewer_history.append(viewers)
    
    def get_avg_viewers(self):
        if self.viewer_history:
            return sum(self.viewer_history) / len(self.viewer_history)
        return 0
    
    def get_stats(self):
        db_stats = self.db.get_stats()
        return {
            'toplam_kontrol': self.total_checks,
            'toplam_bildirim': self.total_notifications,
            'ortalama_izleyici': round(self.get_avg_viewers(), 0),
            'toplam_yayin': db_stats['total'],
            'max_izleyici': db_stats['max_viewers']
        }

# ============================================================
# RATE LIMITER & CACHE
# ============================================================
class RateLimiter:
    def __init__(self, max_requests=10, time_window=60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = deque()
    
    def allow(self):
        now = time.time()
        while self.requests and self.requests[0] < now - self.time_window:
            self.requests.popleft()
        if len(self.requests) < self.max_requests:
            self.requests.append(now)
            return True
        return False

class CacheManager:
    def __init__(self, ttl=30):
        self.cache = {}
        self.ttl = ttl
    
    def get(self, key):
        if key in self.cache:
            data, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return data
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())

# ============================================================
# LOG SİSTEMİ
# ============================================================
def log_message(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except:
        pass
    print(f"[{timestamp}] {message}")

# ============================================================
# KİCK API
# ============================================================
cache = CacheManager(ttl=30)
rate_limiter = RateLimiter(max_requests=30, time_window=60)

def get_channel_info(username):
    if not rate_limiter.allow():
        time.sleep(5)
    
    cached = cache.get(f"kick_{username}")
    if cached:
        return cached
    
    try:
        url = f"https://kick.com/api/v2/channels/{username}"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, timeout=10, headers=headers)
        if response.status_code == 200:
            data = response.json()
            cache.set(f"kick_{username}", data)
            return data
        return None
    except Exception as e:
        log_message(f"API Hatası: {e}")
        return None

def check_live_status(username):
    data = get_channel_info(username)
    if not data:
        return None, None
    
    is_live = data.get('livestream') is not None
    
    if is_live:
        stream_data = data.get('livestream', {})
        user_data = data.get('user', {})
        return {
            'is_live': True,
            'title': stream_data.get('session_title', 'Yayın Başladı!'),
            'viewers': stream_data.get('viewer_count', 0),
            'category': stream_data.get('category', {}).get('name', 'Bilinmiyor'),
            'url': f"https://kick.com/{username}",
            'username': username
        }, stream_data
    else:
        return {'is_live': False}, None

# ============================================================
# ENTEGRASYON FONKSİYONLARI
# ============================================================
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except:
        pass

def send_discord_notification(title, viewers, url):
    config = load_config()
    webhook_url = config.get('discord_webhook', '')
    if not webhook_url:
        return
    data = {
        "content": f"🔴 **{KICK_USERNAME} CANLI YAYINDA!**",
        "embeds": [{
            "title": title[:100],
            "description": f"👁️ {viewers} izleyici\n[📺 Yayını İzle]({url})",
            "color": 0xff0000,
            "timestamp": datetime.now().isoformat()
        }]
    }
    try:
        requests.post(webhook_url, json=data, timeout=5)
        log_message("✅ Discord bildirimi gönderildi")
    except:
        pass

def send_telegram_notification(title, viewers, url):
    config = load_config()
    bot_token = config.get('telegram_bot', '')
    chat_id = config.get('telegram_chat', '')
    if not bot_token or not chat_id:
        return
    message = f"🔴 *{KICK_USERNAME} CANLI YAYINDA!*\n📺 {title[:50]}\n👁️ {viewers} izleyici\n[🔗 Yayını İzle]({url})"
    try:
        requests.get(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            params={'chat_id': chat_id, 'message': message, 'parse_mode': 'Markdown'},
            timeout=5
        )
        log_message("✅ Telegram bildirimi gönderildi")
    except:
        pass

def send_push_notification(title, message):
    config = load_config()
    pushbullet_api = config.get('pushbullet_api', '')
    if not pushbullet_api:
        return
    try:
        requests.post(
            'https://api.pushbullet.com/v2/pushes',
            json={'type': 'note', 'title': title[:50], 'body': message[:200]},
            headers={'Access-Token': pushbullet_api},
            timeout=5
        )
        log_message("✅ Pushbullet bildirimi gönderildi")
    except:
        pass

# ============================================================
# SİSTEM TRAY
# ============================================================
TRAY_SUPPORT = False
try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_SUPPORT = True
except ImportError:
    TRAY_SUPPORT = False

# ============================================================
# ANA UYGULAMA (Tam Ekran Merkez + Ses Düzeltme)
# ============================================================
class ZeraTrackerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("520x750")
        self.root.minsize(420, 650)
        self.root.configure(bg='#0a0a14')
        
        # Değişkenler
        self.is_running = True
        self.notified = False
        self.last_status = False
        self.notification_window = None
        self.tray_icon = None
        self.manual_check_active = False
        self.current_theme = 'dark'
        self.is_fullscreen = False
        self.current_stream_id = None
        self.scale_factor = 1.0
        
        # Modüller
        self.db = Database()
        self.stats = Statistics()
        self.sound = SoundManager()
        
        # Ana container (merkez için)
        self.main_container = tk.Frame(self.root, bg='#0a0a14')
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Orta alan için center frame
        self.center_frame = tk.Frame(self.main_container, bg='#0a0a14')
        self.center_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        # İçerik frame (sabit boyutlu)
        self.content_frame = tk.Frame(self.center_frame, bg='#0a0a14', width=500, height=750)
        self.content_frame.pack_propagate(False)
        self.content_frame.pack()
        
        # Scrollable canvas
        self.canvas = tk.Canvas(self.content_frame, bg='#0a0a14', highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self.content_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg='#0a0a14')
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Fare tekerleği
        def on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # Arayüz
        self.create_widgets()
        self.apply_theme(self.current_theme)
        
        # Arka plan thread'i
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()
        
        # Sistem tepsisi
        if TRAY_SUPPORT:
            try:
                self.setup_tray()
            except:
                pass
        
        # Pencere olayları
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind('<F11>', self.toggle_fullscreen)
        self.root.bind('<Escape>', self.exit_fullscreen)
        self.root.bind('<Configure>', self.on_window_resize)
        
        self.root.mainloop()
    
    def on_window_resize(self, event):
        """Pencere boyut değişikliğinde merkezleme ve ölçekleme"""
        if self.is_fullscreen:
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            # İçerik boyutunu hesapla
            content_width = int(width * 0.45)
            content_height = int(height * 0.80)
            if content_width < 420:
                content_width = 420
            if content_height < 650:
                content_height = 650
            self.content_frame.config(width=content_width, height=content_height)
            
            # Fontları ölçekle
            self.scale_factor = content_width / 500
            self.update_scale()
    
    def update_scale(self):
        """Fontları ölçekle"""
        try:
            for widget in self.scrollable_frame.winfo_children():
                try:
                    if isinstance(widget, (tk.Label, tk.Button, tk.Entry)):
                        current_font = widget.cget('font')
                        if isinstance(current_font, tuple) and len(current_font) >= 2:
                            size = current_font[1]
                            new_size = int(size * self.scale_factor)
                            if new_size < 8:
                                new_size = 8
                            widget.config(font=(current_font[0], new_size))
                except:
                    pass
        except:
            pass
    
    def create_widgets(self):
        # Ana frame
        main_frame = tk.Frame(self.scrollable_frame, bg='#0a0a14')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=15)
        
        # ============================================================
        # HEADER
        # ============================================================
        header_frame = tk.Frame(main_frame, bg='#0a0a14')
        header_frame.pack(fill=tk.X, pady=(5, 10))
        
        tk.Label(
            header_frame,
            text="🎮 ZeraSophia Tracker",
            font=('Segoe UI', 22, 'bold'),
            fg='#e8e8f0',
            bg='#0a0a14'
        ).pack(anchor=tk.W)
        
        tk.Label(
            header_frame,
            text="Kick Canlı Yayın Bildirim Sistemi v7.0",
            font=('Segoe UI', 10),
            fg='#8888bb',
            bg='#0a0a14'
        ).pack(anchor=tk.W)
        
        # Kontrol çubuğu
        control_bar = tk.Frame(header_frame, bg='#0a0a14')
        control_bar.pack(fill=tk.X, pady=8)
        
        # Tema butonları
        theme_frame = tk.Frame(control_bar, bg='#0a0a14')
        theme_frame.pack(side=tk.LEFT)
        
        themes = [('🌙', 'dark'), ('☀️', 'light'), ('💜', 'purple'), ('💚', 'matrix')]
        for emoji, name in themes:
            btn = tk.Button(
                theme_frame,
                text=emoji,
                font=('Segoe UI', 12),
                bg='#141425',
                fg='#e8e8f0',
                relief=tk.FLAT,
                padx=10,
                pady=3,
                command=lambda n=name: self.apply_theme(n)
            )
            btn.pack(side=tk.LEFT, padx=2)
        
        # Sağ kontroller
        right_frame = tk.Frame(control_bar, bg='#0a0a14')
        right_frame.pack(side=tk.RIGHT)
        
        self.speed_display = tk.Label(
            right_frame,
            text=f"⏱️ {CHECK_INTERVAL}s",
            font=('Segoe UI', 10, 'bold'),
            fg='#ff6b6b',
            bg='#0a0a14'
        )
        self.speed_display.pack(side=tk.LEFT, padx=8)
        
        self.fullscreen_btn = tk.Button(
            right_frame,
            text='⛶ Tam Ekran',
            font=('Segoe UI', 10),
            bg='#141425',
            fg='#e8e8f0',
            relief=tk.FLAT,
            padx=10,
            pady=3,
            command=self.toggle_fullscreen
        )
        self.fullscreen_btn.pack(side=tk.LEFT, padx=2)
        
        # Çizgi
        line = tk.Frame(main_frame, height=2, bg='#2a2a50')
        line.pack(fill=tk.X, pady=(5, 12))
        
        # ============================================================
        # DURUM KARTI
        # ============================================================
        status_card = tk.Frame(main_frame, bg='#141425', relief=tk.FLAT, bd=0)
        status_card.pack(fill=tk.X, pady=(0, 10))
        
        status_inner = tk.Frame(status_card, bg='#141425')
        status_inner.pack(fill=tk.BOTH, expand=True, padx=18, pady=12)
        
        self.status_dot = tk.Label(
            status_inner,
            text="⚪",
            font=('Segoe UI', 26),
            bg='#141425'
        )
        self.status_dot.pack(side=tk.LEFT, padx=(0, 12))
        
        status_text_frame = tk.Frame(status_inner, bg='#141425')
        status_text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.status_text = tk.Label(
            status_text_frame,
            text="Bekleniyor...",
            font=('Segoe UI', 16, 'bold'),
            fg='#8888bb',
            bg='#141425',
            anchor=tk.W
        )
        self.status_text.pack(anchor=tk.W)
        
        self.status_sub = tk.Label(
            status_text_frame,
            text="Yayın kontrolü başlatıldı.",
            font=('Segoe UI', 11),
            fg='#8888bb',
            bg='#141425',
            anchor=tk.W
        )
        self.status_sub.pack(anchor=tk.W)
        
        # ============================================================
        # İSTATİSTİK KARTI
        # ============================================================
        stats_card = tk.Frame(main_frame, bg='#141425', relief=tk.FLAT, bd=0)
        stats_card.pack(fill=tk.X, pady=(0, 10))
        
        stats_inner = tk.Frame(stats_card, bg='#141425')
        stats_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        
        stats_data = self.stats.get_stats()
        stat_items = [
            ('📊', 'Kontrol', stats_data['toplam_kontrol']),
            ('🔔', 'Bildirim', stats_data['toplam_bildirim']),
            ('👁️', 'Ort. İzleyici', stats_data['ortalama_izleyici']),
            ('📺', 'Toplam Yayın', stats_data['toplam_yayin'])
        ]
        
        for i, (icon, label, value) in enumerate(stat_items):
            item_frame = tk.Frame(stats_inner, bg='#141425')
            item_frame.pack(side=tk.LEFT, expand=True, fill=tk.X)
            
            tk.Label(
                item_frame,
                text=f"{icon} {value}",
                font=('Segoe UI', 16, 'bold'),
                fg='#ff6b6b',
                bg='#141425'
            ).pack()
            tk.Label(
                item_frame,
                text=label,
                font=('Segoe UI', 9),
                fg='#8888bb',
                bg='#141425'
            ).pack()
        
        # ============================================================
        # YAYINCI BİLGİSİ
        # ============================================================
        channel_card = tk.Frame(main_frame, bg='#141425', relief=tk.FLAT, bd=0)
        channel_card.pack(fill=tk.X, pady=(0, 10))
        
        channel_inner = tk.Frame(channel_card, bg='#141425')
        channel_inner.pack(fill=tk.X, padx=18, pady=10)
        
        tk.Label(
            channel_inner,
            text="📺 Takip Edilen Yayıncı",
            font=('Segoe UI', 10),
            fg='#8888bb',
            bg='#141425'
        ).pack(anchor=tk.W)
        
        self.channel_label = tk.Label(
            channel_inner,
            text=KICK_USERNAME,
            font=('Segoe UI', 18, 'bold'),
            fg='#ff6b6b',
            bg='#141425'
        )
        self.channel_label.pack(anchor=tk.W)
        
        # ============================================================
        # KONTROL HIZI
        # ============================================================
        speed_card = tk.Frame(main_frame, bg='#141425', relief=tk.FLAT, bd=0)
        speed_card.pack(fill=tk.X, pady=(0, 10))
        
        speed_inner = tk.Frame(speed_card, bg='#141425')
        speed_inner.pack(fill=tk.X, padx=18, pady=8)
        
        speed_label_frame = tk.Frame(speed_inner, bg='#141425')
        speed_label_frame.pack(fill=tk.X)
        
        tk.Label(
            speed_label_frame,
            text="⏱️ Kontrol Hızı",
            font=('Segoe UI', 11),
            fg='#8888bb',
            bg='#141425'
        ).pack(side=tk.LEFT)
        
        self.speed_label = tk.Label(
            speed_label_frame,
            text=f"{CHECK_INTERVAL} saniye",
            font=('Segoe UI', 11, 'bold'),
            fg='#ff6b6b',
            bg='#141425'
        )
        self.speed_label.pack(side=tk.RIGHT)
        
        self.speed_slider = tk.Scale(
            speed_inner,
            from_=5,
            to=120,
            orient=tk.HORIZONTAL,
            bg='#141425',
            fg='#ff6b6b',
            highlightthickness=0,
            troughcolor='#2a2a50',
            activebackground='#ff6b6b',
            sliderlength=20,
            width=10,
            command=self.update_speed
        )
        self.speed_slider.set(CHECK_INTERVAL)
        self.speed_slider.pack(fill=tk.X, pady=(5, 0))
        
        # ============================================================
        # BUTONLAR
        # ============================================================
        btn_card = tk.Frame(main_frame, bg='#141425', relief=tk.FLAT, bd=0)
        btn_card.pack(fill=tk.X, pady=(0, 10))
        
        btn_inner = tk.Frame(btn_card, bg='#141425')
        btn_inner.pack(fill=tk.X, padx=18, pady=8)
        
        self.check_btn = tk.Button(
            btn_inner,
            text="🔄 Şimdi Kontrol Et",
            font=('Segoe UI', 12, 'bold'),
            bg='#2a2a50',
            fg='#e8e8f0',
            activebackground='#3a3a60',
            relief=tk.FLAT,
            padx=20,
            pady=10,
            command=self.manual_check
        )
        self.check_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        
        self.settings_btn = tk.Button(
            btn_inner,
            text="⚙️ Ayarlar",
            font=('Segoe UI', 12, 'bold'),
            bg='#2a2a50',
            fg='#e8e8f0',
            activebackground='#3a3a60',
            relief=tk.FLAT,
            padx=16,
            pady=10,
            command=self.open_settings
        )
        self.settings_btn.pack(side=tk.RIGHT, padx=(6, 0))
        
        # ============================================================
        # DURUM ÇUBUĞU
        # ============================================================
        status_bar = tk.Frame(main_frame, bg='#0a0a12', relief=tk.FLAT, bd=1)
        status_bar.pack(fill=tk.X, pady=(0, 8))
        
        self.status_bar_label = tk.Label(
            status_bar,
            text="✅ Sistem aktif | Son kontrol: Bekleniyor...",
            font=('Segoe UI', 9),
            fg='#8888bb',
            bg='#0a0a12'
        )
        self.status_bar_label.pack(side=tk.LEFT, padx=12, pady=6)
        
        self.counter_label = tk.Label(
            status_bar,
            text="#0",
            font=('Segoe UI', 9, 'bold'),
            fg='#ff6b6b',
            bg='#0a0a12'
        )
        self.counter_label.pack(side=tk.RIGHT, padx=12, pady=6)
        
        # ============================================================
        # LOG ALANI
        # ============================================================
        log_card = tk.Frame(main_frame, bg='#0a0a12', relief=tk.FLAT, bd=0)
        log_card.pack(fill=tk.BOTH, expand=True)
        
        log_header = tk.Frame(log_card, bg='#0a0a12')
        log_header.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        tk.Label(
            log_header,
            text="📋 Aktivite Günlüğü",
            font=('Segoe UI', 10),
            fg='#8888bb',
            bg='#0a0a12'
        ).pack(side=tk.LEFT)
        
        clear_btn = tk.Button(
            log_header,
            text="🗑️ Temizle",
            font=('Segoe UI', 9),
            bg='#0a0a12',
            fg='#8888bb',
            activebackground='#1a1a2e',
            relief=tk.FLAT,
            command=self.clear_log
        )
        clear_btn.pack(side=tk.RIGHT)
        
        self.log_text = tk.Text(
            log_card,
            height=7,
            bg='#0a0a12',
            fg='#88aacc',
            font=('Consolas', 9),
            relief=tk.FLAT,
            bd=0,
            wrap=tk.WORD
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))
        
        scrollbar_log = tk.Scrollbar(self.log_text)
        scrollbar_log.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar_log.set)
        scrollbar_log.config(command=self.log_text.yview)
        
        # ============================================================
        # ALT BİLGİ
        # ============================================================
        footer = tk.Label(
            main_frame,
            text=f"v7.0 | {CHECK_INTERVAL}s aralıkla çalışıyor | F11 tam ekran",
            font=('Segoe UI', 8),
            fg='#666688',
            bg='#0a0a14'
        )
        footer.pack(pady=(8, 0))
    
    def apply_theme(self, theme_name):
        self.current_theme = theme_name
        theme = THEMES.get(theme_name, THEMES['dark'])
        
        self.root.configure(bg=theme['bg'])
        self.main_container.configure(bg=theme['bg'])
        self.center_frame.configure(bg=theme['bg'])
        self.content_frame.configure(bg=theme['bg'])
        self.canvas.configure(bg=theme['bg'])
        self.scrollable_frame.configure(bg=theme['bg'])
        
        log_message(f"🎨 Tema değiştirildi: {theme_name}")
    
    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes('-fullscreen', self.is_fullscreen)
        if self.is_fullscreen:
            self.fullscreen_btn.config(text='⛶ Çık')
            self.root.after(100, self.on_window_resize, None)
        else:
            self.fullscreen_btn.config(text='⛶ Tam Ekran')
            self.scale_factor = 1.0
            self.content_frame.config(width=500, height=750)
            self.update_scale()
    
    def exit_fullscreen(self, event=None):
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.root.attributes('-fullscreen', False)
            self.fullscreen_btn.config(text='⛶ Tam Ekran')
            self.scale_factor = 1.0
            self.content_frame.config(width=500, height=750)
            self.update_scale()
    
    def update_speed(self, value):
        global CHECK_INTERVAL
        try:
            new_speed = int(float(value))
            if new_speed < 5:
                new_speed = 5
            CHECK_INTERVAL = new_speed
            self.speed_label.config(text=f"{CHECK_INTERVAL} saniye")
            self.speed_display.config(text=f"⏱️ {CHECK_INTERVAL}s")
            self.add_log(f"⚙️ Kontrol hızı {CHECK_INTERVAL} saniye olarak ayarlandı")
        except:
            pass
    
    def update_status(self, is_live, stream_data=None):
        try:
            if is_live and stream_data:
                self.status_dot.config(text="🔴", fg='#ff4444')
                self.status_text.config(text="🟢 CANLI YAYINDA!", fg='#ff6b6b')
                title = stream_data.get('title', '')[:30]
                self.status_sub.config(text=f"{title} | {stream_data.get('viewers', 0)} izleyici", fg='#88aacc')
                self.status_bar_label.config(text="🔴 Yayın aktif!", fg='#ff6b6b')
            else:
                self.status_dot.config(text="⚪", fg='#666688')
                self.status_text.config(text="Yayında Değil", fg='#8888bb')
                self.status_sub.config(text="Yayın bekleniyor...", fg='#666688')
                self.status_bar_label.config(text="✅ Sistem aktif | Yayın bekleniyor...", fg='#8888bb')
        except Exception as e:
            log_message(f"⚠️ Durum hatası: {e}")
    
    def add_log(self, message):
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.log_text.see(tk.END)
            if int(self.log_text.index('end-1c').split('.')[0]) > 100:
                self.log_text.delete(1.0, 2.0)
        except:
            pass
    
    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self.add_log("🗑️ Log temizlendi")
    
    def manual_check(self):
        if self.manual_check_active:
            return
        self.manual_check_active = True
        self.add_log("🔄 Manuel kontrol başlatıldı...")
        self.check_btn.config(text="⏳ Kontrol Ediliyor...", state=tk.DISABLED)
        self.root.after(100, self.do_manual_check)
    
    def do_manual_check(self):
        try:
            current_status, stream_data = check_live_status(KICK_USERNAME)
            self.check_btn.config(text="🔄 Şimdi Kontrol Et", state=tk.NORMAL)
            self.manual_check_active = False
            
            if current_status and current_status.get('is_live'):
                self.update_status(True, current_status)
                self.add_log(f"✅ CANLI! {current_status.get('title', '')[:40]}")
                if not self.notified:
                    self.show_notification(current_status)
                    self.notified = True
            else:
                self.update_status(False)
                self.add_log("ℹ️ Yayın aktif değil")
                self.notified = False
            
            self.stats.add_check()
            self.counter_label.config(text=f"#{self.stats.total_checks}")
            self.status_bar_label.config(text=f"✅ Son kontrol: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            self.check_btn.config(text="🔄 Şimdi Kontrol Et", state=tk.NORMAL)
            self.manual_check_active = False
            self.add_log(f"❌ Hata: {e}")
    
    def show_notification(self, stream_data):
        try:
            # SES ÇAL (DÜZELTİLMİŞ)
            self.sound.play('live_start')
            
            stream_id = self.db.add_stream(
                KICK_USERNAME,
                stream_data.get('title', ''),
                stream_data.get('viewers', 0),
                stream_data.get('category', '')
            )
            self.current_stream_id = stream_id
            
            # Discord, Telegram, Pushbullet
            send_discord_notification(
                stream_data.get('title', ''),
                stream_data.get('viewers', 0),
                stream_data.get('url', '')
            )
            send_telegram_notification(
                stream_data.get('title', ''),
                stream_data.get('viewers', 0),
                stream_data.get('url', '')
            )
            send_push_notification(
                f"🔴 {KICK_USERNAME} CANLI!",
                f"{stream_data.get('title', '')[:50]}\n👁️ {stream_data.get('viewers', 0)} izleyici"
            )
            
            # GUI Bildirimi
            if self.notification_window and self.notification_window.winfo_exists():
                self.notification_window.destroy()
            
            self.notification_window = tk.Toplevel(self.root)
            self.notification_window.title("🔴 YAYIN BAŞLADI!")
            self.notification_window.geometry("450x240")
            self.notification_window.resizable(False, False)
            self.notification_window.configure(bg='#141425')
            
            if self.is_fullscreen:
                self.notification_window.geometry("550x280")
            
            screen_width = self.notification_window.winfo_screenwidth()
            x = screen_width - 480
            y = 40
            self.notification_window.geometry(f"+{x}+{y}")
            self.notification_window.attributes('-topmost', True)
            
            frame = tk.Frame(self.notification_window, bg='#141425')
            frame.pack(fill=tk.BOTH, expand=True, padx=25, pady=18)
            
            tk.Label(
                frame,
                text="🔴 YAYIN BAŞLADI!",
                font=('Segoe UI', 18, 'bold'),
                fg='#ff6b6b',
                bg='#141425'
            ).pack(pady=(0, 8))
            
            info = f"""
📺 {stream_data.get('title', 'Yayın Başladı!')[:50]}
👁️ {stream_data.get('viewers', 0)} izleyici  |  📂 {stream_data.get('category', 'Bilinmiyor')}
            """
            
            tk.Label(
                frame,
                text=info,
                font=('Segoe UI', 12),
                fg='#e8e8f0',
                bg='#141425',
                justify=tk.CENTER
            ).pack(pady=6)
            
            btn_frame = tk.Frame(frame, bg='#141425')
            btn_frame.pack(pady=12, fill=tk.X)
            
            tk.Button(
                btn_frame,
                text="✅ İZLE",
                font=('Segoe UI', 13, 'bold'),
                bg='#2ecc71',
                fg='white',
                activebackground='#27ae60',
                relief=tk.FLAT,
                padx=30,
                pady=8,
                command=lambda: self.open_stream(stream_data)
            ).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))
            
            tk.Button(
                btn_frame,
                text="❌ KAPAT",
                font=('Segoe UI', 13, 'bold'),
                bg='#e74c3c',
                fg='white',
                activebackground='#c0392b',
                relief=tk.FLAT,
                padx=30,
                pady=8,
                command=self.close_notification
            ).pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(6, 0))
            
            self.notification_window.after(120000, self.close_notification)
            self.stats.add_notification(stream_data.get('viewers', 0), stream_id)
            
        except Exception as e:
            log_message(f"❌ Bildirim hatası: {e}")
    
    def open_stream(self, stream_data):
        url = stream_data.get('url', f"https://kick.com/{KICK_USERNAME}")
        self.add_log(f"🌐 Yayın açılıyor: {url}")
        
        try:
            if platform.system() == "Windows":
                opera_paths = [
                    r"C:\Program Files\Opera\launcher.exe",
                    r"C:\Program Files (x86)\Opera\launcher.exe",
                    rf"C:\Users\{os.getlogin()}\AppData\Local\Programs\Opera\launcher.exe"
                ]
                for path in opera_paths:
                    if os.path.exists(path):
                        subprocess.Popen([path, url])
                        self.add_log("✅ Opera ile açıldı")
                        break
                else:
                    webbrowser.open(url)
                    self.add_log("✅ Varsayılan tarayıcı ile açıldı")
            else:
                webbrowser.open(url)
                self.add_log("✅ Tarayıcı ile açıldı")
        except:
            webbrowser.open(url)
            self.add_log("⚠️ Hata, varsayılan tarayıcı açıldı")
        
        self.close_notification()
    
    def close_notification(self):
        try:
            if self.notification_window:
                self.notification_window.destroy()
                self.notification_window = None
        except:
            pass
    
    def open_settings(self):
        config = load_config()
        
        settings_win = tk.Toplevel(self.root)
        settings_win.title("⚙️ Ayarlar")
        settings_win.geometry("400x540")
        settings_win.resizable(False, False)
        settings_win.configure(bg='#0a0a14')
        settings_win.attributes('-topmost', True)
        
        canvas = tk.Canvas(settings_win, bg='#0a0a14', highlightthickness=0)
        scrollbar = tk.Scrollbar(settings_win, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#0a0a14')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        frame = scrollable_frame
        
        tk.Label(
            frame,
            text="⚙️ Ayarlar",
            font=('Segoe UI', 18, 'bold'),
            fg='#e8e8f0',
            bg='#0a0a14'
        ).pack(pady=(15, 12))
        
        # Yayıncı Adı
        tk.Label(frame, text="Yayıncı Adı:", font=('Segoe UI', 11), fg='#8888bb', bg='#0a0a14').pack(anchor=tk.W, padx=25)
        username_entry = tk.Entry(frame, font=('Segoe UI', 11), bg='#141425', fg='#e8e8f0', relief=tk.FLAT, bd=0)
        username_entry.insert(0, KICK_USERNAME)
        username_entry.pack(fill=tk.X, padx=25, pady=(5, 10))
        
        # Kontrol Aralığı
        tk.Label(frame, text="Kontrol Aralığı (saniye):", font=('Segoe UI', 11), fg='#8888bb', bg='#0a0a14').pack(anchor=tk.W, padx=25)
        interval_entry = tk.Entry(frame, font=('Segoe UI', 11), bg='#141425', fg='#e8e8f0', relief=tk.FLAT, bd=0)
        interval_entry.insert(0, str(CHECK_INTERVAL))
        interval_entry.pack(fill=tk.X, padx=25, pady=(5, 12))
        
        # Ses
        sound_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame, text="🔊 Sesli Bildirim",
            variable=sound_var, bg='#0a0a14', fg='#8888bb',
            selectcolor='#141425', activebackground='#0a0a14'
        ).pack(anchor=tk.W, padx=25, pady=2)
        
        # Discord
        discord_var = tk.BooleanVar(value=bool(config.get('discord_webhook', '')))
        tk.Checkbutton(
            frame, text="💬 Discord Bildirimi",
            variable=discord_var, bg='#0a0a14', fg='#8888bb',
            selectcolor='#141425', activebackground='#0a0a14'
        ).pack(anchor=tk.W, padx=25, pady=2)
        discord_entry = tk.Entry(frame, font=('Segoe UI', 10), bg='#141425', fg='#8888bb', relief=tk.FLAT, bd=0)
        discord_entry.insert(0, config.get('discord_webhook', ''))
        discord_entry.pack(fill=tk.X, padx=25, pady=(2, 8))
        discord_entry.config(show='*')
        
        # Telegram
        telegram_var = tk.BooleanVar(value=bool(config.get('telegram_bot', '')))
        tk.Checkbutton(
            frame, text="📱 Telegram Bildirimi",
            variable=telegram_var, bg='#0a0a14', fg='#8888bb',
            selectcolor='#141425', activebackground='#0a0a14'
        ).pack(anchor=tk.W, padx=25, pady=2)
        tk.Label(frame, text="Bot Token:", font=('Segoe UI', 9), fg='#8888bb', bg='#0a0a14').pack(anchor=tk.W, padx=25)
        tg_bot_entry = tk.Entry(frame, font=('Segoe UI', 10), bg='#141425', fg='#8888bb', relief=tk.FLAT, bd=0)
        tg_bot_entry.insert(0, config.get('telegram_bot', ''))
        tg_bot_entry.pack(fill=tk.X, padx=25, pady=(2, 2))
        tg_bot_entry.config(show='*')
        tk.Label(frame, text="Chat ID:", font=('Segoe UI', 9), fg='#8888bb', bg='#0a0a14').pack(anchor=tk.W, padx=25)
        tg_chat_entry = tk.Entry(frame, font=('Segoe UI', 10), bg='#141425', fg='#8888bb', relief=tk.FLAT, bd=0)
        tg_chat_entry.insert(0, config.get('telegram_chat', ''))
        tg_chat_entry.pack(fill=tk.X, padx=25, pady=(2, 8))
        tg_chat_entry.config(show='*')
        
        # Pushbullet
        push_var = tk.BooleanVar(value=bool(config.get('pushbullet_api', '')))
        tk.Checkbutton(
            frame, text="📲 Pushbullet Bildirimi",
            variable=push_var, bg='#0a0a14', fg='#8888bb',
            selectcolor='#141425', activebackground='#0a0a14'
        ).pack(anchor=tk.W, padx=25, pady=2)
        push_entry = tk.Entry(frame, font=('Segoe UI', 10), bg='#141425', fg='#8888bb', relief=tk.FLAT, bd=0)
        push_entry.insert(0, config.get('pushbullet_api', ''))
        push_entry.pack(fill=tk.X, padx=25, pady=(2, 12))
        push_entry.config(show='*')
        
        def save_settings():
            global KICK_USERNAME, CHECK_INTERVAL
            KICK_USERNAME = username_entry.get().strip() or KICK_USERNAME
            try:
                CHECK_INTERVAL = int(interval_entry.get().strip())
                if CHECK_INTERVAL < 5:
                    CHECK_INTERVAL = 5
                self.speed_slider.set(CHECK_INTERVAL)
                self.speed_label.config(text=f"{CHECK_INTERVAL} saniye")
                self.speed_display.config(text=f"⏱️ {CHECK_INTERVAL}s")
            except:
                pass
            
            config = {
                'discord_webhook': discord_entry.get().strip() if discord_var.get() else '',
                'telegram_bot': tg_bot_entry.get().strip() if telegram_var.get() else '',
                'telegram_chat': tg_chat_entry.get().strip() if telegram_var.get() else '',
                'pushbullet_api': push_entry.get().strip() if push_var.get() else '',
                'sound': sound_var.get()
            }
            save_config(config)
            self.sound.enabled = sound_var.get()
            
            self.channel_label.config(text=KICK_USERNAME)
            self.add_log(f"⚙️ Ayarlar güncellendi")
            settings_win.destroy()
        
        tk.Button(
            frame,
            text="💾 Kaydet ve Kapat",
            font=('Segoe UI', 12, 'bold'),
            bg='#2a2a50',
            fg='#e8e8f0',
            activebackground='#3a3a60',
            relief=tk.FLAT,
            padx=30,
            pady=10,
            command=save_settings
        ).pack(pady=15)
    
    def worker_loop(self):
        counter = 0
        while self.is_running:
            try:
                current_status, stream_data = check_live_status(KICK_USERNAME)
                counter += 1
                
                if current_status and current_status.get('is_live'):
                    self.root.after(0, lambda: self.update_status(True, current_status))
                    if not self.notified:
                        self.root.after(0, lambda: self.show_notification(current_status))
                        self.notified = True
                    self.last_status = True
                else:
                    if self.last_status:
                        self.root.after(0, lambda: self.update_status(False))
                        self.root.after(0, lambda: self.add_log("⏹️ Yayın sona erdi"))
                        if self.current_stream_id:
                            self.db.end_stream(self.current_stream_id)
                            self.current_stream_id = None
                        self.notified = False
                    self.last_status = False
                
                self.stats.add_check()
                self.root.after(0, lambda: self.counter_label.config(text=f"#{self.stats.total_checks}"))
                self.root.after(0, lambda: self.status_bar_label.config(
                    text=f"✅ Son kontrol: {datetime.now().strftime('%H:%M:%S')} (#{self.stats.total_checks})"
                ))
                
                time.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                log_message(f"⚠️ Döngü hatası: {e}")
                time.sleep(CHECK_INTERVAL)
    
    def setup_tray(self):
        try:
            from PIL import Image, ImageDraw
            icon_image = Image.new('RGBA', (64, 64), color=(10, 10, 20, 255))
            d = ImageDraw.Draw(icon_image)
            d.rectangle([8, 8, 56, 56], fill=(255, 60, 60, 255))
            d.text((16, 12), "Z", fill=(255, 255, 255, 255))
            
            def on_quit(icon, item):
                icon.stop()
                self.on_closing()
            
            def show_window(icon, item):
                self.root.deiconify()
                self.root.attributes('-topmost', True)
                self.root.attributes('-topmost', False)
            
            def manual_check(icon, item):
                self.manual_check()
            
            menu = (
                pystray.MenuItem("📺 Göster", show_window),
                pystray.MenuItem("🔄 Kontrol Et", manual_check),
                pystray.MenuItem("❌ Çıkış", on_quit)
            )
            
            self.tray_icon = pystray.Icon("zeratracker", icon_image, APP_NAME, menu)
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        except:
            pass
    
    def on_closing(self):
        self.is_running = False
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except:
            pass
        self.db.close()
        try:
            self.root.destroy()
        except:
            pass
        sys.exit(0)

# ============================================================
# BAŞLAT
# ============================================================
if __name__ == "__main__":
    try:
        import requests
    except ImportError:
        print("[-] requests kütüphanesi yüklü değil. Kurulum: pip install requests")
        sys.exit(1)
    
    log_message("🚀 Uygulama başlatıldı.")
    try:
        app = ZeraTrackerApp()
    except KeyboardInterrupt:
        print("\n[!] Kapatıldı.")
    except Exception as e:
        log_message(f"💥 Hata: {e}")
        try:
            messagebox.showerror("Hata", f"Bir hata oluştu:\n{e}")
        except:
            print(f"[-] Hata: {e}")
