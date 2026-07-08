import requests
from datetime import date, timedelta

API_KEY = "0a51501f0bc740b39ac6633ef6e913d9"
headers = {"X-Auth-Token": API_KEY}

heute = date.today()
bis   = heute + timedelta(days=50)

resp = requests.get(
    f"https://api.football-data.org/v4/competitions/BL1/matches"
    f"?dateFrom={heute}&dateTo={bis}&status=SCHEDULED",
    headers=headers
)

matches = resp.json().get("matches", [])
print(f"Spiele gefunden: {len(matches)}\n")

for m in matches:
    print(f"{m['utcDate'][:10]}  {m['homeTeam']['name']} vs {m['awayTeam']['name']}")
