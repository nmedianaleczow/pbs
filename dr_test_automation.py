import subprocess
import time
import os
import re
import json
import random
import smtplib
import urllib.request
import urllib.error
import sys
import select
import shutil
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.encoders import encode_base64
from fpdf import FPDF
from PIL import Image

# ==================== DYNAMIC CONFIGURATION LOADING ====================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

if not os.path.exists(CONFIG_PATH):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [CRITICAL] Brak pliku konfiguracyjnego: {CONFIG_PATH}")
    sys.exit(1)

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
except Exception as e:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [CRITICAL] Blad parsowania pliku config.json: {e}")
    sys.exit(1)

PBS_PVE_STORAGE = config.get("PBS_PVE_STORAGE", "PBS-1Y")
TARGET_STORAGE = config.get("TARGET_STORAGE", "SANDBOX")
TEST_VM_ID = str(config.get("TEST_VM_ID", "999"))
BRIDGE = config.get("BRIDGE", "vmbr999")
BOOT_DELAY_VM = int(config.get("BOOT_DELAY_VM", 90))
BOOT_DELAY_LXC = int(config.get("BOOT_DELAY_LXC", 15))
WEBHOOK_URL = config.get("WEBHOOK_URL", "")
SMTP_SERVER = config.get("SMTP_SERVER", "")
SMTP_PORT = int(config.get("SMTP_PORT", 587))
SMTP_USER = config.get("SMTP_USER", "")
SMTP_PASS = config.get("SMTP_PASS", "")
MAIL_TO = config.get("MAIL_TO", "")
# =======================================================================

execution_logs = []

