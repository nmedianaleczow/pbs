# Proxmox VE Automated DR Test Engine (v4.1)

Automated Disaster Recovery (DR) testing script for Proxmox VE clusters connected to Proxmox Backup Server (PBS).

[Instrukcja w języku polskim](#instrukcja-polish-version) | [English Instructions](#instructions-english-version)

---

## Instrukcja (Polish Version)

Skrypt służy do automatycznego i bezobsługowego testowania kopii zapasowych (Disaster Recovery) losowo wybranych maszyn wirtualnych (VM) oraz kontenerów (LXC) z repozytorium Proxmox Backup Server (PBS). 

Całość wykonuje się w odizolowanym środowisku sieciowym (Sandbox). Skrypt sprawdza dostępność usług przez Nmap, zbiera logi lub zrzuty ekranu, a na koniec czyści po sobie storage i wysyła raport na e-mail oraz webhooka.

### Jak działa skrypt?

1. Losowanie celu: Pobiera pełną listę kopii z PBS, losuje jedną maszynę VM lub kontener LXC i lokalizuje najnowszy dostępny backup.
2. Przywracanie: Klonuje wylosowany backup do wskazanego storage testowego pod tymczasowym ID 999.
3. Czyszczenie konfigu: Odpina osierocone obrazy ISO (które mogłyby zablokować bootowanie) i czyści stare interfejsy sieciowe w jądrze.
4. Izolacja sieci: Przepina wirtualną kartę sieciową do osobnego mostka (vmbr999), całkowicie odcinając maszynę od sieci produkcyjnej i internetu.
5. Ekran dla VM: W przypadku maszyn wirtualnych wymusza standardową kartę graficzną (--vga std), żeby QEMU odpaliło bufor ekranu do screenshotów.
6. Rozruch: Uruchamia instancję i czeka na pełne załadowanie systemu (40 sekund dla VM, 15 sekund dla LXC).
7. Wykrywanie IP: Ustala adres IP przez QEMU Guest Agent, komendy pct exec lub pasywny sniffer pakietów ARP (tcpdump).
8. Audyt portów: Tworzy tymczasowy alias IP na hoście Proxmoxa i skanuje wszystkie 65535 portów przez Nmap, wyciągając tylko te otwarte.
9. Dowód działania: Robi screenshot z konsoli graficznej VM lub wyciąga 25 ostatnich linii logów systemowych z kontenera LXC.
10. Raportowanie: Generuje plik PDF z pełnym logiem konsoli krok po kroku, wysyła go mailem i strzela webhookiem z podsumowaniem (np. na Slacka lub Discorda).

### Wbudowane zabezpieczenia

- Bezpieczeństwo produkcji: Skrypt działa wyłącznie na klonie. Nie dotyka oryginalnych maszyn ani rzeczywistych danych na PBS.
- Izolacja sandbox: Blokada maszyny wewnątrz unikalnego vmbr999 bez routingu wyklucza konflikt adresów IP w sieci czy fałszywe alerty w monitoringach.
- Gwarantowane czyszczenie (Failsafe): Cała logika sprzątająca siedzi w bloku finally. Niezależnie od błędu w trakcie testu (brak miejsca, timeout PBS), maszyna 999 zostanie bezwzględnie wyłączona i skasowana.
- Ominięcie blokad AppArmor: Zrzut ekranu leci bezpośrednio do katalogu /var/log/ z rozszerzeniem .log, dzięki czemu kernel nie blokuje zapisu.
- Odporność na awarię webhooka: Sekcja API ma własny try-except. Jeśli Slack leży, skrypt i tak wyśle maila i posprząta dyski.
- Brak crashu na znakach Unicode: Funkcja clean_text() filtruje logi systemowe i usuwa polskie znaki przed budowaniem PDF, co zapobiega wywaleniu się biblioteki FPDF.

### Wymagania systemowe

Zaloguj się na hosta PVE przez SSH jako root i zainstaluj pakiety:

```bash
apt update && apt install nmap tcpdump python3-pil python3-fpdf -y
```

### Konfiguracja
Edytuj sekcję GLOBAL CONFIGURATION na samym górze skryptu:
PBS_PVE_STORAGE: Nazwa Twojego storage PBS w Proxmoxie (np. PBS-1Y).
TARGET_STORAGE: Storage docelowy na maszynę testową (np. local-lvm lub SANDBOX).
TEST_VM_ID: Tymczasowe ID instancji testowej (domyślnie 999).
BRIDGE: Odizolowany mostek sieciowy (np. vmbr999).
WEBHOOK_URL: URL do webhooka Slack/Discord/Teams. Jeśli nie używasz, zostaw puste "".
Pola SMTP_* oraz MAIL_TO: Dane serwera pocztowego do wysyłki raportów PDF.
Uruchomienie
Wrzuć skrypt na Proxmoxa jako /root/dr_test_automation.py.
Nadaj uprawnienia:
```Bash
chmod +x /root/dr_test_automation.py
```
Odpal test ręcznie:
```Bash
python3 /root/dr_test_automation.py
```
Harmonogram Crontab
Żeby skrypt leciał automatycznie w każdą niedzielę o 2:00 w nocy:
```Bash
crontab -e
```
Wklej na samym dole:
Fragment kodu
```
0 2 * * 0 /usr/bin/python3 /root/dr_test_automation.py >> /var/log/dr_script_cron.log 2>&1
```
## Instructions (English Version)
Automated, hands-free Disaster Recovery (DR) testing script for randomly selected Virtual Machines (VM) and Containers (LXC) stored on Proxmox Backup Server (PBS).
It runs inside a 100% isolated sandbox network, performs a full service port audit via Nmap, captures console screenshots or system logs, emails a PDF report, fires a webhook, and cleans up the storage afterward.
### How it works
1. Target Selection: Fetches the backup list from PBS, randomly picks a VM or LXC, and finds the latest snapshot.
2. Restore: Clones the selected backup to the designated test storage using temporary ID 999.
3. Config Sanitation: Detaches orphaned ISO images and cleans old network interfaces in the kernel.
4. Network Isolation: Reconfigures the network interface to an isolated bridge (vmbr999), cutting it off from the LAN and Internet.
5. Display for VM: Forces a standard graphic card (--vga std) for VMs to initialize the frame buffer for screenshots.
6. Booting: Starts the instance and waits for the OS to initialize (40s for VM, 15s for LXC).
7. IP Resolution: Detects the internal IP via QEMU Guest Agent, pct exec, or passive ARP sniffing (tcpdump).
8. Port Audit: Creates a temporary IP alias on the host and scans all 65535 ports using Nmap, listing open services only.
9. Evidence Collection: Captures a graphical screenshot of the VM console or extracts the last 25 lines of LXC logs.
10. Reporting: Generates a step-by-step PDF report from the console log, emails it, and sends a summary via Webhook.
### Built-in Failsafe Features
1. Production Safe: Operates strictly on cloned data. Never touches live environments or actual PBS backup chunks.
2. Sandbox Isolation: Locking the machine inside an unrouted vmbr999 bridge prevents IP conflicts and false monitoring alerts.
3. Failsafe Storage Protection: The entire cleanup routine is wrapped in a finally block. No matter where the script fails, instance 999 is unconditionally stopped and destroyed.
4. AppArmor Bypass: Saves raw screen dumps directly to /var/log/ as a .log file to bypass kernel write blocks.
5. Webhook Fault Tolerance: The API notification logic runs in its own try-except handler. If your chat platform is down, email delivery and disk wiping still execute.
6. Unicode Crash Prevention: The clean_text() filter strips out non-ASCII characters and foreign diacritics, preventing FPDF engine crashes.
### Prerequisites
Log in via SSH to your PVE node as root and run:
```Bash
apt update && apt install nmap tcpdump python3-pil python3-fpdf -y
```
### Configuration
Modify the GLOBAL CONFIGURATION section at the top of the script:
PBS_PVE_STORAGE: The name of your PBS storage in PVE (e.g., PBS-1Y).
TARGET_STORAGE: Target storage where the temporary instance will be restored (e.g., local-lvm).
TEST_VM_ID: Temporary VMID used for the sandbox environment (default 999).
BRIDGE: Isolated virtual network bridge (e.g., vmbr999).
WEBHOOK_URL: Your webhook URL (Slack/Discord/Teams). Leave as "" to disable.
SMTP_* fields & MAIL_TO: Mail server settings for PDF report delivery.
Usage
Save the script on the Proxmox host as /root/dr_test_automation.py.
Make it executable:
```Bash
chmod +x /root/dr_test_automation.py
```
Run a manual dry run:
```Bash
python3 /root/dr_test_automation.py
```
Crontab Automation
To schedule the script to run every Sunday at 2:00 AM:
```Bash
crontab -e
```
Append the following line:
```
0 2 * * 0 /usr/bin/python3 /root/dr_test_automation.py >> /var/log/dr_script_cron.log 2>&1
```
