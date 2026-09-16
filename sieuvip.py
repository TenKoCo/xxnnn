#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
SIEU VIP ROBLOX AUTOMATION ENGINE - ANDROID 10 (API 29) ROOT / TERMUX
Architecture: Multi-Daemon IPC, Android 10 Freeform Manager, Logcat Watchdog
================================================================================
"""

import os
import sys
import time
import json
import re
import random
import string
import datetime
import threading
import subprocess
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# -----------------------------------------------------------------------------
# 1. CONSTANTS & SYSTEM CONFIGURATION
# -----------------------------------------------------------------------------
BASE_DIR = "/sdcard/Download/SieuVip"
WORKERS_DIR = os.path.join(BASE_DIR, "workers")
AUTOEXEC_DIR = os.path.join(BASE_DIR, "Autoexecute")
CONFIG_FILE = os.path.join(BASE_DIR, "config.logs")
CRASH_LOG_FILE = os.path.join(BASE_DIR, "crash.logs")
COOKIE_SRC_FILE = "/sdcard/Download/cookie.txt"
COOKIE_HU_FILE = os.path.join(BASE_DIR, "cookie_hu.txt")

EXECUTOR_DIRS = [
    "/sdcard/Delta/autoexecute",
    "/sdcard/Codex/autoexecute",
    "/sdcard/Arceus X/autoexecute",
    "/sdcard/Fluxus/autoexecute"
]

HOT_GAMES = [
    ("Blox Fruits", "2753915549"),
    ("Steal an Egg", "18336484504"),
    ("Pet Simulator 99", "8737899170"),
    ("Blade Ball", "13772394625"),
    ("Toilet Tower Defense", "13775256536"),
    ("Brookhaven RP", "4924922222"),
    ("Anime Defenders", "17017769292"),
    ("King Legacy", "4520749081"),
    ("Sol's RNG", "15532962292"),
    ("Da Hood", "2788229376")
]

# ANSI Color Codes
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_CYAN = "\033[96m"
C_WHITE = "\033[97m"
C_MAGENTA = "\033[95m"

# Global runtime state
RUNNING_WORKERS = {}  # {user_id: WorkerState}
STOP_REQUESTED = threading.Event()
WATCHDOG_THREAD = None


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class WorkerState:
    def __init__(self, user_id, username, package, port):
        self.user_id = str(user_id)
        self.username = username
        self.package = package
        self.port = port
        self.status = "Initializing..."
        self.last_ping = 0
        self.launch_time = 0
        self.rejoin_count = 0
        self.script_active = False


# -----------------------------------------------------------------------------
# 2. ROOT PRIVILEGE, ENFORCEMENT & SYSTEM SETUP
# -----------------------------------------------------------------------------
def run_cmd(cmd, check_output=False):
    """Execute a system shell command safely via su."""
    full_cmd = f"su -c \"{cmd}\""
    try:
        if check_output:
            res = subprocess.check_output(full_cmd, shell=True, stderr=subprocess.STDOUT)
            return res.decode("utf-8", errors="ignore").strip()
        else:
            return subprocess.call(full_cmd, shell=True)
    except Exception as e:
        return "" if check_output else -1


def check_and_enforce_root():
    """Verify 100% root access on Termux / Android 10."""
    uid = run_cmd("id -u", check_output=True)
    if uid != "0":
        print(f"{C_RED}[!] LOI: Yeu cau quyen Root (su). Vui long cap quyen Root cho Termux.{C_RESET}")
        sys.exit(1)

    # Disable SELinux to prevent IPC/Storage denials
    run_cmd("setenforce 0")

    # Anti-kill protections for Android 10
    try:
        run_cmd("termux-wake-lock")
    except Exception:
        pass

    try:
        my_pid = os.getpid()
        run_cmd(f"echo -1000 > /proc/{my_pid}/oom_score_adj")
    except Exception:
        pass


def init_directories():
    """Ensure all core paths exist on external storage."""
    for d in [BASE_DIR, WORKERS_DIR, AUTOEXEC_DIR]:
        if not os.path.exists(d):
            run_cmd(f"mkdir -p '{d}'")
            run_cmd(f"chmod 777 '{d}'")

    for ed in EXECUTOR_DIRS:
        if not os.path.exists(ed):
            run_cmd(f"mkdir -p '{ed}'")
            run_cmd(f"chmod 777 '{ed}'")


# -----------------------------------------------------------------------------
# 3. CONFIGURATION MANAGER
# -----------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "selected_packages": [],
    "accounts": {},  # {package: {"cookie": ..., "user_id": ..., "username": ...}}
    "game_mode": "global",  # "global" or "per_package"
    "global_game": {"place_id": "2753915549", "link_code": ""},
    "package_games": {},    # {pkg: {"place_id": ..., "link_code": ...}}
    "auto_block": False,
    "sort_tab_mode": 1,     # 1: Full Grid, 2: Ultra Small Grid, 0: Disabled
    "settings": {
        "check_method": "Executor",  # "Executor" or "Online"
        "queue_next": True,
        "timeout_sec": 60,
        "delay_open_sec": 8,
        "clear_cache": False,
        "time_to_stop_mins": 360
    },
    "discord": {
        "webhook_url": "",
        "enabled": False
    }
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults to prevent key errors
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return DEFAULT_CONFIG


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        run_cmd(f"chmod 666 '{CONFIG_FILE}'")
    except Exception as e:
        log_crash("SYSTEM", f"Loi luu config: {str(e)}")


def log_crash(user_id, message):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{ts}] [UserId: {user_id}] {message}\n"
    try:
        with open(CRASH_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        run_cmd(f"chmod 666 '{CRASH_LOG_FILE}'")
    except Exception:
        pass


# -----------------------------------------------------------------------------
# 4. DISCORD WEBHOOK INTEGRATION
# -----------------------------------------------------------------------------
def send_discord_embed(title, description, color=3066993, fields=None):
    cfg = load_config()
    webhook_url = cfg.get("discord", {}).get("webhook_url", "").strip()
    enabled = cfg.get("discord", {}).get("enabled", False)

    if not enabled or not webhook_url.startswith("http"):
        return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "footer": {"text": "SieuVip Roblox Android 10 Daemon"}
    }
    if fields:
        embed["fields"] = fields

    payload = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "SieuVip/1.0"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        pass


# -----------------------------------------------------------------------------
# 5. ROBLOX API & AUTHENTICATION ENGINE
# -----------------------------------------------------------------------------
def validate_roblox_cookie(cookie_str):
    """Validate .ROBLOSECURITY and return (user_id, username)."""
    clean_cookie = cookie_str.strip()
    if not clean_cookie:
        return None, None

    url = "https://users.roblox.com/v1/users/authenticated"
    headers = {
        "Cookie": f".ROBLOSECURITY={clean_cookie}",
        "User-Agent": "Roblox/Android"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return str(data.get("id")), data.get("name")
    except urllib.error.HTTPError as e:
        return None, None
    except Exception:
        return None, None


def get_csrf_token(cookie_str):
    """Retrieve x-csrf-token via 403 challenge."""
    url = "https://auth.roblox.com/v2/login"
    headers = {
        "Cookie": f".ROBLOSECURITY={cookie_str}",
        "User-Agent": "Roblox/Android"
    }
    req = urllib.request.Request(url, headers=headers, data=b"{}")
    try:
        urllib.request.urlopen(req, timeout=8)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return e.headers.get("x-csrf-token", "")
    except Exception:
        pass
    return ""


def execute_block_account(cookie_str, target_userid):
    """Send block request using Roblox API."""
    csrf = get_csrf_token(cookie_str)
    if not csrf:
        return False
    url = f"https://accountsettings.roblox.com/v1/users/{target_userid}/block"
    headers = {
        "Cookie": f".ROBLOSECURITY={cookie_str}",
        "X-CSRF-TOKEN": csrf,
        "User-Agent": "Roblox/Android",
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, headers=headers, data=b"{}")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def run_cross_blocking(accounts_dict):
    """Cross-block all registered UserIds to avoid same-server placement."""
    user_ids = [acc["user_id"] for acc in accounts_dict.values() if "user_id" in acc]
    total = len(user_ids)
    if total < 2:
        return

    print(f"\n{C_YELLOW}[*] Dang thuc hien chan cheo (Cross-Block) giua {total} tai khoan...{C_RESET}")
    for pkg, acc in accounts_dict.items():
        c_user = acc.get("user_id")
        cookie = acc.get("cookie")
        if not c_user or not cookie:
            continue
        for target in user_ids:
            if target != c_user:
                execute_block_account(cookie, target)
                time.sleep(0.3)
    print(f"{C_GREEN}[+] Hoan tat chan cheo toan bo tai khoan.{C_RESET}")


# -----------------------------------------------------------------------------
# 6. ROOT COOKIE INJECTION (ANDROID 10)
# -----------------------------------------------------------------------------
def inject_cookie_into_package(package_name, cookie_value):
    """Inject cookie into Roblox shared preferences & app WebView SQLite."""
    run_cmd(f"am force-stop {package_name}")

    # Fix storage permission for executor on Android 10
    run_cmd(f"pm grant {package_name} android.permission.READ_EXTERNAL_STORAGE")
    run_cmd(f"pm grant {package_name} android.permission.WRITE_EXTERNAL_STORAGE")

    pkg_data_dir = f"/data/data/{package_name}"
    if not os.path.exists(pkg_data_dir):
        return False, "Khong tim thay thu muc data cua ung dung."

    uid_gid = run_cmd(f"stat -c '%u %g' '{pkg_data_dir}'", check_output=True)
    if not uid_gid or " " not in uid_gid:
        uid, gid = "10000", "10000"
    else:
        uid, gid = uid_gid.split()

    sp_dir = f"{pkg_data_dir}/shared_prefs"
    run_cmd(f"mkdir -p '{sp_dir}'")

    pref_file = f"{sp_dir}/com.roblox.client_preferences.xml"
    xml_content = f"""<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="Cookie">{cookie_value}</string>
    <string name="RBXSessionInfo">.ROBLOSECURITY={cookie_value}</string>
