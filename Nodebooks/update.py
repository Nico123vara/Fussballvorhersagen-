import logging
import os
import subprocess
from datetime import datetime

# ─── Logging Setup ───────────────────────────────────────────────────────────
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s — %(levelname)s — %(message)s',
    handlers=[
        logging.FileHandler(f'logs/update_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()  # auch im Terminal anzeigen
    ]
)

log = logging.getLogger(__name__)


def run_script(script_name):
    """Führt ein Script aus und loggt Output und Fehler."""
    log.info(f"=== Starte {script_name} ===")
    start = datetime.now()

    try:
        result = subprocess.run(
            ['uv', 'run', script_name],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        # Output loggen
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    log.info(f"  {line}")

        # Fehler loggen
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    log.warning(f"  STDERR: {line}")

        # Erfolg oder Fehler
        dauer = (datetime.now() - start).seconds
        if result.returncode == 0:
            log.info(f"=== {script_name} erfolgreich ({dauer}s) ===\n")
            return True
        else:
            log.error(f"=== {script_name} FEHLER (returncode={result.returncode}) ===\n")
            return False

    except Exception as e:
        log.error(f"=== {script_name} EXCEPTION: {e} ===\n")
        return False


def main():
    log.info("╔══════════════════════════════════════╗")
    log.info("║     Bundesliga Update gestartet      ║")
    log.info("╚══════════════════════════════════════╝\n")

    start_total = datetime.now()
    erfolge = []

    # 1. Neue Spiele laden
    ok = run_script('monthly_update.py')
    erfolge.append(('monthly_update.py', ok))

    # 2. Modell neu trainieren
    ok = run_script('retrain.py')
    erfolge.append(('retrain.py', ok))

    # 3. Vorhersagen speichern
    ok = run_script('save_predictions.py')
    erfolge.append(('save_predictions.py', ok))

    # Zusammenfassung
    dauer_total = (datetime.now() - start_total).seconds
    log.info("╔══════════════════════════════════════╗")
    log.info("║            Zusammenfassung           ║")
    log.info("╚══════════════════════════════════════╝")

    alle_ok = True
    for script, ok in erfolge:
        status = "✅ OK" if ok else "❌ FEHLER"
        log.info(f"  {script}: {status}")
        if not ok:
            alle_ok = False

    log.info(f"\n  Gesamtdauer: {dauer_total}s")

    if alle_ok:
        log.info("  Status: Alles erfolgreich ✅")
    else:
        log.error("  Status: Fehler aufgetreten ❌ — Log prüfen!")


if __name__ == "__main__":
    main()
