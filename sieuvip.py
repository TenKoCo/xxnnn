#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ==============================================================================
# SIEUVIP - ADVANCED ROOT TERMUX ROBLOX AUTOMATION DAEMON
# ==============================================================================

import os
import sys
import time
import json
import re
import shutil
import datetime
import subprocess
import threading
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- SYSTEM PATHS & DIRECTORY STRUCTURE ---
BASE_DIR = "/data/data/com.termux/files/home/SieuVip"
CONFIGS_DIR = os.path.join(BASE_DIR, "configs")
AUTOEXEC_DIR = os.path.join(BASE_DIR, "Autoexecute")
LOG_FILE = os.path.join(BASE_DIR, "crash.logs")
COOKIE_HU_FILE = os.path.join(BASE_DIR, "cookie_hu.txt")
DOWNLOAD_DIR = "/sdcard/Download"
COOKIE_SRC = os.path.join(DOWNLOAD_DIR, "cookie.txt")

SETTINGS_FILE = os.path.join(CONFIGS_DIR, "settings.json")
PACKAGES_FILE = os.path.join(CONFIGS_DIR, "packages.json")
GAMES_FILE = os.path.join(CONFIGS_DIR, "games.json")
SESSIONS_FILE = os.path.join(CONFIGS_DIR, "sessions.json")

