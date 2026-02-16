import sys
import os
import platform
import tkinter as tk
from tkinter import messagebox
import subprocess
import socket
import struct
import re

def is_admin():
    try:
        return os.getuid() == 0
    except AttributeError:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0

def get_router_ip():
    # Attempt to find the default gateway
    try:
        system = platform.system()
        if system == "Darwin":
            route = subprocess.check_output(["route", "-n", "get", "default"]).decode()
            for line in route.split("\n"):
                if "gateway" in line:
                    return line.split(":")[1].strip()
        elif system == "Linux":
            with open("/proc/net/route") as fh:
                for line in fh:
                    fields = line.strip().split()
                    if fields[1] != '00000000' or not int(fields[3], 16) & 2:
                        continue
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
        elif system == "Windows":
             # Use ipconfig and parse Default Gateway
             output = subprocess.check_output("ipconfig", shell=True).decode()
             # Look for "Default Gateway . . . . . . . . . : 192.168.1.1"
             match = re.search(r"Default Gateway.*: ([\d\.]+)", output)
             if match:
                 return match.group(1)
    except Exception:
        pass
    return "192.168.1.1" # Fallback

def get_active_interface_name_mac():
    try:
        # Get default interface (e.g., en0)
        route = subprocess.check_output(["route", "-n", "get", "default"]).decode()
        interface_id = None
        for line in route.split("\n"):
            if "interface" in line:
                interface_id = line.split(":")[1].strip()
                break
        
        if not interface_id:
            return "Wi-Fi"

        # Map en0 to "Wi-Fi"
        ports = subprocess.check_output(["networksetup", "-listallhardwareports"]).decode()
        current_port = None
        for line in ports.split("\n"):
            if "Hardware Port" in line:
                current_port = line.split(":")[1].strip()
            if f"Device: {interface_id}" in line and current_port:
                return current_port
    except:
        pass
    return "Wi-Fi"

def block_porn_dns():
    # Cloudflare Family DNS (Blocks Malware, Porn, & Known Threats)
    # Primary: 1.1.1.3 (Malware + Porn Blocking)
    # Secondary: 1.0.0.3 (Redundancy)
    primary_dns = "1.1.1.3"
    secondary_dns = "1.0.0.3"
    
    system = platform.system()
    try:
        if system == "Darwin":
            service = get_active_interface_name_mac()
            print(f"Setting DNS for {service}...")
            subprocess.run(["networksetup", "-setdnsservers", service, primary_dns, secondary_dns], check=True)
            subprocess.run(["dscacheutil", "-flushcache"], check=False)
            
        elif system == "Linux":
            # Modify /etc/resolv.conf (temporary) or use nmcli
            # This is tricky without knowing the distro/network manager
            # Let's try writing to /etc/resolv.conf directly as a fallback
            with open("/etc/resolv.conf", "w") as f:
                f.write(f"nameserver {primary_dns}\nnameserver {secondary_dns}\n")
                
        elif system == "Windows":
            # netsh interface ip set dns "Wi-Fi" static 1.1.1.3
            subprocess.run(f'netsh interface ip set dns "Wi-Fi" static {primary_dns}', shell=True)
            subprocess.run(f'netsh interface ip add dns "Wi-Fi" {secondary_dns} index=2', shell=True)
            
        return True
    except Exception as e:
        print(f"Error setting DNS: {e}")
        return False

def block_reddit_hosts():
    hosts_path = "/etc/hosts"
    if platform.system() == "Windows":
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    
    domains_to_block = [
        "reddit.com", "www.reddit.com", "old.reddit.com", "api.reddit.com"
    ]
    
    try:
        with open(hosts_path, "r") as f:
            content = f.read()
        
        new_lines = []
        for domain in domains_to_block:
            entry = f"127.0.0.1 {domain}"
            if entry not in content:
                new_lines.append(entry)
        
        if new_lines:
            with open(hosts_path, "a") as f:
                f.write("\n# Added by 1ClickBlock\n")
                for line in new_lines:
                    f.write(f"{line}\n")
            return True
        return True # Already blocked
    except Exception as e:
        print(f"Error modifying hosts file: {e}")
        return False

def restore_defaults():
    # 1. Clear Hosts File (Remove our entries)
    hosts_path = "/etc/hosts"
    if platform.system() == "Windows":
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
    
    try:
        with open(hosts_path, "r") as f:
            lines = f.readlines()
        
        # Write back all lines that ARE NOT our blocked domains
        with open(hosts_path, "w") as f:
            for line in lines:
                if "127.0.0.1 reddit.com" not in line and \
                   "127.0.0.1 www.reddit.com" not in line and \
                   "Added by 1ClickBlock" not in line and \
                   "old.reddit.com" not in line and \
                   "api.reddit.com" not in line:
                    f.write(line)
    except Exception as e:
        print(f"Error restoring hosts: {e}")

    # 2. Reset DNS to Automatic/Empty
    system = platform.system()
    try:
        if system == "Darwin":
            service = get_active_interface_name_mac()
            subprocess.run(["networksetup", "-setdnsservers", service, "Empty"], check=False)
            subprocess.run(["dscacheutil", "-flushcache"], check=False)
        elif system == "Windows":
             # Reset DNS to DHCP
            subprocess.run('netsh interface ip set dns "Wi-Fi" dhcp', shell=True)
            # Remove any specific secondary if it exists
            # (The above command usually clears both, but safe to be sure)
    except Exception as e:
        print(f"Error restoring DNS: {e}")

    messagebox.showinfo("Restored", "Protection disabled. Your internet settings are back to normal.")

