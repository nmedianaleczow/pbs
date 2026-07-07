# Proxmox VE Automated DR Test Engine (v4.12)

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
## Changelog / Historia zmian

### v4.12
**🇵🇱 Wersja polska:**
* **Zewnętrzny plik konfiguracyjny (`config.json`):** Odseparowano hasła SMTP, tokeny webhooków i nazwy zasobów od kodu źródłowego, co umożliwia bezpieczne aktualizacje samego skryptu.
* **Manualny wybór ID z timeoutem:** Dodano opcję ręcznego wskazania ID maszyny do testu DR. Skrypt odczekuje 15 sekund na wpis użytkownika – w przypadku braku akcji automatycznie przechodzi do losowania.
* **Dynamiczne pobieranie nazw maszyn:** Naprawiono błąd wyświetlania `UNKNOWN_NAME` — skrypt pobiera teraz prawdziwą nazwę bezpośrednio z odzyskanej konfiguracji Proxmoxa.
* **Deaktywacja Zapory PVE (Firewall):** Wymuszono wyłączenie firewallu klastra Proxmox dla maszyn wirtualnych (`firewall=0`), co zapobiega domyślnemu blokowaniu ruchu wewnątrz odizolowanego mostka.
* **Wymuszenie aktywacji interfejsu:** Dodano automatyczne podnoszenie wirtualnego mostka (`ip link set ... up`) przed rozpoczęciem audytu sieciowego.
* **Usprawnienia skanowania Nmap:** Wprowadzono flagi `-Pn` (pomijanie sprawdzania ping) oraz `--send-ip` (wymuszenie trasowania warstwy 3), eliminując błędy tablicy ARP i błyskawiczne zamykanie procesu na świeżych interfejsach.
* **Pełne logowanie w e-mailach:** Wiadomości SMTP zawierają teraz kompletny zrzut logów z konsoli zamiast ostatnich 15 linii.
* **Zaawansowana diagnostyka w PDF:** Do raportu dodano logowanie wyniku komendy `ping` oraz automatyczną sekcję rozwiązywania problemów w przypadku wykrycia 0 otwartych portów.

**🇬🇧 English Version:**
* **Externalized Configuration (`config.json`):** Completely separated credentials (SMTP passwords, webhook tokens, storage names) from the source code, allowing safe script updates.
* **Manual ID Input with Timeout:** Added capability to manually select a specific VM/CT for the DR test. The script waits 15 seconds for user input and automatically falls back to random selection if no input is detected.
* **Robust Name Resolution:** Fixed the bug that previously caused VM names to display as `UNKNOWN_NAME`. The script now extracts the real hostname directly from the active temporary instance configuration.
* **PVE Firewall Deactivation:** Explicitly disabled the Proxmox cluster firewall for Virtual Machines (`firewall=0`) to prevent default traffic dropping inside the isolated sandbox.
* **Interface Activation Force:** Added automated virtual bridge interface activation (`ip link set ... up`) prior to starting network scans.
* **Nmap Scan Optimizations:** Integrated `-Pn` (skip host discovery) and `--send-ip` (enforce Layer 3 routing) flags, resolving ARP table inconsistencies and instant scan drops on fresh virtual environments.
* **Full Email Content Logs:** Updated the SMTP mail body to deliver the comprehensive terminal runtime output rather than filtering only the final 15 lines.
* **Enhanced PDF Diagnostics:** Incorporated full `ping` output logging and an automated troubleshooting block (Diagnostic Note) that triggers if 0 open ports are discovered.