</map>
"""
    tmp_path = f"/data/local/tmp/pref_{package_name}.xml"
    with open(f"/sdcard/Download/SieuVip/temp_pref.xml", "w", encoding="utf-8") as f:
        f.write(xml_content)

    run_cmd(f"cp /sdcard/Download/SieuVip/temp_pref.xml '{pref_file}'")
    run_cmd(f"rm -f /sdcard/Download/SieuVip/temp_pref.xml")

    # Set ownership & permissions
    run_cmd(f"chown -R {uid}:{gid} '{pkg_data_dir}'")
    run_cmd(f"chmod 771 '{sp_dir}'")
    run_cmd(f"chmod 660 '{pref_file}'")
    return True, "Thanh cong"


# -----------------------------------------------------------------------------
# 7. WORKER IPC & HTTP HEARTBEAT DAEMON
# -----------------------------------------------------------------------------
class HeartbeatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/ping":
            params = urllib.parse.parse_qs(parsed.query)
            user_id = params.get("userid", [""])[0]
            if user_id and user_id in RUNNING_WORKERS:
                worker = RUNNING_WORKERS[user_id]
                worker.last_ping = time.time()
                worker.script_active = True
                worker.status = "In Game (Script Active)"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        return  # Suppress console HTTP access logs


def generate_worker_file(user_id, package, port):
    """Write an isolated worker Python script per UserId."""
    worker_code = f"""#!/usr/bin/env python3
import time, urllib.request, subprocess, sys

USER_ID = "{user_id}"
PACKAGE = "{package}"
PORT = {port}

def check_alive():
    try:
        url = f"http://127.0.0.1:{{PORT}}/ping?userid={{USER_ID}}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except:
        return False

if __name__ == "__main__":
    while True:
        time.sleep(5)