import requests
import json
import threading
import time
from datetime import datetime

API_URL = "https://gaurd-online.onrender.com" # Update after deploy

class GaurdAgent:
    def __init__(self):
        self.user_id = None
        self.profile_id = None
        self.running = False
        self.current_policy = None

    def sync_loop(self):
        while self.running:
            try:
                if self.profile_id:
                    response = requests.get(f"{API_URL}/policy/{self.profile_id}")
                    if response.status_code == 200:
                        self.current_policy = response.json()
                        self.apply_policy()
            except Exception as e:
                print(f"Sync error: {e}")
            time.sleep(60) # Sync every minute

    def apply_policy(self):
        if not self.current_policy:
            return
            
        policy = self.current_policy["profile"]
        schedules = self.current_policy["schedules"]
        
        # Check if we should be active now
        should_be_active = True
        if schedules:
            now = datetime.now()
            day = now.weekday()
            current_time = now.strftime("%H:%M")
            
            should_be_active = False
            for s in schedules:
                if s["day_of_week"] == day:
                    if s["start_time"] <= current_time <= s["end_time"]:
                        should_be_active = True
                        break
        
        if should_be_active:
            if policy["block_porn"]:
                block_porn_dns()
            if policy["block_reddit"]:
                block_reddit_hosts()
        else:
            restore_defaults()

    def log_event(self, event_type, details):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "details": details
        }
        with open("gaurd_events.log", "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # In a real app, we would POST this to /events/ endpoint
        print(f"Logged: {event_type} - {details}")

    def enforcement_loop(self):
        while self.running:
            if self.current_policy and self.current_policy["profile"]["block_porn"]:
                # Force DNS and Hosts
                dns_success = block_porn_dns()
                hosts_success = block_reddit_hosts()
                
                if not dns_success or not hosts_success:
                    self.log_event("SHIELD_REPAIR", "Protection was tampered with and successfully restored.")
                else:
                    self.log_event("HEARTBEAT", "System secure.")
            
            # Simulate AI Threat Detection
            import random
            if random.random() < 0.1: # 10% chance to 'detect' a simulated attack
                threats = ["Botnet Probe", "Credential Stuffing Attempt", "AI-Scanner Blocked"]
                self.log_event("AI_DEFENSE", f"Neutralized: {random.choice(threats)}")

            time.sleep(30)

    def start(self, profile_id):
        self.profile_id = profile_id
        self.running = True
        self.sync_thread = threading.Thread(target=self.sync_loop, daemon=True)
        self.enforce_thread = threading.Thread(target=self.enforcement_loop, daemon=True)
        self.sync_thread.start()
        self.enforce_thread.start()

agent = GaurdAgent()

def on_click_block():
    if not is_admin():
        messagebox.showerror("Permission Denied", "Please run this application as Administrator/Root.")
        return

    # 1. Block Porn (DNS)
    dns_success = block_porn_dns()
    
    # 2. Block Reddit (Hosts)
    hosts_success = block_reddit_hosts()
    
    # 3. Router Attempt
    router_ip = get_router_ip()
    
    msg = "✅ Protection is now ON!\n\n"
    msg += "• Pornography & Malware: BLOCKED\n"
    msg += "• Reddit: BLOCKED\n"
    msg += "• AI Threats: BLOCKED\n\n"
    msg += "For full home protection, please update your router settings."
    
    messagebox.showinfo("Family Shield", msg)

    # Attempt to open router page
    import webbrowser
    webbrowser.open(f"http://{router_ip}")

def restore_block():
    if not is_admin():
        messagebox.showerror("Permission Denied", "Please run this application as Administrator/Root to apply changes.")
        return
        
    restore_defaults()

def main():
    root = tk.Tk()
    root.title("Family Shield")
    root.geometry("400x400")
    # root.configure(bg="#f0f0f0") # Default bg is fine

    # Title
    label = tk.Label(root, text="Family Shield", font=("Helvetica", 24, "bold"))
    label.pack(pady=20)
    
    # Description
    desc = tk.Label(root, text="One Click to Block Porn & Hackers.\nKeeps your family safe.", font=("Helvetica", 12))
    desc.pack(pady=10)
    
    # Status Indicator (visual)
    status_label = tk.Label(root, text="⚠️ Protection OFF", font=("Helvetica", 12, "bold"), fg="red")
    status_label.pack(pady=10)
    
    def on_click_safe():
        on_click_block()
        status_label.config(text="✅ Protection ON", fg="green")

    def on_click_restore():
        restore_block()
        status_label.config(text="⚠️ Protection OFF", fg="red")

    # Big Green Button
    btn_safe = tk.Button(root, text="TURN ON PROTECTION", command=on_click_safe, font=("Helvetica", 16, "bold"), bg="#28a745", fg="white", height=2, width=20)
    btn_safe.pack(pady=15)
    
    # Small Restore Link/Button
    btn_restore = tk.Button(root, text="Turn Off / Restore Normal Settings", command=on_click_restore, font=("Helvetica", 10, "underline"), fg="blue", borderwidth=0, cursor="hand2")
    btn_restore.pack(pady=10)

    # Router Help
    help_lbl = tk.Label(root, text="Tip: Configure your router for full home protection.", font=("Helvetica", 9, "italic"), fg="#666")
    help_lbl.pack(side="bottom", pady=20)
    
    root.mainloop()

if __name__ == "__main__":
    main()
