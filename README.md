# Proxmox VE Automated DR Test Engine (v4.26)

Automated Disaster Recovery (DR) testing script for Proxmox VE clusters connected to Proxmox Backup Server (PBS).

[Instrukcja w języku polskim](#instrukcja-polish-version) | [English Instructions](#instructions-english-version)

---

## Instrukcja (Polish Version)

Skrypt służy do automatycznego i bezobsługowego testowania kopii zapasowych (Disaster Recovery) losowo wybranych maszyn wirtualnych (VM) oraz kontenerów (LXC) z repozytorium Proxmox Backup Server (PBS). 

Całość wykonuje się w odizolowanym środowisku sieciowym (Sandbox). Skrypt sprawdza dostępność usług przez Nmap (wraz z głębokim audytem skryptami NSE), generuje zrzuty ekranu z konsoli systemowej oraz **pobiera pełne, graficzne screenshoty paneli aplikacji webowych (np. UniFi, Proxmox, Oxidized, Xopero)** za pomocą dedykowanego silnika Chromium. Na koniec czyści po sobie storage i wysyła kompletny raport PDF na e-mail oraz webhooka.

### Jak działa skrypt?

1. **Losowanie celu:** Pobiera pełną listę kopii z PBS, losuje jedną maszynę VM lub kontener LXC i lokalizuje najnowszy dostępny backup (lub przyjmuje ID wskazane ręcznie).
2. **Przywracanie:** Klonuje wylosowany backup do wskazanego storage testowego pod tymczasowym ID 999.
3. **Czyszczenie konfigu:** Odpina osierocone obrazy ISO (które mogłyby zablokować bootowanie) i czyści stare interfejsy sieciowe w jądrze.
4. **Izolacja sieci:** Przepina wirtualną kartę sieciową do osobnego mostka (vmbr999), całkowicie odcinając maszynę od sieci produkcyjnej i internetu.
5. **Ekran dla VM:** W przypadku maszyn wirtualnych wymusza standardową kartę graficzną (`--vga std`), żeby QEMU odpaliło bufor ekranu do screenshotów.
6. **Rozruch:** Uruchamia instancję i czeka na pełne załadowanie systemu i usług (domyślnie 90 sekund dla VM, 15 sekund dla LXC).
7. **Wykrywanie IP:** Ustala adres IP przez QEMU Guest Agent, komendy `pct exec` lub pasywny sniffer pakietów ARP (`tcpdump`).
8. **Audyt portów i usług:** Tworzy tymczasowy alias IP na hoście Proxmoxa i skanuje wszystkie porty przez Nmap z flagami `-sV -sC`. Wyciąga otwarte porty, bannery usług, nagłówki HTTP oraz klucze SSH.
9. **Fotografia aplikacji Web (Proof of Life):** Jeśli wykryje port HTTP/HTTPS (w tym porty niestandardowe i deweloperskie jak 8888, 3000, 5000, 9000), uruchamia odizolowany silnik Chromium z buforem czasowym 15 sekund, pozwalając ciężkim panelom (SPA/React/Java) na pełne wyrenderowanie formularza logowania przed wykonaniem zrzutu.
10. **Zrzut konsoli:** Robi screenshot z konsoli graficznej VM lub wyciąga 25 ostatnich linii logów systemowych z kontenera LXC.
11. **Raportowanie:** Generuje plik PDF z pełnym logiem konsoli krok po kroku, wynikami Nmapa oraz wklejonymi obrazkami (konsola + strona www). Wysyła go mailem i strzela webhookiem z podsumowaniem (np. na Slacka lub Discorda).

### Wbudowane zabezpieczenia

* **Bezpieczeństwo produkcji:** Skrypt działa wyłącznie na klonie. Nie dotyka oryginalnych maszyn ani rzeczywistych danych na PBS.
* **Izolacja sandbox:** Blokada maszyny wewnątrz unikalnego `vmbr999` bez routingu wyklucza konflikt adresów IP w sieci czy fałszywe alerty w monitoringach.
* **Gwarantowane czyszczenie (Failsafe):** Cała logika sprzątająca siedzi w bloku `finally`. Niezależnie od błędu w trakcie testu, maszyna 999 zostanie bezwzględnie wyłączona i skasowana.
* **Odporność na awarię sieci:** Sekcje powiadomień mają własne bloki przechwytywania wyjątków – awaria Slacka nie blokuje wysyłki maila ani czyszczenia dysków.

### Wymagania systemowe

Zaloguj się na hosta PVE przez SSH jako root. Nowoczesne wersje Chromium (150+) posiadają blokady jądra (Crashpad locks), które uniemożliwiają działanie headless na maszynie matce Proxmoxa. **Wymagane jest zainstalowanie stabilnej wersji granicznej Chromium 147 i zablokowanie jej aktualizacji:**

```bash
# 1. Instalacja pakietów bazowych
apt update && apt install nmap tcpdump python3-pil python3-fpdf -y
```
# 2. Downgrade Chromium do stabilnej wersji 147
```
apt install -y \
  chromium=147.0.7727.137-1~deb13u1 \
  chromium-common=147.0.7727.137-1~deb13u1 \
  chromium-sandbox=147.0.7727.137-1~deb13u1
```
# 3. Zablokowanie pakietów przed automatyczną aktualizacją systemu
```
apt-mark hold chromium chromium-common chromium-sandbox
```
Konfiguracja

Edytuj plik config.json znajdujący się w tym samym katalogu co skrypt:

    PBS_PVE_STORAGE: Nazwa Twojego storage PBS w Proxmoxie (np. PBS-1Y).

    TARGET_STORAGE: Storage docelowy na maszynę testową (np. local-lvm).

    TEST_VM_ID: Tymczasowe ID instancji testowej (domyślnie 999).

    BRIDGE: Odizolowany mostek sieciowy (np. vmbr999).

    BOOT_DELAY_VM / BOOT_DELAY_LXC: Czas oczekiwania na podniesienie OS (sekundy).

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

Żeby skrypt leciał automatycznie w każdą niedzielę o 2:00 w nocy, wpisz crontab -e i wklej na samym dole:
Plaintext
```
0 2 * * 0 /usr/bin/python3 /root/dr_test_automation.py >> /var/log/dr_script_cron.log 2>&1
```
##Instructions (English Version)

Automated, hands-free Disaster Recovery (DR) testing script for randomly selected Virtual Machines (VM) and Containers (LXC) stored on Proxmox Backup Server (PBS).

It runs inside a 100% isolated sandbox network, performs a full service port and banner audit via Nmap NSE, captures system console screenshots, takes pixel-perfect graphical screenshots of web application panels (e.g., UniFi, Proxmox, Oxidized, Xopero) using a dedicated Chromium engine, emails a PDF report, fires a webhook, and cleans up the storage afterward.
How it works

  1.**Target Selection:** Fetches the backup list from PBS, randomly picks a VM or LXC, and finds the latest snapshot (or accepts a manually specified ID).

  2.**Restore:** Clones the selected backup to the designated test storage using temporary ID 999.

  3.**Config Sanitation:** Detaches orphaned ISO images and cleans old network interfaces in the kernel.

  4.**Network Isolation:** Reconfigures the network interface to an isolated bridge (vmbr999), cutting it off from the LAN and Internet.

  5.**Display for VM:** Forces a standard graphic card (--vga std) for VMs to initialize the frame buffer for screenshots.

  6.**Booting:** Starts the instance and waits for the OS and background daemons to initialize (default 90s for VM, 15s for LXC).

  7.**IP Resolution:** Detects the internal IP via QEMU Guest Agent, pct exec, or passive ARP sniffing (tcpdump).

  8.**Port & Service Audit:** Creates a temporary IP alias on the host and scans all ports using Nmap with -sV -sC flags to extract open services, banners, HTTP headers, and SSH keys.

  9.**Web App Photography (Proof of Life):** If a web service is detected (including custom management ports like 8888, 3000, 5000, 9000), it deploys the Chromium engine with a 15-second virtual time budget, ensuring heavy client-side applications (SPA/React/Java) fully render their login pages before capturing the image.

  10.**Evidence Collection:** Captures a graphical screenshot of the VM console or extracts the last 25 lines of LXC logs.

  11.**Reporting:** Generates a comprehensive step-by-step PDF report including terminal outputs, Nmap audit results, and embedded images (both console and web application screen). Delivers it via SMTP mail and posts a summary via Webhook.

System Prerequisites

Log in via SSH to your PVE node as root. Modern Chromium builds (150+) introduce kernel-level namespace constraints (Crashpad handlers) that cause immediate crashes on a bare Proxmox host. You must downgrade to the stable threshold version (Chromium 147) and pin the packages:
Bash

# 1. Install baseline prerequisites
```
apt update && apt install nmap tcpdump python3-pil python3-fpdf -y
```
# 2. Downgrade Chromium to the stable v147 branch
```
apt install -y \
  chromium=147.0.7727.137-1~deb13u1 \
  chromium-common=147.0.7727.137-1~deb13u1 \
  chromium-sandbox=147.0.7727.137-1~deb13u1
```
# 3. Hold the packages to block automatic system upgrades
```
apt-mark hold chromium chromium-common chromium-sandbox
```

Changelog / Historia zmian
v4.26

🇵🇱 Wersja polska:

    Rozszerzenie tablicy monitorowanych portów webowych: Rozbudowano wewnętrzny filtr skryptu o porty deweloperskie i administracyjne: 8888 (Oxidized / Puma), 3000 (Grafana), 5000 (Docker Registry / Flask) oraz 9000 (Portainer). Zapobiega to pomijaniu paneli webowych w sytuacji, gdy Nmap zidentyfikuje usługę pod niestandardową lub nierozpoznaną nazwą (np. sun-answerbook?).

🇬🇧 English Version:

    Expanded Monitored Web Ports Array: Expanded the internal web port validation matrix to include common administrative and development ports: 8888 (Oxidized / Puma), 3000 (Grafana), 5000 (Docker Registry), and 9000 (Portainer). This prevents the capture engine from skipping web applications when Nmap flags the service under generic non-standard labels (e.g., sun-answerbook?).

v4.25

🇵🇱 Wersja polska:

    Wdrożenie buforu czasu dla JavaScript (SPA): Dodano flagę --virtual-time-budget=15000 (15 sekund) do silnika graficznego Chromium. Pozwala to na pełne załadowanie i wykonanie asynchronicznych skryptów JS na ciężkich panelach logowania (UniFi, Xopero, Proxmox API) przed przechwyceniem obrazu, eliminując problem "pustych białych pasków".

🇬🇧 English Version:

    JavaScript Execution Time Budget (SPA): Integrated the --virtual-time-budget=15000 (15 seconds) flag into the Chromium capture command. This forces the browser to wait for heavy asynchronous JS components (such as UniFi, Xopero, or PVE login frameworks) to render completely before taking the snapshot, eliminating empty white bar artifacts.

v4.24

🇵🇱 Wersja polska:

    Przywrócenie silnika Chromium (Obejście blokad jądra PVE): Ze względu na ograniczenia przestrzeni nazw jądra Linuxa i asercje modułu Crashpad wprowadzone w Chromium 150+, udokumentowano i zaimplementowano procedurę obniżenia wersji przeglądarki do Chromium 147 (apt-mark hold). Skrypt odzyskał natywną możliwość robienia zrzutów ekranu stron www bezpośrednio z poziomu konta root na hoście.

🇬🇧 English Version:

    Chromium Engine Restoration (PVE Kernel Namespace Bypass): Due to strict Linux kernel namespace locks and Crashpad assertions introduced in Chromium 150+, documented and deployed a package pinning strategy downgrading the browser to Chromium 147 (apt-mark hold). Restored native full-fidelity web screenshot captures running directly as root on the hypervisor host.

v4.20

🇵🇱 Wersja polska:

    Głęboki audyt usług za pomocą Nmap NSE: Do głównego skanowania sieciowego dodano flagę -sC (skrypty domyślne Nmap Scripting Engine). Skrypt automatycznie pobiera teraz zaawansowane dane diagnostyczne: nagłówki serwerów, metody HTTP, tytuły stron HTML oraz odciski kluczy hostów SSH i umieszcza je bezpośrednio w Sekcji 2 raportu PDF.

🇬🇧 English Version:

    Deep Service Auditing via Nmap NSE: Appended the -sC (default Nmap Scripting Engine scripts) flag to the scanning engine. The engine now automatically extracts deep diagnostic parameters: server header data, HTTP methods, native HTML page titles, and SSH host key fingerprints, embedding them seamlessly into Section 2 of the PDF report.

v4.16

🇵🇱 Wersja polska:

    Rozbudowane logowanie błędów podprocesów: Dodano pełne przechwytywanie strumieni STDOUT/STDERR oraz kodów wyjścia dla zewnętrznych narzędzi renderujących. Wszystkie niepowodzenia systemowe są teraz jawnie wypisywane w konsoli i dołączane do raportu tekstowego.

🇬🇧 English Version:

    Subprocess Error Logging Overhaul: Implemented exhaustive STDOUT/STDERR and exit-code capture handlers for external rendering utilities. Any runtime environment faults are now clearly isolated, echoed to the screen, and attached to the text log dump.

v4.12

🇵🇱 Wersja polska:

    Zewnętrzny plik konfiguracyjny (config.json): Odseparowano hasła SMTP, tokeny webhooków i nazwy zasobów od kodu źródłowego.

    Manualny wybór ID z timeoutem: Dodano opcję ręcznego wskazania ID maszyny do testu DR (15 sekund oczekiwania na wpis przed losowaniem).

    Dynamiczne pobieranie nazw maszyn: Skrypt pobiera prawdziwą nazwę bezpośrednio z odzyskanej konfiguracji Proxmoxa.

    Deaktywacja Zapory PVE (Firewall): Wymuszono wyłączenie firewallu dla instancji testowej (firewall=0).

🇬🇧 English Version:

    Externalized Configuration (config.json): Separated credentials (SMTP, webhooks, storages) from the script code.

    Manual ID Input with Timeout: Added capability to manually select a specific ID for the DR test (15-second prompt fallback to random).

    Robust Name Resolution: Extracted real VM/CT hostnames directly from the restored configuration.

    PVE Firewall Deactivation: Disabled the network cluster firewall for the temporary instance (firewall=0).