# --- ANSI DISPLAY PROTOCOLS ---
CLR = "\033[2J\033[H"
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[1;31m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[1;34m"
MAGENTA = "\033[1;35m"
CYAN = "\033[1;36m"
WHITE = "\033[1;37m"

HOT_GAMES = [
    ("Blox Fruits", "2753915549"),
    ("Steal an Egg", "142823291"),
    ("Pet Simulator 99", "8737899170"),
    ("King Legacy", "4520749081"),
    ("Blade Ball", "13772394625"),
    ("Da Hood", "2788229376"),
    ("Brookhaven RP", "4924922222"),
    ("Murder Mystery 2", "142823291"),
    ("Toilet Tower Defense", "13775256536"),
    ("Anime Defenders", "17013391468"),
]

EXECUTOR_DIRS = [
    "/sdcard/Delta/autoexecute",
    "/sdcard/Fluxus/autoexecute",
    "/sdcard/Arceus/autoexecute",
    "/sdcard/Codex/autoexecute",
    "/sdcard/VegaX/autoexecute",
    "/sdcard/Hydrogen/autoexecute",
]

# --- ROOT SYSTEM EXECUTION ENGINE ---
def run_root(cmd: str, timeout: int = 15) -> Tuple[int, str, str]:
    """Execute low-level commands through su root bridge."""
    try:
        proc = subprocess.Popen(
            ["su", "-c", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        return proc.returncode, stdout.strip(), stderr.strip()
    except subprocess.TimeoutExpired:
        proc.kill()
        return -1, "", "Command Timeout"
    except Exception as e:
        return -1, "", str(e)

def log_error(msg: str):
    """Write critical exceptions to crash log."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")

# --- CONFIGURATION IO DRIVER ---
def load_json(filepath: str, default: Any) -> Any:
    if not os.path.exists(filepath):
        save_json(filepath, default)
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_error(f"JSON Load Failure ({filepath}): {str(e)}")
        return default

def save_json(filepath: str, data: Any):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log_error(f"JSON Save Failure ({filepath}): {str(e)}")

# --- HARDWARE METRICS MONITOR ---
class HardwareMonitor:
    @staticmethod
    def read_cpu_usage() -> float:
        try:
            def get_stats():
                with open("/proc/stat", "r") as f:
                    fields = [float(x) for x in f.readline().strip().split()[1:8]]
                idle = fields[3] + fields[4]
                total = sum(fields)
                return idle, total

            idle1, total1 = get_stats()
            time.sleep(0.1)
            idle2, total2 = get_stats()

            idle_delta = idle2 - idle1
            total_delta = total2 - total1
            if total_delta == 0:
                return 0.0
            return round((1.0 - (idle_delta / total_delta)) * 100.0, 1)
        except Exception:
            return 0.0

    @staticmethod
    def read_ram_usage() -> Tuple[float, int, int]:
        try:
            meminfo = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        meminfo[key] = int(val)
            total = meminfo.get("MemTotal", 1)
            available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
            used = total - available
            pct = round((used / total) * 100.0, 1)
            return pct, used // 1024, total // 1024
        except Exception:
            return 0.0, 0, 0

# --- ROBLOX API CLIENT PIPELINE ---
class RobloxClient:
    def __init__(self):
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36",
            "Accept": "application/json",
        })

    def get_csrf(self, cookie: str) -> Optional[str]:
        headers = {
            "Cookie": f".ROBLOSECURITY={cookie};",
            "Content-Type": "application/json"
        }
        try:
            res = self.session.post("https://auth.roblox.com/v2/login", headers=headers, timeout=10)
            return res.headers.get("x-csrf-token")
        except Exception as e:
            log_error(f"CSRF acquisition failed: {str(e)}")
            return None

    def validate_cookie(self, cookie: str) -> Optional[Dict[str, Any]]:
        headers = {"Cookie": f".ROBLOSECURITY={cookie};"}
        try:
            res = self.session.get("https://users.roblox.com/v1/users/authenticated", headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return {"id": data.get("id"), "name": data.get("name")}
            return None
        except Exception as e:
            log_error(f"Cookie validation error: {str(e)}")
            return None

    def block_user(self, cookie: str, csrf: str, target_user_id: int) -> bool:
        headers = {
            "Cookie": f".ROBLOSECURITY={cookie};",
            "x-csrf-token": csrf,
            "Content-Type": "application/json"
        }
        url = f"https://accountsettings.roblox.com/v1/users/{target_user_id}/block"
        for _ in range(4):
            try:
                res = self.session.post(url, headers=headers, timeout=10)
                if res.status_code == 200:
                    return True
                elif res.status_code == 403:
                    new_csrf = res.headers.get("x-csrf-token")
                    if new_csrf:
                        headers["x-csrf-token"] = new_csrf
                        csrf = new_csrf
                        continue
                elif res.status_code == 429:
                    time.sleep(2.0)
                    continue
                return False
            except Exception:
                time.sleep(1.0)
        return False

    def get_presence(self, cookie: str, csrf: str, user_id: int) -> Optional[Dict[str, Any]]:
        headers = {
            "Cookie": f".ROBLOSECURITY={cookie};",
            "x-csrf-token": csrf,
            "Content-Type": "application/json"
        }
        try:
            res = self.session.post(
                "https://presence.roblox.com/v1/presence/users",
                headers=headers,
                json={"userIds": [user_id]},
                timeout=8
            )
            if res.status_code == 200:
                presences = res.json().get("userPresences", [])
                if presences:
                    return presences[0]
            elif res.status_code == 403:
                new_csrf = res.headers.get("x-csrf-token")
                if new_csrf:
                    headers["x-csrf-token"] = new_csrf
                    res = self.session.post(
                        "https://presence.roblox.com/v1/presence/users",
                        headers=headers,
                        json={"userIds": [user_id]},
                        timeout=8
                    )
                    if res.status_code == 200:
                        presences = res.json().get("userPresences", [])
                        if presences:
                            return presences[0]
            return None
        except Exception as e:
            log_error(f"Presence inquiry failed: {str(e)}")
            return None

# ==============================================================================
# SUB-SYSTEM MODULE IMPLEMENTATIONS
# ==============================================================================

# --- MODULE 5 & STORAGE INJECTION ENGINE ---
def sanitize_cookie(raw: str) -> str:
    match = re.search(r'_\|WARNING:-DO-NOT-SHARE-THIS\.--Sharing-this-will-allow-someone-to-log-into-your-account-and-commit-fraud\._[A-Za-z0-9]+', raw)
    if match:
        return match.group(0)
    raw = raw.strip()
    if raw.startswith(".ROBLOSECURITY="):
        raw = raw.replace(".ROBLOSECURITY=", "")
    return raw.strip(";").strip()

def inject_session_to_package(package_name: str, cookie: str):
    """Inject validated authentication cookie directly into app Shared Preferences."""
    shared_prefs_dir = f"/data/data/{package_name}/shared_prefs"
    xml_file = f"{shared_prefs_dir}/{package_name}_preferences.xml"
    
    # Retrieve UID/GID of target package
    code, uid_str, _ = run_root(f"stat -c '%u:%g' /data/data/{package_name}")
    if code != 0 or not uid_str:
        uid_str = "1000:1000"

    xml_content = f"""<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
    <string name="ROBLOSECURITY">{cookie}</string>
    <string name="Cookie">{cookie}</string>
    <boolean name="HasLoggedIn" value="true" />
</map>
"""
    run_root(f"mkdir -p {shared_prefs_dir}")
    run_root(f"cat << 'EOF' > {xml_file}\n{xml_content}\nEOF")
    run_root(f"chmod 660 {xml_file}")
    run_root(f"chown -R {uid_str} {shared_prefs_dir}")

def module_cookie_validator():
    client = RobloxClient()
    if not os.path.exists(COOKIE_SRC):
        print(f"{RED}[-] Source cookie file missing: {COOKIE_SRC}{RESET}")
        time.sleep(2)
        return

    with open(COOKIE_SRC, "r", encoding="utf-8") as f:
        lines = f.readlines()

    sessions = load_json(SESSIONS_FILE, {})
    valid_count = 0
    invalid_count = 0

    print(f"{CYAN}[*] Validating {len(lines)} cookies against Roblox Gateway...{RESET}")
    for raw in lines:
        cleaned = sanitize_cookie(raw)
        if not cleaned:
            continue

        account_info = client.validate_cookie(cleaned)
        if account_info:
            uid = str(account_info["id"])
            sessions[uid] = {
                "userId": account_info["id"],
                "username": account_info["name"],
                "cookie": cleaned,
                "validated_at": datetime.datetime.now().isoformat()
            }
            valid_count += 1
            print(f"  {GREEN}[VALID]{RESET} {account_info['name']} (ID: {uid})")
        else:
            invalid_count += 1
            ts = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            with open(COOKIE_HU_FILE, "a", encoding="utf-8") as f_hu:
                f_hu.write(f"[{ts}] {cleaned}\n")
            print(f"  {RED}[EXPIRED/INVALID]{RESET} Quarantined to cookie_hu.txt")

    save_json(SESSIONS_FILE, sessions)
    print(f"\n{BOLD}Results: {GREEN}{valid_count} Active{RESET} | {RED}{invalid_count} Quarantined{RESET}")
    input(f"\n{DIM}Press Enter to return...{RESET}")

# --- MODULE 2: PACKAGE SCANNER & SELECTOR ---
def module_package_selector():
    while True:
        packages_pool = load_json(PACKAGES_FILE, [])
        code, out, _ = run_root("pm list packages")
        all_pkgs = [line.replace("package:", "").strip() for line in out.splitlines() if line.strip()]

        candidates = [
            pkg for pkg in all_pkgs
            if any(k in pkg.lower() for k in ["roblox", "clone", "vphone", "dual", "multi", "sand"])
        ]

        print(CLR + f"{CYAN}{BOLD}=== MODULE 2: PACKAGE SELECTOR ==={RESET}")
        print(f"{WHITE}Detected matching packages in system:{RESET}\n")

        for idx, pkg in enumerate(candidates, 1):
            status = f"{GREEN}[ACTIVE]{RESET}" if pkg in packages_pool else f"{RED}[OFF]{RESET}"
            print(f"  {idx:2d}. {status} {pkg}")

        print(f"\n  {YELLOW}[A]{RESET} Auto-select all matched packages")
        print(f"  {YELLOW}[C]{RESET} Clear selection pool")
        print(f"  {YELLOW}[0]{RESET} Save and Return")

        choice = input(f"\n{CYAN}Selection > {RESET}").strip().upper()
        if choice == "0":
            break
        elif choice == "A":
            packages_pool = list(set(packages_pool + candidates))
            save_json(PACKAGES_FILE, packages_pool)
        elif choice == "C":
            packages_pool = []
            save_json(PACKAGES_FILE, packages_pool)
        elif choice.isdigit():
            val = int(choice)
            if 1 <= val <= len(candidates):
                target = candidates[val - 1]
                if target in packages_pool:
                    packages_pool.remove(target)
                else:
                    packages_pool.append(target)
                save_json(PACKAGES_FILE, packages_pool)

# --- MODULE 3: GAME ID & VIP SERVER MANAGER ---
def module_games_manager():
    games_cfg = load_json(GAMES_FILE, {
        "mode": "global",
        "global_place_id": "2753915549",
        "global_job_id": "",
        "global_link_code": "",
        "package_specific": {}
    })

    while True:
        print(CLR + f"{CYAN}{BOLD}=== MODULE 3: GAME ID & VIP SERVER MANAGER ==={RESET}")
        print(f"Current Mode: {YELLOW}{games_cfg.get('mode', 'global').upper()}{RESET}")
        print(f"Global Place ID: {GREEN}{games_cfg.get('global_place_id')}{RESET}")
        print(f"Global Job ID  : {DIM}{games_cfg.get('global_job_id') or 'N/A'}{RESET}")
        print(f"Global VIP Code: {DIM}{games_cfg.get('global_link_code') or 'N/A'}{RESET}")
        print("\n1. Configure Global Target (All Packages)")
        print("2. Configure Package-Specific Target")
        print("3. Quick Select Hot Games (Top 10)")
        print("0. Return")

        ch = input(f"\n{CYAN}Choice > {RESET}").strip()
        if ch == "0":
            break
        elif ch == "1":
            games_cfg["mode"] = "global"
            games_cfg["global_place_id"] = input("Enter Place ID: ").strip()
            games_cfg["global_job_id"] = input("Enter Job ID (Enter to skip): ").strip()
            vip_link = input("Enter Private Server Link / LinkCode (Enter to skip): ").strip()
            if "privateServerLinkCode=" in vip_link:
                games_cfg["global_link_code"] = vip_link.split("privateServerLinkCode=")[-1].split("&")[0]
            else:
                games_cfg["global_link_code"] = vip_link
            save_json(GAMES_FILE, games_cfg)
        elif ch == "2":
            games_cfg["mode"] = "package"
            packages_pool = load_json(PACKAGES_FILE, [])
            for pkg in packages_pool:
                print(f"\n{WHITE}Configuring package:{RESET} {CYAN}{pkg}{RESET}")
                pid = input(f"Place ID for {pkg} (Leave empty to skip): ").strip()
                if pid:
                    jid = input("Job ID: ").strip()
                    vlink = input("VIP Code / Link: ").strip()
                    if "privateServerLinkCode=" in vlink:
                        vlink = vlink.split("privateServerLinkCode=")[-1].split("&")[0]
                    games_cfg.setdefault("package_specific", {})[pkg] = {
                        "place_id": pid,
                        "job_id": jid,
                        "link_code": vlink
                    }
            save_json(GAMES_FILE, games_cfg)
        elif ch == "3":
            print(CLR + f"{CYAN}{BOLD}=== HOT ROBLOX EXPERIENCES ==={RESET}")
            for idx, (g_name, g_id) in enumerate(HOT_GAMES, 1):
                print(f"  {idx:2d}. {WHITE}{g_name:<22}{RESET} ID: {GREEN}{g_id}{RESET}")
            g_idx = input(f"\nSelect game (1-{len(HOT_GAMES)}): ").strip()
            if g_idx.isdigit() and 1 <= int(g_idx) <= len(HOT_GAMES):
                sel_name, sel_id = HOT_GAMES[int(g_idx) - 1]
                games_cfg["global_place_id"] = sel_id
                games_cfg["global_job_id"] = ""
                games_cfg["global_link_code"] = ""
                save_json(GAMES_FILE, games_cfg)
                print(f"{GREEN}[+] Applied {sel_name} ({sel_id}) Globally.{RESET}")
                time.sleep(1.5)

# --- MODULE 4: MUTUAL ANTI-COLLISION ENGINE ---
def module_mutual_anti_collision():
    print(CLR + f"{CYAN}{BOLD}=== MODULE 4: MUTUAL ANTI-COLLISION (AUTO BLOCK) ==={RESET}")
    sessions = load_json(SESSIONS_FILE, {})
    if len(sessions) < 2:
        print(f"{RED}[-] At least 2 active accounts required to execute mutual blocking.{RESET}")
        time.sleep(2)
        return

    client = RobloxClient()
    account_list = list(sessions.values())
    total_pairs = len(account_list) * (len(account_list) - 1)
    executed = 0

    print(f"Accounts Pool: {GREEN}{len(account_list)}{RESET} | Total Block Operations: {YELLOW}{total_pairs}{RESET}\n")

    for actor in account_list:
        actor_id = actor["userId"]
        actor_name = actor["username"]
        cookie = actor["cookie"]
        csrf = client.get_csrf(cookie)

        if not csrf:
            print(f"{RED}[-] CSRF token handshake rejected for {actor_name}. Skipping.{RESET}")
            continue

        for target in account_list:
            target_id = target["userId"]
            target_name = target["username"]
            if actor_id == target_id:
                continue

            success = client.block_user(cookie, csrf, target_id)
            status = f"{GREEN}BLOCKED{RESET}" if success else f"{RED}FAILED{RESET}"
            print(f"  [{status}] {actor_name} -> {target_name} ({target_id})")
            executed += 1
            time.sleep(0.3)

    print(f"\n{GREEN}[+] Mutual blocking routine finished. Operation count: {executed}{RESET}")
    input(f"\n{DIM}Press Enter to return...{RESET}")

# --- MODULE 6: EXPORT COOKIES ---
def module_export_cookies():
    print(CLR + f"{CYAN}{BOLD}=== MODULE 6: EXPORT COOKIE UTILITY ==={RESET}")
    sessions = load_json(SESSIONS_FILE, {})
    if not sessions:
        print(f"{RED}[-] No active sessions registered.{RESET}")
        time.sleep(2)
        return

    today = datetime.datetime.now().strftime("%d%m%Y")
    export_path = f"/sdcard/Download/cookie_export_{today}.txt"

    print("1. Export all active cookies (Plain text format)")
    print("2. Export all active cookies (Username:Cookie format)")
    print("0. Return")

    ch = input(f"\n{CYAN}Choice > {RESET}").strip()
    if ch in ["1", "2"]:
        with open(export_path, "w", encoding="utf-8") as f:
            for s in sessions.values():
                if ch == "1":
                    f.write(f"{s['cookie']}\n")
                else:
                    f.write(f"{s['username']}:{s['cookie']}\n")
        print(f"\n{GREEN}[+] Export complete -> {export_path}{RESET}")
        time.sleep(2)

# --- MODULE 7: MULTI-WINDOW GRID TILER ---
def module_auto_sort_tabs():
    print(CLR + f"{CYAN}{BOLD}=== MODULE 7: MULTI-WINDOW GRID TILER ==={RESET}")
    packages = load_json(PACKAGES_FILE, [])
    if not packages:
        print(f"{RED}[-] No target packages enabled.{RESET}")
        time.sleep(2)
        return

    code, res_str, _ = run_root("wm size")
    m = re.search(r'Physical size:\s*(\d+)x(\d+)', res_str)
    if not m:
        m = re.search(r'(\d+)x(\d+)', res_str)
    
    screen_w = int(m.group(1)) if m else 1080
    screen_h = int(m.group(2)) if m else 2400

    print(f"Display Dimensions: {GREEN}{screen_w}x{screen_h}{RESET}")
    print("1. Tile Grid Evenly (Full Display Allocation)")
    print("2. Ultra-Compact Micro Grid (Minimum Dimension)")
    print("0. Return")

    ch = input(f"\n{CYAN}Choice > {RESET}").strip()
    if ch == "1":
        total = len(packages)
        cols = 2 if total >= 2 else 1
        rows = (total + cols - 1) // cols
        tile_w = screen_w // cols
        tile_h = screen_h // rows

        for i, pkg in enumerate(packages):
            col = i % cols
            row = i // cols
            left = col * tile_w
            top = row * tile_h
            right = left + tile_w
            bottom = top + tile_h
            cmd = f"am start -n {pkg}/com.roblox.client.ActivityProtocolLaunch --windowingMode 5 --bounds {left},{top},{right},{bottom}"
            run_root(cmd)
            time.sleep(0.3)
        print(f"{GREEN}[+] Full-screen grid tiled successfully.{RESET}")
        time.sleep(1.5)

    elif ch == "2":
        tile_w, tile_h = 360, 280
        for i, pkg in enumerate(packages):
            left = (i % 2) * tile_w
            top = (i // 2) * tile_h
            right = left + tile_w
            bottom = top + tile_h
            cmd = f"am start -n {pkg}/com.roblox.client.ActivityProtocolLaunch --windowingMode 5 --bounds {left},{top},{right},{bottom}"
            run_root(cmd)
            time.sleep(0.3)
        print(f"{GREEN}[+] Micro-grid arrangement established.{RESET}")
        time.sleep(1.5)

# --- MODULE 10: AUTOEXECUTE SYNCHRONIZER ---
def sync_autoexecute():
    """Propagate custom Luau scripts into all mobile executor workspace trees."""
    if not os.path.exists(AUTOEXEC_DIR):
        os.makedirs(AUTOEXEC_DIR, exist_ok=True)
        return

    scripts = [f for f in os.listdir(AUTOEXEC_DIR) if f.endswith(".lua") or f.endswith(".luau")]
    if not scripts:
        return

    for target_dir in EXECUTOR_DIRS:
        if os.path.exists(os.path.dirname(target_dir)):
            os.makedirs(target_dir, exist_ok=True)
            for sc in scripts:
                src = os.path.join(AUTOEXEC_DIR, sc)
                dst = os.path.join(target_dir, sc)
                shutil.copyfile(src, dst)
                run_root(f"chmod 666 {dst}")

# --- MODULE 8: INSTANCE DISPATCHER ---
def launch_roblox_package(pkg: str, settings: Dict[str, Any], games_cfg: Dict[str, Any]):
    sync_autoexecute()
    if settings.get("clear_cache", False):
        run_root(f"rm -rf /data/data/{pkg}/cache/*")
        run_root(f"rm -rf /data/data/{pkg}/code_cache/*")

    if games_cfg.get("mode") == "package":
        p_data = games_cfg.get("package_specific", {}).get(pkg, {})
        place_id = p_data.get("place_id", games_cfg.get("global_place_id", "2753915549"))
        job_id = p_data.get("job_id", "")
        link_code = p_data.get("link_code", "")
    else:
        place_id = games_cfg.get("global_place_id", "2753915549")
        job_id = games_cfg.get("global_job_id", "")
        link_code = games_cfg.get("global_link_code", "")

    uri = f"roblox://experiences/start?placeId={place_id}"
    if link_code:
        uri += f"&linkCode={link_code}"
    elif job_id:
        uri += f"&gameInstanceId={job_id}"

    cmd = f'am start -n {pkg}/com.roblox.client.ActivityProtocolLaunch -a android.intent.action.VIEW -d "{uri}"'
    run_root(cmd)

# --- MODULE 9: CONFIGURATION SUBSYSTEM MENU ---
def module_config_menu():
    settings = load_json(SETTINGS_FILE, {
        "check_method": "Online",
        "queue_next": True,
        "check_timeout": 60,
        "delay_open": 5,
        "clear_cache": False,
        "time_to_stop": 30
    })

    while True:
        print(CLR + f"{CYAN}{BOLD}=== MODULE 9: SYSTEM CONFIGURATIONS ==={RESET}")
        print(f"  1. Check Method        : {GREEN}{settings['check_method']}{RESET}")
        print(f"  2. Queue Next Instance : {GREEN}{settings['queue_next']}{RESET}")
        print(f"  3. Check Timeout       : {GREEN}{settings['check_timeout']}s{RESET}")
        print(f"  4. Delay Open Interval : {GREEN}{settings['delay_open']}s{RESET}")
        print(f"  5. Flush App Cache     : {GREEN}{settings['clear_cache']}{RESET}")
        print(f"  6. Periodic Master Stop: {GREEN}{settings['time_to_stop']} min{RESET}")
        print(f"  0. Save and Exit")

        ch = input(f"\n{CYAN}Select option to modify > {RESET}").strip()
        if ch == "0":
            break
        elif ch == "1":
            settings["check_method"] = "Executor" if settings["check_method"] == "Online" else "Online"
        elif ch == "2":
            settings["queue_next"] = not settings["queue_next"]
        elif ch == "3":
            val = input("Enter timeout in seconds: ").strip()
            if val.isdigit(): settings["check_timeout"] = int(val)
        elif ch == "4":
            val = input("Enter delay in seconds: ").strip()
            if val.isdigit(): settings["delay_open"] = int(val)
        elif ch == "5":
            settings["clear_cache"] = not settings["clear_cache"]
        elif ch == "6":
            val = input("Enter cycle stop time (minutes): ").strip()
            if val.isdigit(): settings["time_to_stop"] = int(val)

        save_json(SETTINGS_FILE, settings)

# --- MODULE 1: AUTO REJOIN DAEMON & LIVE TUI DASHBOARD ---
def module_auto_rejoin_daemon():
    settings = load_json(SETTINGS_FILE, {
        "check_method": "Online",
        "queue_next": True,
        "check_timeout": 60,
        "delay_open": 5,
        "clear_cache": False,
        "time_to_stop": 30
    })
    packages = load_json(PACKAGES_FILE, [])
    sessions = load_json(SESSIONS_FILE, {})
    games_cfg = load_json(GAMES_FILE, {})

    if not packages:
        print(f"{RED}[-] Active package pool is empty. Configure Module 2 first.{RESET}")
        time.sleep(2)
        return

    # User input for cycle limit
    print(CLR + f"{CYAN}{BOLD}=== MODULE 1: REJOIN DAEMON SCHEDULER ==={RESET}")
    print(f"Saved master cycle timeout: {YELLOW}{settings.get('time_to_stop', 30)} min{RESET}")
    val_in = input("Time to stop roblox: xx (phút) [Enter to skip]: ").strip()
    if val_in.isdigit():
        settings["time_to_stop"] = int(val_in)
        save_json(SETTINGS_FILE, settings)

    cycle_limit_sec = settings["time_to_stop"] * 60
    cycle_start = time.time()

    # Map package to account credentials
    account_keys = list(sessions.keys())
    package_map = {}
    for i, pkg in enumerate(packages):
        acc = sessions[account_keys[i % len(account_keys)]] if account_keys else None
        package_map[pkg] = {
            "account": acc,
            "status": "Starting",
            "launch_ts": 0.0,
            "runtime_ts": 0.0,
            "online": False
        }
        if acc:
            inject_session_to_package(pkg, acc["cookie"])

    client = RobloxClient()

    # Instance launcher queue controller
    for pkg in packages:
        package_map[pkg]["status"] = "Injecting"
        package_map[pkg]["launch_ts"] = time.time()
        launch_roblox_package(pkg, settings, games_cfg)

        if settings.get("queue_next", True):
            # Block until validated or timed out
            tout = settings.get("check_timeout", 60)
            t_start = time.time()
            while time.time() - t_start < tout:
                time.sleep(2.0)
                acc = package_map[pkg]["account"]
                if acc:
                    csrf = client.get_csrf(acc["cookie"])
                    pres = client.get_presence(acc["cookie"], csrf, acc["userId"])
                    if pres and pres.get("userPresenceType") == 2:
                        package_map[pkg]["status"] = "In-Game (Stable)"
                        package_map[pkg]["runtime_ts"] = time.time()
                        break
        time.sleep(settings.get("delay_open", 5))

    # Main Monitor Engine Loop
    while True:
        elapsed = time.time() - cycle_start
        remaining = max(0, cycle_limit_sec - elapsed)
        if remaining == 0:
            # Trigger cyclic reset
            for pkg in packages:
                run_root(f"am force-stop {pkg}")
            break

        cpu_usage = HardwareMonitor.read_cpu_usage()
        ram_pct, ram_used, ram_total = HardwareMonitor.read_ram_usage()

        # Update and poll presence status
        for pkg, data in package_map.items():
            acc = data["account"]
            if not acc:
                data["status"] = "Unauthenticated"
                continue

            csrf = client.get_csrf(acc["cookie"])
            pres = client.get_presence(acc["cookie"], csrf, acc["userId"])
            if pres and pres.get("userPresenceType") == 2:
                data["status"] = "In-Game (Stable)"
                if data["runtime_ts"] == 0.0:
                    data["runtime_ts"] = time.time()
            else:
                # Check for crash or launch timeout
                if time.time() - data["launch_ts"] > settings.get("check_timeout", 60):
                    data["status"] = "Timeout/Rejoining"
                    run_root(f"am force-stop {pkg}")
                    time.sleep(1.0)
                    data["launch_ts"] = time.time()
                    launch_roblox_package(pkg, settings, games_cfg)

        # ANSI Render Output
        sys.stdout.write("\033[H")
        sys.stdout.write(f"{CYAN}{BOLD}==================== SIEUVIP TUI DAEMON MONITOR ===================={RESET}\n")
        sys.stdout.write(f" CPU Usage: {GREEN}{cpu_usage}%{RESET} | RAM: {GREEN}{ram_pct}%{RESET} ({ram_used}MB/{ram_total}MB) | Reset In: {YELLOW}{int(remaining)}s{RESET}\n")
        sys.stdout.write(f" Check Mode: {WHITE}{settings['check_method']}{RESET} | Queue Mode: {WHITE}{settings['queue_next']}{RESET}\n")
        sys.stdout.write("--------------------------------------------------------------------\n")
        sys.stdout.write(f"{BOLD}{'Package Name':<28} | {'Username':<14} | {'Status':<18} | {'Uptime'}{RESET}\n")
        sys.stdout.write("--------------------------------------------------------------------\n")

        for pkg, data in package_map.items():
            u_name = data["account"]["username"] if data["account"] else "None"
            st_color = GREEN if "Stable" in data["status"] else (YELLOW if "Injecting" in data["status"] else RED)
            uptime_str = f"{int(time.time() - data['runtime_ts'])}s" if data["runtime_ts"] > 0 else "0s"
            sys.stdout.write(f" {pkg:<27} | {u_name:<14} | {st_color}{data['status']:<18}{RESET} | {uptime_str}\n")

        sys.stdout.write("--------------------------------------------------------------------\n")
        sys.stdout.write(f"{DIM}[Ctrl+C to abort daemon and halt monitoring]{RESET}\n")
        sys.stdout.flush()
        time.sleep(2.0)

# --- MAIN TUI CONTROL CENTER ---
def main_menu():
    if os.geteuid() != 0:
        run_root("echo 1")  # Prime root context

    while True:
        print(CLR + f"{CYAN}{BOLD}===================================================={RESET}")
        print(f"{GREEN}{BOLD}      SIEUVIP: PRODUCTION ROOT TERMUX DAEMON         {RESET}")
        print(f"{CYAN}{BOLD}===================================================={RESET}")
        print(f"  {YELLOW}1.{RESET} Auto Rejoin Daemon & Live TUI Dashboard")
        print(f"  {YELLOW}2.{RESET} Package Selector Engine")
        print(f"  {YELLOW}3.{RESET} Game ID & VIP Server Manager")
        print(f"  {YELLOW}4.{RESET} Mutual Anti-Collision (Auto Block Pool)")
        print(f"  {YELLOW}5.{RESET} Cookie Login & Gateway Validator")
        print(f"  {YELLOW}6.{RESET} Export Authenticated Cookies")
        print(f"  {YELLOW}7.{RESET} Multi-Window Grid Tiler (Freeform / WM)")
        print(f"  {YELLOW}8.{RESET} Direct Open All Roblox Instances")
        print(f"  {YELLOW}9.{RESET} System Configurations Subsystem")
        print(f"  {YELLOW}10.{RESET} Autoexecute Synchronization Dispatcher")
        print(f"  {RED}0. Exit Daemon{RESET}")
        print(f"{CYAN}===================================================={RESET}")

        opt = input(f"{CYAN}Enter selection [0-10] > {RESET}").strip()
        if opt == "0":
            sys.exit(0)
        elif opt == "1": module_auto_rejoin_daemon()
        elif opt == "2": module_package_selector()
        elif opt == "3": module_games_manager()
        elif opt == "4": module_mutual_anti_collision()
        elif opt == "5": module_cookie_validator()
        elif opt == "6": module_export_cookies()
        elif opt == "7": module_auto_sort_tabs()
        elif opt == "8":
            s = load_json(SETTINGS_FILE, {})
            g = load_json(GAMES_FILE, {})
            pkgs = load_json(PACKAGES_FILE, [])
            for p in pkgs:
                launch_roblox_package(p, s, g)
                time.sleep(s.get("delay_open", 5))
        elif opt == "9": module_config_menu()
        elif opt == "10":
            sync_autoexecute()
            print(f"{GREEN}[+] Synchronized Autoexecute scripts to all executor workspaces.{RESET}")
            time.sleep(1.5)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Daemon aborted by operator.{RESET}")
        sys.exit(0)
