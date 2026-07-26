import json
import psycopg2
import os

# Test 1: JSON lesen
print("Test 1: JSON lesen...")
with open('data/teams_bl1_2023.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
print(f"  Teams in Datei: {len(data['teams'])}")
print(f"  Erstes Team: {data['teams'][0]['name']}")

# Test 2: DB verbinden
print("\nTest 2: DB verbinden...")
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur  = conn.cursor()
print("  Verbunden!")

# Test 3: Ein Team schreiben
print("\nTest 3: Ein Team schreiben...")
t = data['teams'][0]
cur.execute("""
    INSERT INTO teams (id, name, short_name, tla, crest_url)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
""", (t['id'], t['name'], t.get('shortName'), t.get('tla'), t.get('crest')))
conn.commit()
print(f"  {t['name']} gespeichert!")

cur.close()
conn.close()
print("\nFertig!")