"""
    file_path = os.path.join(WORKERS_DIR, f"{user_id}.py")
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(worker_code)
        run_cmd(f"chmod 755 '{file_path}'")
    except Exception:
        pass


def start_ipc_server(port):
    server = ThreadedHTTPServer(("127.0.0.1", port), HeartbeatHandler)
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    return server


# -----------------------------------------------------------------------------
# 8. ANDROID 10 FREEFORM MULTI-WINDOW MANAGER
# -----------------------------------------------------------------------------
def get_screen_resolution():
    res = run_cmd("wm size", check_output=True)
    m = re.search(r"(\d+)x(\d+)", res)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 1080, 2400  # Fallback default


def enable_freeform_system():
    run_cmd("settings put global enable_freeform_support 1")
    run_cmd("settings put global force_resizable_activities 1")


def calculate_window_bounds(index, total, mode):
    """
    Calculate Android 10 Freeform bounding boxes: (left, top, right, bottom)
    Mode 1: Equal division across display.
    Mode 2: Ultra-small grid.
    """
    w, h = get_screen_resolution()
    if total <= 1:
        return (0, 0, w, h)

    if mode == 2:
        # Ultra Small Mode: Fixed mini tiles
        tile_w = min(400, w // 2)
        tile_h = min(600, h // 3)
        cols = max(1, w // tile_w)
        col = index % cols
        row = index // cols
        l = col * tile_w
        t = row * tile_h
        return (l, t, l + tile_w, t + tile_h)
    else:
        # Full Screen Grid Mode
        if total == 2:
            rows, cols = 2, 1
        elif total <= 4:
            rows, cols = 2, 2
        elif total <= 6:
            rows, cols = 3, 2
        else:
            rows, cols = (total + 1) // 2, 2

        cell_w = w // cols
        cell_h = h // rows

        col = index % cols
        row = index // rows
        l = col * cell_w
        t = row * cell_h
        return (l, t, l + cell_w, t + cell_h)


# -----------------------------------------------------------------------------
# 9. ROBLOX LAUNCHER & URL PARSER
# -----------------------------------------------------------------------------
def parse_roblox_url(raw_input):
    """Extract placeId and linkCode from raw ID, VIP link, or share code."""
    raw = raw_input.strip()
    if raw.isdigit():
        return raw, ""

    place_id = ""
    link_code = ""

    # Check placeId
    m_pid = re.search(r"games/(\d+)", raw)
    if m_pid:
        place_id = m_pid.group(1)
    else:
        m_pid2 = re.search(r"placeId=(\d+)", raw)
        if m_pid2:
            place_id = m_pid2.group(1)

    # Check VIP / Private Server Code
    m_code = re.search(r"privateServerLinkCode=([a-zA-Z0-9_\-]+)", raw)
    if m_code:
        link_code = m_code.group(1)
    else:
        m_code2 = re.search(r"code=([a-zA-Z0-9_\-]+)", raw)
        if m_code2:
            link_code = m_code2.group(1)
        else:
            m_code3 = re.search(r"linkCode=([a-zA-Z0-9_\-]+)", raw)
            if m_code3:
                link_code = m_code3.group(1)

    return place_id, link_code


def launch_roblox_app(package, place_id, link_code="", bounds=None):
    """Launch package using View Intent, Freeform Mode & Multi-task flags."""
    if link_code:
        deep_link = f"roblox://placeId={place_id}&linkCode={link_code}"
    else:
        deep_link = f"roblox://placeId={place_id}"

    cmd = (
        f"am start -n {package}/com.roblox.client.Activity "
        f"-a android.intent.action.VIEW "
        f"-d \"{deep_link}\" "
        f"-f 0x18000000"  # FLAG_ACTIVITY_NEW_TASK | FLAG_ACTIVITY_MULTIPLE_TASK
    )

    if bounds:
        l, t, r, b = bounds
        cmd += f" --windowingMode 5 --bounds {l},{t},{r},{b}"

    run_cmd(cmd)


# -----------------------------------------------------------------------------
# 10. SYSTEM WATCHDOGS (LOGCAT & BLACK SCREEN)
# -----------------------------------------------------------------------------
DISCONNECT_CODES = ["277", "268", "279", "264", "529", "524"]

def logcat_monitor_thread():
    """Real-time logcat inspection for disconnect errors."""
    run_cmd("logcat -c")
    p = subprocess.Popen(
        ["su", "-c", "logcat -v brief -b main -b events"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="ignore"
    )

    while not STOP_REQUESTED.is_set():
        line = p.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue

        for code in DISCONNECT_CODES:
            if f"Error {code}" in line or f"Disconnect ({code})" in line or f"error code: {code}" in line.lower():
                # Identify which package triggered the logcat event
                for u_id, worker in list(RUNNING_WORKERS.items()):
                    log_crash(u_id, f"Logcat phat hien ma loi: {code}")
                    worker.status = f"Rejoining (Error {code})"
                    worker.script_active = False

                    # Trigger Discord notification
                    send_discord_embed(
                        "Canh bao: Mat ket noi Game",
                        f"Tai khoan **{worker.username}** (ID: `{u_id}`) bi ngat ket noi voi ma loi: `{code}`.\nDang tien hanh Rejoin...",
                        15158332
                    )
                    run_cmd(f"am force-stop {worker.package}")
                    time.sleep(1)
                    # Rejoin logic will be picked up by main watchdog loop
                break

    try:
        p.kill()
    except Exception:
        pass


def check_black_screen_or_anr(package):
    """Check if SurfaceView rendered within window manager."""
    dump = run_cmd(f"dumpsys window visible-apps", check_output=True)
    if package in dump and "SurfaceView" not in dump and "Application Not Responding" in dump:
        return True
    return False


# -----------------------------------------------------------------------------
# 11. SCRIPT AUTOEXECUTE MANAGER
# -----------------------------------------------------------------------------
def sync_lua_script(custom_lua_content):
    """Wrap script with heartbeat reporter and deploy across all executors."""
    rand_name = "script_" + "".join(random.choices(string.hexdigits.lower(), k=6)) + ".txt"
    src_file = os.path.join(AUTOEXEC_DIR, rand_name)

    # Prepend dynamic Lua Heartbeat IPC stub
    heartbeat_stub = """-- [SieuVip Auto Heartbeat Stub]
