import requests
import json
import os
from time import sleep

# ─── Konfiguration ───────────────────────────────────────────────────────────
API_KEY  = "0a51501f0bc740b39ac6633ef6e913d9"
BASE_URL = "https://api.football-data.org/v4"
HEADERS  = {"X-Auth-Token": API_KEY}

LIGEN = {
    'BL1': {'name': 'Bundesliga',     'saisons': [2023, 2024, 2025]},
    'PL':  {'name': 'Premier League', 'saisons': [2023, 2024, 2025]},
    'SA':  {'name': 'Serie A',        'saisons': [2023, 2024, 2025]},
}

os.makedirs('data', exist_ok=True)


def fetch_teams(liga_code, saison):
    url = f"{BASE_URL}/competitions/{liga_code}/teams?season={saison}"
    print(f"  Teams {liga_code} {saison}...")
    resp = requests.get(url, headers=HEADERS)
    sleep(6)  # Rate Limit: 10 Requests/Minute
    if resp.status_code != 200:
        print(f"  Fehler: {resp.status_code}")
        return None
    return resp.json()


def fetch_matches(liga_code, saison):
    url = f"{BASE_URL}/competitions/{liga_code}/matches?season={saison}"
    print(f"  Matches {liga_code} {saison}...")
    resp = requests.get(url, headers=HEADERS)
    sleep(6)
    if resp.status_code != 200:
        print(f"  Fehler: {resp.status_code}")
        return None
    return resp.json()


def main():
    print("=== Daten holen für alle Ligen ===\n")

    for liga_code, info in LIGEN.items():
        print(f"--- {info['name']} ({liga_code}) ---")

        for saison in info['saisons']:
            # Teams
            teams_data = fetch_teams(liga_code, saison)
            if teams_data:
                path = f"data/teams_{liga_code}_{saison}.json"
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(teams_data, f, ensure_ascii=False)
                print(f"  Gespeichert: {path}")

            # Matches
            matches_data = fetch_matches(liga_code, saison)
            if matches_data:
                path = f"data/matches_{liga_code}_{saison}.json"
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(matches_data, f, ensure_ascii=False)
                anzahl = len(matches_data.get('matches', []))
                print(f"  Gespeichert: {path} ({anzahl} Spiele)")

        print()

    print("Fertig!")


if __name__ == "__main__":
    main()