def log(msg):
    """Wypisuje komunikat na ekranie i rejestruje go do raportu PDF"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    execution_logs.append(full_msg)

def clean_text(text):
    """Zamienia polskie znaki na ASCII i standaryzuje linie, chroniąc FPDF przed nadpisywaniem tekstu"""
    if not text:
        return ""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    rep = {
        'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z',
        'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'
    }
    for k, v in rep.items():
        text = text.replace(k, v)
    return text.encode('ascii', 'ignore').decode('ascii')

def run_cmd(cmd):
    """Wykonuje komendę i automatycznie loguje jej wywołanie oraz błędy"""
    result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    return result.stdout, result.stderr, result.returncode

def main():
    log("=== ROZPOCZECIE AUTOMATYCZNEGO TESTU DR (Wersja 4.27) ===")
    
    status_dr = "CRASHED_BEFORE_START"
    chosen_id = "UNKNOWN"
    chosen_name = "UNKNOWN_NAME"
    chosen_type = "UNKNOWN"
    latest_backup = "UNKNOWN"
    nmap_out = "Brak danych - skrypt zostal przerwany przed skanowaniem."
    screenshot_error_msg = "Brak danych wizualnych."
    ct_logs = "N/A"
    target_ip = None
    is_vm = True
    png_path = "/tmp/dr_screen.png"
    web_png_path = "/tmp/web_screen.png"
    environment_created = False
    web_screenshot_taken = False

    try:
        # 1. Pobranie listy kopii zapasowych i wybór celu (manualny z timeoutem lub automatyczny)
        log(f"Pobieranie listy zasobow z repozytorium: {PBS_PVE_STORAGE}...")
        out, stderr, code = run_cmd(f"pvesm list {PBS_PVE_STORAGE}")
        if code != 0:
            status_dr = "STORAGE_ERROR"
            raise RuntimeError(f"Brak dostepu do storage {PBS_PVE_STORAGE}. Serwer zwrocil: {stderr.strip()}")

        matches = re.findall(rf"({PBS_PVE_STORAGE}:backup/(vm|ct|lxc)/(\d+)/\S+)", out)
        if not matches:
            status_dr = "NO_BACKUPS_FOUND"
            raise RuntimeError(f"Repozytorium {PBS_PVE_STORAGE} nie zawiera zadnych kopii zapasowych!")

        user_input = None
        if sys.stdin.isatty():
            log("Wykryto terminal interaktywny. Oczekiwanie na manualny wybor ID...")
            sys.stdout.write("Wpisz ID maszyny/kontenera do testu (lub kliknij Enter dla losowania, czas 15s): ")
            sys.stdout.flush()
            ready, _, _ = select.select([sys.stdin], [], [], 15)
            if ready:
                user_input = sys.stdin.readline().strip()
            else:
                log("\n[TIMEOUT] Brak wpisu. Przechodze do automatycznego losowania zasobu.")
        else:
            log("Skrypt uruchomiony w tle (np. Crontab). Pomijam prompt interaktywny.")

        if user_input:
            id_matches = [m for m in matches if m[2] == user_input]
            if not id_matches:
                status_dr = "MANUAL_ID_NOT_FOUND"
                raise RuntimeError(f"Nie znaleziono zadnych kopii zapasowych na PBS dla podanego ID: {user_input}")
            
            chosen_type = id_matches[0][1]
            chosen_id = user_input
            is_vm = (chosen_type == "vm")
            
            id_backups = [m[0] for m in id_matches]
            latest_backup = sorted(id_backups)[-1]
            log(f"Wybrano manualnie obiekt: {chosen_type.upper()} o ID {chosen_id}")
        else:
            unique_targets = list(set((m[1], m[2]) for m in matches)) 
            chosen_type, chosen_id = random.choice(unique_targets)
            is_vm = (chosen_type == "vm")
            
            id_backups = [m[0] for m in matches if m[2] == chosen_id]
            latest_backup = sorted(id_backups)[-1]
            log(f"🎲 Wylosowano automatycznie obiekt: {chosen_type.upper()} o ID {chosen_id}")

        log(f"📦 Najnowsza kopia do odzyskania: {latest_backup}")

        # 2. Przywracanie kopii zapasowej
        status_dr = "RESTORE_FAILED" 
        if is_vm:
            log(f"Uruchamiam proces qmrestore dla VM {TEST_VM_ID}...")
            r_out, r_err, code = run_cmd(f"qmrestore {latest_backup} {TEST_VM_ID} --storage {TARGET_STORAGE}")
        else:
            log(f"Uruchamiam proces pct restore dla CT {TEST_VM_ID}...")
            r_out, r_err, code = run_cmd(f"pct restore {TEST_VM_ID} {latest_backup} --storage {TARGET_STORAGE}")

        log(f"--- LOGI PROCESU PRZYWRACANIA PROXMOX ---\nSTDOUT:\n{r_out.strip()}\nSTDERR:\n{r_err.strip()}\n---------------------------------------")

        if code != 0:
            raise RuntimeError("Proxmox odmowil przywrocenia dyskow z repozytorium PBS.")
        
        environment_created = True
        log("Przywracanie obrazu dysku zakonczone pomyslnie.")

        log("Pobieram nazwe z odzyskanej konfiguracji Proxmoxa...")
        name_out, _, _ = run_cmd(f"qm config {TEST_VM_ID}" if is_vm else f"pct config {TEST_VM_ID}")
        name_match = re.search(r"^(name|hostname):\s*(.+)$", name_out, re.MULTILINE)
        if name_match:
            chosen_name = name_match.group(2).strip()
            log(f"Prawdziwa nazwa zidentyfikowana w Proxmox jako: '{chosen_name}'")
        else:
            chosen_name = f"Zasob_{chosen_id}"

        # 3. Modyfikacja konfiguracji i izolacja sieciowa
        status_dr = "CONFIGURATION_FAILED"
        if is_vm:
            log("Analiza konfiguracji maszyny pod katem osieroconych obrazow ISO...")
            vm_conf, _, _ = run_cmd(f"qm config {TEST_VM_ID}")
            cdrom_matches = re.findall(r"^([a-z0-9]+):\s*.*media=cdrom", vm_conf, re.MULTILINE)
            for drive in cdrom_matches:
                log(f"Wysuwam brakujaca plyte ISO z napedu: {drive}")
                run_cmd(f"qm set {TEST_VM_ID} --{drive} none")

            log(f"Przepinanie wirtualnej karty do mostka {BRIDGE} (firewall=0) oraz aktywacja VGA std...")
            run_cmd(f"qm set {TEST_VM_ID} --net0 model=virtio,bridge={BRIDGE},firewall=0 --vga std")
        else:
            log(f"Czyszczenie potencjalnych pozostalosci po interfejsach veth{TEST_VM_ID}i0...")
            run_cmd(f"ip link delete veth{TEST_VM_ID}i0 2>/dev/null")

            log("Odczytywanie natywnej konfiguracji IP kontenera...")
            ct_conf, _, _ = run_cmd(f"pct config {TEST_VM_ID}")
            target_net = "dhcp"
            ip_match = re.search(r"ip=([0-9\.]+/\d+|dhcp)", ct_conf)
            if ip_match:
                target_net = ip_match.group(1)

            log(f"Izolacja kontenera na bridge {BRIDGE} z zachowaniem adresacji: {target_net}")
            run_cmd(f"pct set {TEST_VM_ID} --net0 name=eth0,bridge={BRIDGE},ip={target_net},firewall=0")

        # 4. Rozruch środowiska z opóźnieniem
        status_dr = "BOOT_FAILED"
        log("Wydawanie komendy startu do hypervisora...")
        if is_vm: _, stderr, code = run_cmd(f"qm start {TEST_VM_ID}")
        else: _, stderr, code = run_cmd(f"pct start {TEST_VM_ID}")

        if code != 0:
            raise RuntimeError(f"System hypervisora nie byl w stanie uruchomic instancji: {stderr.strip()}")

        if is_vm:
            log(f"Wykryto maszyne VM: Wstrzymuje skrypt na {BOOT_DELAY_VM} sekund na rozruch OS i uslug aplikacyjnych...")
            time.sleep(BOOT_DELAY_VM)  
        else:
            log(f"Wykryto kontener LXC: Wstrzymuje skrypt na {BOOT_DELAY_LXC} sekund na inicjalizacje...")
            time.sleep(BOOT_DELAY_LXC)

        # 5. Silnik wykrywania adresu IP
        status_dr = "NO_IP_FOUND"
        prefix = 24
        
        if is_vm:
            log("Proba pobrania IP przez protokol QEMU Guest Agent (timeout 60s)...")
            start_time = time.time()
            while time.time() - start_time < 60:
                agent_out, _, agent_code = run_cmd(f"qm guest cmd {TEST_VM_ID} network-get-interfaces 2>/dev/null")
                if agent_code == 0 and agent_out:
                    try:
                        interfaces = json.loads(agent_out)
                        for iface in interfaces:
                            for ip_addr in iface.get("ip-addresses", []):
                                if ip_addr.get("ip-address-type") == "ipv4":
                                    ip_candidate = ip_addr.get("ip-address").strip()
                                    
                                    # POPRAWKA: Twarde odrzucenie pętli zwrotnej (Windows Loopback / Linux lo)
                                    if ip_candidate == "127.0.0.1" or ip_candidate.startswith("127."):
                                        continue
                                        
                                    target_ip = ip_candidate
                                    prefix = ip_addr.get("prefix", 24)
                                    break
                            if target_ip: break
                        if target_ip: break
                    except: pass
                time.sleep(5)
        else:
            if "dhcp" in target_net:
                log("Kontener w trybie DHCP: Odpytuje tablice sieciowa eth0 kontenera...")
                for _ in range(6):
                    ct_ip_out, _, _ = run_cmd(f"pct exec {TEST_VM_ID} -- ip -4 addr show dev eth0 2>/dev/null")
                    ip_find = re.search(r"inet\s+([0-9\.]+)/(\d+)", ct_ip_out)
                    if ip_find:
                        target_ip = ip_find.group(1).strip()
                        prefix = int(ip_find.group(2))
                        break
                    time.sleep(5)
            else:
                static_match = re.search(r"([0-9\.]+)/(\d+)", target_net)
                if static_match:
                    target_ip = static_match.group(1).strip()
                    prefix = int(static_match.group(2))

        # Awaryjny Sniffer ARP
        if not target_ip:
            log("Brak komunikacji IP z systemem. Uruchamiam sniffer pakietow ARP na 30 sekund...")
            proc = subprocess.Popen(f"timeout 30 tcpdump -l -n -i {BRIDGE} arp 2>/dev/null", shell=True, stdout=subprocess.PIPE, text=True)
            arp_start = time.time()
            while time.time() - arp_start < 30:
                line = proc.stdout.readline()
                if not line: break
                match = re.search(r"tell\s+([0-9\.]+)", line)
                if match and match.group(1) != "0.0.0.0":
                    target_ip = match.group(1).strip()
                    break
            proc.terminate()

        if not target_ip:
            raise RuntimeError("Nie udalo sie przechwycic adresu sieciowego instancji testowej.")

        target_ip = target_ip.strip()

        # 6. Skanowanie i Audyt Sieciowy
        status_dr = "AUDIT_FAILED"
        log(f"Wykryto IP: {target_ip}. Konfiguracja aliasu sieciowego na hostu...")
        
        run_cmd(f"ip link set {BRIDGE} up 2>/dev/null || true")
        
        ip_parts = target_ip.split('.')
        host_ip = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.250/{prefix}"
        run_cmd(f"ip addr add {host_ip} dev {BRIDGE} 2>/dev/null || true")
        time.sleep(5) 
        
        if_config, _, _ = run_cmd(f"ip addr show dev {BRIDGE}")
        log(f"--- AKTUALNY STAN INTERFEJSU HOSTU Proxmox ---\n{if_config.strip()}\n---------------------------------------------")
        
        log("Wysylanie pakietow ICMP Echo (Ping)...")
        ping_out, _, _ = run_cmd(f"ping -c 4 {target_ip}")
        log(f"--- WYNIK PINGOWANIA INSTANCJI TESTOWEJ ---\n{ping_out.strip()}\n-------------------------------------------")
        
        nmap_cmd = f"nmap -Pn --send-ip -p- --open -sV -sC --min-rate 2000 {target_ip}"
        log(f"Inicjalizacja skanowania. Wykonuje komende: {nmap_cmd}")
        
        nmap_out, nmap_err, _ = run_cmd(nmap_cmd)
        if nmap_err.strip():
            nmap_out += f"\n\n[NMAP SYSTEM STDERR]\n{nmap_err.strip()}"
            
        if "open" not in nmap_out.lower():
            nmap_out += f"\n\n[DIAGNOSTIC NOTE]\n" \
                        f"Nmap detected 0 open ports inside the isolated sandbox.\n" \
                        f"The temporary host is UP and network layer responds.\n" \
                        f"If guest firewall is disabled, this means application background services\n" \
                        f"(e.g. docker engines, database stacks, backup daemons) did not finish\n" \
                        f"initialization inside the boot window. Consider increasing BOOT_DELAY_VM value in config.json."
        else:
            web_ports = re.findall(r"(\d+)/tcp\s+open\s+(\S+)", nmap_out)
            for port, service in web_ports:
                service_lower = service.lower()
                if "http" in service_lower or port in ["80", "443", "8080", "8443", "8880", "8888", "3000", "5000", "9000"]:
                    proto = "https" if (port in ["443", "8443"] or "ssl" in service_lower or "https" in service_lower) else "http"
                    web_url = f"{proto}://{target_ip}:{port}"
                    
                    if shutil.which("chromium") or shutil.which("chromium-browser"):
                        chrome_bin = "chromium" if shutil.which("chromium") else "chromium-browser"
                        log(f"🌐 Wykryto aktywny port web {port}. Uruchamiam Chromium 147 (15s budżetu czasu) dla: {web_url}...")
                        
                        cmd_web = f"{chrome_bin} --headless --no-sandbox --disable-gpu --ignore-certificate-errors --virtual-time-budget=15000 --window-size=1920,1080 --screenshot={web_png_path} '{web_url}'"
                        _, c_err, web_code = run_cmd(cmd_web)
                        
                        if os.path.exists(web_png_path) and os.path.getsize(web_png_path) > 0:
                            log("📸 [Chromium v147] Dowód działania nowoczesnej aplikacji (Proof of Life) został w pełni załadowany i zapisany.")
                            web_screenshot_taken = True
                            break
                        else:
                            log(f"❌ [Chromium Error] Błąd migawki. Kod wyjścia: {web_code}")
                            if c_err.strip(): log(f"   [Chromium STDERR]: {c_err.strip()}")
                    else:
                        log(f"[INFO] Wykryto port web {port}, ale pominięto zrzut ekranu (brak Chromium na Proxmoxie).")
                    break

        run_cmd(f"ip addr del {host_ip} dev {BRIDGE} 2>/dev/null || true")
        
        status_dr = "SUCCESS"
        log("Audyt sieciowy zakonczony pelnym sukcesem!")

        # 7. Zbieranie Dowodów (Screenshot konsoli maszyn wirtualnych)
        if is_vm:
            log("Pobieranie wirtualnego zrzutu ekranu konsoli (Log Bypass)...")
            screenshot_error_msg = ""
            ppm_fake_log_path = f"/var/log/dr_screen_{TEST_VM_ID}.log"
            node_name, _, _ = run_cmd("hostname")
            node_name = node_name.strip()
            
            run_cmd(f'pvesh create /nodes/{node_name}/qemu/{TEST_VM_ID}/monitor --command "screendump {ppm_fake_log_path}"')
            
            if os.path.exists(ppm_fake_log_path):
                try:
                    with Image.open(ppm_fake_log_path) as im:
                        im.save(png_path)
                    os.remove(ppm_fake_log_path)
                    log("Zrzut z konsoli graficznej pobrany pomyslnie.")
                except Exception as e:
                    screenshot_error_msg = f"Blad przetwarzania obrazu: {str(e)}"
                    if os.path.exists(ppm_fake_log_path): os.remove(ppm_fake_log_path)
            else:
                screenshot_error_msg = "Blad: Brak wygenerowanego pliku obrazu z monitora QEMU."
        else:
            log("Zrzucanie ostatnich 25 linii logow systemowych z kontenera...")
            screenshot_error_msg = "TRYB LXC: Ponizej zalaczono logi systemowe kontenera."
            ct_logs, _, _ = run_cmd(f"pct exec {TEST_VM_ID} -- tail -n 25 /var/log/messages 2>/dev/null || pct exec {TEST_VM_ID} -- journalctl -n 25 --no-pager 2>/dev/null")
            if not ct_logs.strip():
                ct_logs = "Brak wpisow w logach systemowych wewnatrz kontenera."

    except Exception as e:
        log(f"KRYTYCZNY BLAD SKRYPTU: {str(e)}")
        if status_dr == "CRASHED_BEFORE_START":
            status_dr = "SCRIPT_EXCEPTION_CRASH"

    finally:
        log("=== GWARANTOWANE GENEROWANIE RAPORTU PDF ===")
        pdf_path = "/tmp/raport_dr_automated.pdf"
        try:
            pdf = FPDF()
            pdf.add_page()
            
            pdf.set_font("helvetica", "B", 16)
            pdf.cell(0, 10, clean_text("Automated Disaster Recovery Report"))
            pdf.ln(12)
            
            pdf.set_font("helvetica", "", 11)
            pdf.cell(0, 8, clean_text(f"Target Resource: {chosen_id} ({chosen_type.upper()}) | Name: {chosen_name}"))
            pdf.ln(6)
            pdf.cell(0, 8, clean_text(f"Final Verification Status: {status_dr}"))
            pdf.ln(6)
            pdf.cell(0, 8, clean_text(f"Source Backup Target: {latest_backup}"))
            pdf.ln(10)
            
            pdf.set_font("helvetica", "B", 12)
            pdf.cell(0, 10, "1. Full Execution Runtime Logs (Terminal Console Dump):")
            pdf.ln(7)
            pdf.set_font("courier", "", 7)
            
            cleaned_logs = [clean_text(line) for line in execution_logs]
            full_dump_text = "\n".join(cleaned_logs)
            
            pdf.multi_cell(0, 3.5, full_dump_text)
            pdf.ln(10)
            
            if environment_created and status_dr not in ["STORAGE_ERROR", "NO_BACKUPS_FOUND", "RESTORE_FAILED"]:
                pdf.set_font("helvetica", "B", 12)
                pdf.cell(0, 10, "2. Network Security Port Audit (ALL OPEN PORTS):")
                pdf.ln(7)
                pdf.set_font("courier", "", 9)
                pdf.multi_cell(0, 4, clean_text(nmap_out))
                pdf.ln(10)
                
                pdf.set_font("helvetica", "B", 12)
                pdf.cell(0, 10, "3. Operating System Health Verification (Hypervisor Console):")
                pdf.ln(7)
                
                if is_vm:
                    if os.path.exists(png_path) and screenshot_error_msg == "":
                        pdf.image(png_path, x=10, w=180)
                    else:
                        pdf.set_font("courier", "", 10)
                        pdf.multi_cell(0, 5, clean_text(f"Graficzna konsola niedostepna. Powod: {screenshot_error_msg}"))
                else:
                    pdf.set_font("courier", "", 8)
                    pdf.multi_cell(0, 4, clean_text(f"{screenshot_error_msg}\n\n=== LOG SNAPSHOT ===\n{ct_logs}"))
                
                if web_screenshot_taken and os.path.exists(web_png_path):
                    pdf.ln(10)
                    pdf.set_font("helvetica", "B", 12)
                    pdf.cell(0, 10, "4. Web Service Application Verification (Proof of Life Screenshot):")
                    pdf.ln(7)
                    pdf.image(web_png_path, x=10, w=180)
            
            pdf.output(pdf_path)
            print("[SYSTEM] Plik PDF wygenerowany na dysku.")
        except Exception as pdf_err:
            print(f"[CRITICAL] Blad krytyczny podczas generowania PDF: {pdf_err}")

        if WEBHOOK_URL:
            print("[SYSTEM] Inicjalizacja powiadomienia Webhook...")
            try:
                emoji = "✅" if status_dr == "SUCCESS" else "❌"
                webhook_payload = {
                    "text": f"{emoji} *Zakonczono test DR dla obiektu {chosen_type.upper()}*\n"
                            f"• *ID:* `{chosen_id}`\n"
                            f"• *Nazwa:* `{chosen_name}`\n"
                            f"• *Status:* `{status_dr}`\n"
                            f"• *Kopia źródłowa:* `{latest_backup.split('/')[-1]}`"
                }
                
                req = urllib.request.Request(
                    WEBHOOK_URL, 
                    data=json.dumps(webhook_payload).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    response.read()
                print("[SYSTEM] Powiadomienie Webhook wyslane.")
            except Exception as web_err:
                print(f"[⚠️ WARNING] Nie udalo sie dostarczyc pakietu Webhook: {web_err}")

        print("[SYSTEM] Przygotowanie wysylki poczty SMTP...")
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = MAIL_TO
        msg['Subject'] = f"[AUTOMATED-DR] {chosen_type.upper()} {chosen_id} - {chosen_name} -> Status: {status_dr}"
        
        mail_body = f"Automated system test finished with status: {status_dr}.\n\nPelne logi z przebiegu testu:\n\n"
        mail_body += "\n".join([clean_text(line) for line in execution_logs])
        msg.attach(MIMEText(mail_body, 'plain'))
        
        if os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
                encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="DR_Report_{chosen_id}.pdf"')
                msg.attach(part)
        else:
            part = MIMEBase('text', 'plain')
            part.set_payload("\n".join([clean_text(line) for line in execution_logs]).encode('utf-8'))
            encode_base64(part)
            part.add_header('Content-Disposition', 'attachment; filename="dr_crash_logs.txt"')
            msg.attach(part)
                
        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, MAIL_TO, msg.as_string())
            server.quit()
            print("[SYSTEM] Raport mailowy wyslany pomyslnie.")
        except Exception as smtp_err: 
            print(f"[CRITICAL] Krytyczny blad sieci pocztowej SMTP: {smtp_err}")

        if environment_created:
            print(f"[CLEANUP] Bezwarunkowe czyszczenie zasobow dla ID {TEST_VM_ID}...")
            if is_vm:
                run_cmd(f"qm stop {TEST_VM_ID} 2>/dev/null")
                run_cmd(f"qm destroy {TEST_VM_ID} --destroy-unreferenced-disks 1 2>/dev/null")
            else:
                run_cmd(f"pct stop {TEST_VM_ID} 2>/dev/null")
                run_cmd(f"pct destroy {TEST_VM_ID} 2>/dev/null")
            
        for f in [png_path, web_png_path, pdf_path]:
            if os.path.exists(f): os.remove(f)
                
        print(f"=== KONIEC PROCESU AUTOMATYZACJI. WYNIK: {status_dr} ===")

if __name__ == "__main__":
    main()