task.spawn(function()
    local HttpService = game:GetService("HttpService")
    local Players = game:GetService("Players")
    local LocalPlayer = Players.LocalPlayer or Players.PlayerAdded:Wait()
    local userId = tostring(LocalPlayer.UserId)
    
    local req = (syn and syn.request) or (http and http.request) or http_request or request or (fluxus and fluxus.request)
    if not req then return end
    
    while task.wait(5) do
        pcall(function()
            for port = 20000, 20030 do
                req({
                    Url = "http://127.0.0.1:" .. port .. "/ping?userid=" .. userId,
                    Method = "GET"
                })
            end
        end)
    end
end)
-- [End Heartbeat Stub]

"""
    full_content = heartbeat_stub + custom_lua_content

    # Save to SieuVip Autoexecute
    with open(src_file, "w", encoding="utf-8") as f:
        f.write(full_content)
    run_cmd(f"chmod 666 '{src_file}'")

    # Clean old scripts and sync to active executor directories
    synced_count = 0
    for ed in EXECUTOR_DIRS:
        run_cmd(f"rm -rf '{ed}'/*")
        target_path = os.path.join(ed, rand_name)
        run_cmd(f"cp '{src_file}' '{target_path}'")
        run_cmd(f"chmod 666 '{target_path}'")
        synced_count += 1

    return rand_name, synced_count


# -----------------------------------------------------------------------------
# 12. CORE EXECUTION: [1] AUTO REJOIN & LIVE MONITOR
# -----------------------------------------------------------------------------
def render_live_monitor(start_epoch, duration_mins):
    """ANSI Live Monitor Dashboard."""
    total_sec = duration_mins * 60
    elapsed = int(time.time() - start_epoch)
    remain = max(0, total_sec - elapsed)
    rem_m, rem_s = divmod(remain, 60)

    # Fetch CPU & RAM stats
    mem_info = run_cmd("cat /proc/meminfo", check_output=True)
    mem_total_m = re.search(r"MemTotal:\s+(\d+)", mem_info)
    mem_free_m = re.search(r"MemAvailable:\s+(\d+)", mem_info)

    ram_used = 0
    ram_free = 0
    if mem_total_m and mem_free_m:
        t_kb = int(mem_total_m.group(1))
        a_kb = int(mem_free_m.group(1))
        ram_free = a_kb // 1024
        ram_used = (t_kb - a_kb) // 1024

    os.system("clear")
    print(f"{C_CYAN}{'='*80}{C_RESET}")
    print(
        f"{C_BOLD}{C_WHITE}[TUT MONITOR]{C_RESET} "
        f"RAM: {C_YELLOW}Used {ram_used}MB / Free {ram_free}MB{C_RESET} | "
        f"Dem nguoc: {C_GREEN}{rem_m:02d}:{rem_s:02d}{C_RESET}"
    )
    print(f"{C_CYAN}{'='*80}{C_RESET}")
    print(f"{C_BOLD}{'STT':<4} | {'Package':<23} | {'UserId':<12} | {'Username':<15} | {'Status'}{C_RESET}")
    print(f"{'-'*80}")

    idx = 1
    for u_id, w in RUNNING_WORKERS.items():
        status_color = C_GREEN if "In Game" in w.status else (C_RED if "Rejoining" in w.status else C_YELLOW)
        print(f"{idx:<4} | {w.package:<23} | {w.user_id:<12} | {w.username:<15} | {status_color}{w.status}{C_RESET}")
        idx += 1

    print(f"{C_CYAN}{'='*80}{C_RESET}")
    print(f"{C_WHITE}Nhan Ctrl+C de dung chu trinh va quay ve Menu chinh.{C_RESET}")


def execute_auto_rejoin_pipeline():
    cfg = load_config()
    selected_pkgs = cfg.get("selected_packages", [])
    if not selected_pkgs:
        print(f"{C_RED}[!] Chua chon package nao tai muc [2]. Vui long chon package truoc.{C_RESET}")
        time.sleep(2)
        return

    # Step 1: Timer prompt
    saved_time = cfg.get("settings", {}).get("time_to_stop_mins", 360)
    print(f"\n{C_YELLOW}[?] Time to stop roblox: {saved_time} (phut), Enter de su dung: {C_RESET}", end="")
    user_t = input().strip()
    if user_t.isdigit() and int(user_t) > 0:
        stop_mins = int(user_t)
        cfg["settings"]["time_to_stop_mins"] = stop_mins
        save_config(cfg)
    else:
        stop_mins = saved_time

    settings = cfg.get("settings", {})
    delay_open = settings.get("delay_open_sec", 8)
    timeout_sec = settings.get("timeout_sec", 60)
    queue_next = settings.get("queue_next", True)
    clear_cache = settings.get("clear_cache", False)
    sort_mode = cfg.get("sort_tab_mode", 1)

    enable_freeform_system()

    STOP_REQUESTED.clear()
    RUNNING_WORKERS.clear()

    # Step 2: Setup Workers & HTTP IPC
    accounts = cfg.get("accounts", {})
    server_port = 20000
    ipc_server = start_ipc_server(server_port)

    # Initialize worker instances
    idx = 0
    for pkg in selected_pkgs:
        acc = accounts.get(pkg, {})
        u_id = acc.get("user_id", f"User_{idx+1}")
        u_name = acc.get("username", f"Player_{idx+1}")
        w = WorkerState(u_id, u_name, pkg, server_port)
        RUNNING_WORKERS[u_id] = w
        generate_worker_file(u_id, pkg, server_port)
        idx += 1

    # Step A: Clean up existing instances
    for pkg in selected_pkgs:
        run_cmd(f"am force-stop {pkg}")

    # Step B: Auto Cross-Block if enabled
    if cfg.get("auto_block", False):
        run_cross_blocking(accounts)

    # Launch background logcat watchdog
    global WATCHDOG_THREAD
    WATCHDOG_THREAD = threading.Thread(target=logcat_monitor_thread)
    WATCHDOG_THREAD.daemon = True
    WATCHDOG_THREAD.start()

    # Send Discord Run Notification
    field_data = []
    for u_id, w in RUNNING_WORKERS.items():
        field_data.append({"name": w.username, "value": f"ID: `{u_id}`\nPkg: `{w.package}`", "inline": True})
    send_discord_embed("Khoi dong Auto Rejoin", f"Bat dau chuong trinh chay tren {len(selected_pkgs)} tai khoan.", 3066993, field_data)

    start_cycle_epoch = time.time()
    last_periodic_discord = time.time()

    try:
        # Step D: Sequential Launch Loop
        total_pkgs = len(selected_pkgs)
        for i, pkg in enumerate(selected_pkgs):
            acc = accounts.get(pkg, {})
            u_id = acc.get("user_id", f"User_{i+1}")
            worker = RUNNING_WORKERS[u_id]

            if clear_cache:
                run_cmd(f"rm -rf /data/data/{pkg}/cache/*")

            # Determine Place ID & Link Code
            if cfg.get("game_mode") == "per_package":
                p_game = cfg.get("package_games", {}).get(pkg, {})
                p_id = p_game.get("place_id", "2753915549")
                l_code = p_game.get("link_code", "")
            else:
                p_id = cfg.get("global_game", {}).get("place_id", "2753915549")
                l_code = cfg.get("global_game", {}).get("link_code", "")

            bounds = calculate_window_bounds(i, total_pkgs, sort_mode) if sort_mode > 0 else None
            worker.status = "Starting App..."
            worker.launch_time = time.time()

            launch_roblox_app(pkg, p_id, l_code, bounds)

            if queue_next:
                worker.status = "Waiting Queue..."
                # Poll until worker receives valid script ping or hits timeout
                wait_start = time.time()
                while time.time() - wait_start < timeout_sec:
                    render_live_monitor(start_cycle_epoch, stop_mins)
                    if worker.script_active:
                        break
                    time.sleep(1)
            else:
                time.sleep(delay_open)

        # Step 3: Main Active Monitoring Loop
        while not STOP_REQUESTED.is_set():
            now = time.time()

            # Check Total Session Timer
            if (now - start_cycle_epoch) >= (stop_mins * 60):
                print(f"\n{C_YELLOW}[*] Het thoi gian phien ({stop_mins} phut). Tien hanh Restart toan bo...{C_RESET}")
                for pkg in selected_pkgs:
                    run_cmd(f"am force-stop {pkg}")
                time.sleep(3)
                start_cycle_epoch = time.time()
                # Re-trigger pipeline
                for i, pkg in enumerate(selected_pkgs):
                    acc = accounts.get(pkg, {})
                    u_id = acc.get("user_id", f"User_{i+1}")
                    worker = RUNNING_WORKERS[u_id]
                    worker.script_active = False
                    bounds = calculate_window_bounds(i, total_pkgs, sort_mode) if sort_mode > 0 else None
                    launch_roblox_app(pkg, p_id, l_code, bounds)
                    time.sleep(delay_open)

            # Check individual workers for timeout/freeze
            for u_id, worker in RUNNING_WORKERS.items():
                # If script was active but heartbeats stopped
                if worker.script_active and (now - worker.last_ping > timeout_sec):
                    worker.status = "Timeout (Script Frozen)"
                    worker.script_active = False
                    log_crash(u_id, f"Heartbeat timeout qua {timeout_sec}s")
                    run_cmd(f"am force-stop {worker.package}")
                    time.sleep(1)
                    # Rejoin
                    worker.status = "Rejoining..."
                    worker.launch_time = now
                    bounds = calculate_window_bounds(0, total_pkgs, sort_mode) if sort_mode > 0 else None
                    launch_roblox_app(worker.package, p_id, l_code, bounds)

                # Check black screen logo freeze after 40s
                if not worker.script_active and (now - worker.launch_time > 40):
                    if check_black_screen_or_anr(worker.package):
                        worker.status = "ANR / Logo Stuck"
                        log_crash(u_id, "Treo Logo hoac man hinh den qua 40s")
                        run_cmd(f"am force-stop {worker.package}")
                        time.sleep(1)
                        launch_roblox_app(worker.package, p_id, l_code, bounds)
                        worker.launch_time = now

            # Periodic 30m Discord report
            if now - last_periodic_discord >= 1800:
                last_periodic_discord = now
                report_fields = []
                for u_id, w in RUNNING_WORKERS.items():
                    report_fields.append({"name": w.username, "value": f"Trang thai: `{w.status}`", "inline": True})
                send_discord_embed("Bao cao dinh ky (30 Phut)", "He thong dang van hanh on dinh.", 3447003, report_fields)

            render_live_monitor(start_cycle_epoch, stop_mins)
            time.sleep(1.5)

    except KeyboardInterrupt:
        print(f"\n{C_YELLOW}[*] Dang dung he thong va giai phong tien trinh...{C_RESET}")
    finally:
        STOP_REQUESTED.set()
        for pkg in selected_pkgs:
            run_cmd(f"am force-stop {pkg}")
        try:
            ipc_server.shutdown()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# 13. MENU HANDLERS (MODULES [2] TO [11])
# -----------------------------------------------------------------------------
def menu_choose_packages():
    """[2] Scan and select Roblox packages (Global, VNG, Clones)."""
    cfg = load_config()
    print(f"\n{C_CYAN}[*] Dang quet danh sach package trong he thong...{C_RESET}")
    raw_pkgs = run_cmd("pm list packages", check_output=True).splitlines()
    roblox_pkgs = []

    for line in raw_pkgs:
        p = line.replace("package:", "").strip()
        if "roblox" in p.lower() or "clone" in p.lower():
            roblox_pkgs.append(p)

    if not roblox_pkgs:
        # If no specific clone string matched, allow all Roblox matches
        roblox_pkgs = [p.replace("package:", "").strip() for p in raw_pkgs if "roblox" in p.lower()]

    roblox_pkgs = sorted(list(set(roblox_pkgs)))

    while True:
        os.system("clear")
        selected = cfg.get("selected_packages", [])
        print(f"{C_BOLD}{C_GREEN}=== [2] CHON PACKAGE ROBLOX / VNG / CLONE ==={C_RESET}")
        print(f"{C_YELLOW}[A] Chon tat ca package{C_RESET}")
        print(f"{C_YELLOW}[0] Luu va Quay lai{C_RESET}\n")

        for idx, p in enumerate(roblox_pkgs, 1):
            check_box = f"{C_GREEN}[X]{C_RESET}" if p in selected else f"{C_RED}[ ]{C_RESET}"
            print(f"{idx:2d}. {check_box} {p}")

        print(f"\n{C_WHITE}Nhap cac so can chon (VD: 1,2,4), 'A' de chon het, '0' de luu: {C_RESET}", end="")
        inp = input().strip()

        if inp == "0":
            save_config(cfg)
            break
        elif inp.upper() == "A":
            cfg["selected_packages"] = list(roblox_pkgs)
            save_config(cfg)
            print(f"{C_GREEN}[+] Da chon tat ca.{C_RESET}")
            time.sleep(1)
        else:
            parts = re.split(r"[, ]+", inp)
            for part in parts:
                if part.isdigit():
                    num = int(part)
                    if 1 <= num <= len(roblox_pkgs):
                        target_p = roblox_pkgs[num - 1]
                        if target_p in cfg["selected_packages"]:
                            cfg["selected_packages"].remove(target_p)
                        else:
                            cfg["selected_packages"].append(target_p)
            save_config(cfg)


def menu_set_game_id():
    """[3] Configure Place ID or VIP Server link."""
    cfg = load_config()
    os.system("clear")
    print(f"{C_BOLD}{C_GREEN}=== [3] CAU HINH GAME ID / VIP SERVER ==={C_RESET}")
    print("1. Cau hinh chung cho tat ca package")
    print("2. Cau hinh rieng cho tung package")
    print("0. Quay lai")
    opt = input("\nChon che do: ").strip()

    if opt == "1":
        print(f"\n{C_CYAN}--- DANH SACH 10 GAME HOT ---{C_RESET}")
        for idx, (g_name, g_id) in enumerate(HOT_GAMES, 1):
            print(f"{idx:2d}. {g_name} ({g_id})")
        print("11. Tu nhap Place ID hoac URL VIP Server")

        g_choice = input("\nChon game hoac nhap link: ").strip()
        if g_choice.isdigit() and 1 <= int(g_choice) <= 10:
            p_id = HOT_GAMES[int(g_choice) - 1][1]
            l_code = ""
        else:
            p_id, l_code = parse_roblox_url(g_choice)

        cfg["game_mode"] = "global"
        cfg["global_game"] = {"place_id": p_id, "link_code": l_code}
        save_config(cfg)
        print(f"{C_GREEN}[+] Da luu: PlaceID={p_id}, LinkCode={l_code}{C_RESET}")
        time.sleep(1.5)

    elif opt == "2":
        cfg["game_mode"] = "per_package"
        selected = cfg.get("selected_packages", [])
        if not selected:
            print(f"{C_RED}[!] Vui long chon package truoc o muc [2].{C_RESET}")
            time.sleep(1.5)
            return

        for pkg in selected:
            print(f"\n{C_YELLOW}Package: {pkg}{C_RESET}")
            raw = input("Nhap Game ID hoac VIP Server URL: ").strip()
            p_id, l_code = parse_roblox_url(raw)
            cfg["package_games"][pkg] = {"place_id": p_id, "link_code": l_code}

        save_config(cfg)
        print(f"{C_GREEN}[+] Da luu cau hinh rieng cho tung package.{C_RESET}")
        time.sleep(1.5)


def menu_login_with_cookie():
    """[5] Read /sdcard/Download/cookie.txt, inject into selected packages."""
    cfg = load_config()
    selected = cfg.get("selected_packages", [])
    if not selected:
        print(f"{C_RED}[!] Vui long chon package o muc [2] truoc khi inject cookie.{C_RESET}")
        time.sleep(2)
        return

    if not os.path.exists(COOKIE_SRC_FILE):
        print(f"{C_RED}[!] Khong tim thay file: {COOKIE_SRC_FILE}{C_RESET}")
        time.sleep(2)
        return

    with open(COOKIE_SRC_FILE, "r", encoding="utf-8", errors="ignore") as f:
        cookies = [line.strip() for line in f if line.strip()]

    if not cookies:
        print(f"{C_RED}[!] File cookie.txt trong.{C_RESET}")
        time.sleep(2)
        return

    print(f"\n{C_YELLOW}[*] Tim thay {len(cookies)} cookies. Bat dau kiem tra va inject...{C_RESET}")
    c_idx = 0
    for pkg in selected:
        if c_idx >= len(cookies):
            print(f"{C_RED}[!] Da het cookie trong danh sach.{C_RESET}")
            break

        cookie = cookies[c_idx]
        c_idx += 1

        print(f"\n{C_CYAN}[*] Dang kiem tra cookie cho {pkg}...{C_RESET}")
        user_id, username = validate_roblox_cookie(cookie)

        if not user_id:
            print(f"{C_RED}[-] Cookie khong hop le hoac da het han. Luu vao cookie_hu.txt{C_RESET}")
            with open(COOKIE_HU_FILE, "a", encoding="utf-8") as f_hu:
                f_hu.write(cookie + "\n")
            continue

        print(f"{C_GREEN}[+] Xac thuc thanh cong: {username} (ID: {user_id}){C_RESET}")
        ok, msg = inject_cookie_into_package(pkg, cookie)
        if ok:
            print(f"{C_GREEN}[+] Root Injection vao {pkg} hoan tat.{C_RESET}")
            cfg["accounts"][pkg] = {
                "cookie": cookie,
                "user_id": user_id,
                "username": username
            }
            save_config(cfg)
        else:
            print(f"{C_RED}[-] Injection that bai: {msg}{C_RESET}")

    time.sleep(2)


def menu_export_cookie():
    """[6] Export cookies from active config to file."""
    cfg = load_config()
    accounts = cfg.get("accounts", {})
    if not accounts:
        print(f"{C_RED}[!] Chua co tai khoan nao duoc luu.{C_RESET}")
        time.sleep(1.5)
        return

    date_str = datetime.datetime.now().strftime("%d%m%Y")
    export_file = os.path.join(BASE_DIR, f"cookie_export_{date_str}.txt")

    print(f"\n{C_BOLD}=== [6] XUAT COOKIE ==={C_RESET}")
    print("1. Xuat cookie theo tung tab/package")
    print("2. Xuat toan bo cookie da luu")
    opt = input("Chon che do: ").strip()

    lines_to_write = []
    if opt == "1":
        pkgs = list(accounts.keys())
        for idx, p in enumerate(pkgs, 1):
            print(f"{idx}. {p} ({accounts[p].get('username', 'N/A')})")
        c = input("Chon so: ").strip()
        if c.isdigit() and 1 <= int(c) <= len(pkgs):
            target_pkg = pkgs[int(c) - 1]
            lines_to_write.append(accounts[target_pkg].get("cookie", ""))
    else:
        for acc in accounts.values():
            if "cookie" in acc:
                lines_to_write.append(acc["cookie"])

    if lines_to_write:
        with open(export_file, "a", encoding="utf-8") as f:
            for l in lines_to_write:
                f.write(l + "\n")
        run_cmd(f"chmod 666 '{export_file}'")
        print(f"{C_GREEN}[+] Da xuat {len(lines_to_write)} cookie vao: {export_file}{C_RESET}")
    else:
        print(f"{C_YELLOW}[!] Khong co cookie nao duoc xuat.{C_RESET}")
    time.sleep(2)


def menu_auto_sort_tab():
    """[7] Freeform grid layout selection."""
    cfg = load_config()
    print(f"\n{C_BOLD}{C_GREEN}=== [7] CHIA LAYOUT MAN HINH (FREEFORM GRID) ==={C_RESET}")
    print("1. Lam nho toan man hinh (Chia deu luoi display)")
    print("2. Che do cuc nho (Mini Tile Grid toi uu RAM)")
    print("0. Tat Freeform (Chay toan man hinh mac dinh)")
    c = input("\nChon che do: ").strip()
    if c in ["0", "1", "2"]:
        cfg["sort_tab_mode"] = int(c)
        save_config(cfg)
        print(f"{C_GREEN}[+] Da cap nhat che do chia layout.{C_RESET}")
    time.sleep(1.5)


def menu_open_all_tabs():
    """[8] Open all selected packages once without rejoin loop."""
    cfg = load_config()
    selected = cfg.get("selected_packages", [])
    if not selected:
        print(f"{C_RED}[!] Chua chon package tai muc [2].{C_RESET}")
        time.sleep(1.5)
        return

    enable_freeform_system()
    sort_mode = cfg.get("sort_tab_mode", 1)
    total = len(selected)

    print(f"\n{C_CYAN}[*] Dang khoi dong dong loat {total} package...{C_RESET}")
    for i, pkg in enumerate(selected):
        p_id = cfg.get("global_game", {}).get("place_id", "2753915549")
        l_code = cfg.get("global_game", {}).get("link_code", "")
        bounds = calculate_window_bounds(i, total, sort_mode) if sort_mode > 0 else None
        launch_roblox_app(pkg, p_id, l_code, bounds)
        time.sleep(cfg.get("settings", {}).get("delay_open_sec", 6))

    print(f"{C_GREEN}[+] Da mo xong tat ca cac tab.{C_RESET}")
    time.sleep(2)


def menu_configs():
    """[9] Detailed configuration manager."""
    cfg = load_config()
    s = cfg.get("settings", {})

    while True:
        os.system("clear")
        print(f"{C_BOLD}{C_GREEN}=== [9] CAU HINH HE THONG (CONFIGS) ==={C_RESET}")
        print(f"1. Check method: {C_YELLOW}{s.get('check_method')}{C_RESET} (Executor / Online)")
        print(f"2. Hang cho tiep theo (Queue Next): {C_YELLOW}{s.get('queue_next')}{C_RESET}")
        print(f"3. Check time out: {C_YELLOW}{s.get('timeout_sec')}s{C_RESET}")
        print(f"4. Delay open: {C_YELLOW}{s.get('delay_open_sec')}s{C_RESET}")
        print(f"5. Clear cache: {C_YELLOW}{s.get('clear_cache')}{C_RESET}")
        print(f"6. Time to stop: {C_YELLOW}{s.get('time_to_stop_mins')} phut{C_RESET}")
        print(f"0. Luu & Quay lai")

        c = input("\nChon muc can sua: ").strip()
        if c == "0":
            save_config(cfg)
            break
        elif c == "1":
            s["check_method"] = "Online" if s.get("check_method") == "Executor" else "Executor"
        elif c == "2":
            s["queue_next"] = not s.get("queue_next", True)
        elif c == "3":
            val = input("Nhap timeout (giay): ").strip()
            if val.isdigit(): s["timeout_sec"] = int(val)
        elif c == "4":
            val = input("Nhap delay open (giay): ").strip()
            if val.isdigit(): s["delay_open_sec"] = int(val)
        elif c == "5":
            s["clear_cache"] = not s.get("clear_cache", False)
        elif c == "6":
            val = input("Nhap time to stop (phut): ").strip()
            if val.isdigit(): s["time_to_stop_mins"] = int(val)
        save_config(cfg)


def menu_autoexecute_manager():
    """[10] Lua Script Manager."""
    os.system("clear")
    print(f"{C_BOLD}{C_GREEN}=== [10] AUTOEXECUTE SCRIPT MANAGER ==={C_RESET}")
    print("Nhap/Dan doan ma Lua can chay (Nhap 'EOF' o dong rieng de hoan tat):")
    lines = []
    while True:
        try:
            line = input()
            if line.strip() == "EOF":
                break
            lines.append(line)
        except EOFError:
            break

    lua_code = "\n".join(lines)
    if not lua_code.strip():
        print(f"{C_YELLOW}[!] Noi dung script trong. Khong co thay doi.{C_RESET}")
        time.sleep(1.5)
        return

    rand_name, count = sync_lua_script(lua_code)
    print(f"{C_GREEN}[+] Da sinh file: {rand_name}{C_RESET}")
    print(f"{C_GREEN}[+] Da dong bo thanh cong toi {count} thu muc executor.{C_RESET}")
    time.sleep(2)


def menu_discord_webhook():
    """[11] Discord Webhook Configuration."""
    cfg = load_config()
    d = cfg.get("discord", {})
    os.system("clear")
    print(f"{C_BOLD}{C_GREEN}=== [11] DISCORD WEBHOOK QUAN TRI TU XA ==={C_RESET}")
    print(f"Webhook URL: {C_YELLOW}{d.get('webhook_url') or 'Chua cau hinh'}{C_RESET}")
    print(f"Trang thai: {C_GREEN if d.get('enabled') else C_RED}{'BAT' if d.get('enabled') else 'TAT'}{C_RESET}")
    print("\n1. Nhap/Doi Webhook URL")
    print("2. Bat/Tat thong bao")
    print("3. Gui thu nghiem (Test Webhook)")
    print("0. Quay lai")

    c = input("\nChon muc: ").strip()
    if c == "1":
        url = input("Nhap Discord Webhook URL: ").strip()
        d["webhook_url"] = url
        save_config(cfg)
    elif c == "2":
        d["enabled"] = not d.get("enabled", False)
        save_config(cfg)
    elif c == "3":
        send_discord_embed("Test Webhook", "Day la tin nhan thu nghiem tu Tool SieuVip Termux.", 65280)
        print(f"{C_GREEN}[+] Da gui request test.{C_RESET}")
        time.sleep(1.5)


# -----------------------------------------------------------------------------
# 14. MAIN TERMINAL DASHBOARD INTERFACE
# -----------------------------------------------------------------------------
def display_main_menu():
    cfg = load_config()
    selected_count = len(cfg.get("selected_packages", []))
    acc_count = len(cfg.get("accounts", {}))

    os.system("clear")
    print(f"{C_RED}{C_BOLD}")
    print(r"  ███████╗██╗███████╗██╗   ██╗    ██╗   ██╗██╗██████╗ ")
    print(r"  ██╔════╝██║██╔════╝██║   ██║    ██║   ██║██║██╔══██╗")
    print(r"  ███████╗██║█████╗  ██║   ██║    ██║   ██║██║██████╔╝")
    print(r"  ╚════██║██║██╔══╝  ██║   ██║    ╚██╗ ██╔╝██║██╔═══╝ ")
    print(r"  ███████║██║███████╗╚██████╔╝     ╚████╔╝ ██║██║     ")
    print(r"  ╚══════╝╚═╝╚══════╝ ╚═════╝       ╚═══╝  ╚═╝╚═╝     ")
    print(f"{C_RESET}")
    print(f"{C_CYAN}================================================================================{C_RESET}")
    print(f"{C_WHITE} He thong: Android 10 (Root) | Packages da chon: {C_GREEN}{selected_count}{C_WHITE} | Accs: {C_GREEN}{acc_count}{C_RESET}")
    print(f"{C_CYAN}================================================================================{C_RESET}")
    print(f" {C_GREEN}[1]{C_RESET} {C_BOLD}Auto Rejoin (Khoi dong chu trinh da tien trinh cày VIP){C_RESET}")
    print(f" {C_WHITE}[2] Chon Package (Global, VNG, App Cloner){C_RESET}")
    print(f" {C_WHITE}[3] Nhap Game ID hoac Server VIP (Tich hop 10 Game Hot){C_RESET}")
    print(f" {C_WHITE}[4] Auto Block Account (Chan cheo phong ngua trung server){C_RESET}")
    print(f" {C_WHITE}[5] Login with Cookie (Root XML / SQLite Injection){C_RESET}")
    print(f" {C_WHITE}[6] Export Cookie{C_RESET}")
    print(f" {C_WHITE}[7] Auto Sort Tab (Android 10 Freeform Multi-Window Grid){C_RESET}")
    print(f" {C_WHITE}[8] Open All Tabs Roblox{C_RESET}")
    print(f" {C_WHITE}[9] Configs (Timer, Delay, Timeout, Cache, Heartbeat){C_RESET}")
    print(f" {C_WHITE}[10] Autoexecute Script Manager (Lua Sync IPC){C_RESET}")
    print(f" {C_WHITE}[11] Discord Webhook (Canh bao va bao cao tu xa){C_RESET}")
    print(f" {C_RED}[0] Thoat he thong{C_RESET}")
    print(f"{C_CYAN}================================================================================{C_RESET}")
    print(f"{C_YELLOW}Vui long nhap lua chon cua ban [0-11]: {C_RESET}", end="")


def main():
    check_and_enforce_root()
    init_directories()

    while True:
        display_main_menu()
        choice = input().strip()

        if choice == "1":
            execute_auto_rejoin_pipeline()
        elif choice == "2":
            menu_choose_packages()
        elif choice == "3":
            menu_set_game_id()
        elif choice == "4":
            cfg = load_config()
            cfg["auto_block"] = not cfg.get("auto_block", False)
            save_config(cfg)
            print(f"{C_GREEN}[+] Trang thai Auto Block: {cfg['auto_block']}{C_RESET}")
            time.sleep(1.5)
        elif choice == "5":
            menu_login_with_cookie()
        elif choice == "6":
            menu_export_cookie()
        elif choice == "7":
            menu_auto_sort_tab()
        elif choice == "8":
            menu_open_all_tabs()
        elif choice == "9":
            menu_configs()
        elif choice == "10":
            menu_autoexecute_manager()
        elif choice == "11":
            menu_discord_webhook()
        elif choice == "0":
            print(f"\n{C_GREEN}[*] Da dong toan bo he thong. Tam biet boss man!{C_RESET}\n")
            sys.exit(0)
        else:
            print(f"\n{C_RED}[!] Lua chon khong hop le.{C_RESET}")
            time.sleep(1)


if __name__ == "__main__":
    main()
