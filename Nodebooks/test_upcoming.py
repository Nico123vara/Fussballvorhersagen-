import psycopg2
 
conn = psycopg2.connect(host='localhost', port=5432, dbname='fussball', user='fussball', password='fussball_pw')
cur  = conn.cursor()
 
cur.execute("SELECT c.code, COUNT(DISTINCT t.id) FROM teams t JOIN matches m ON (m.home_team_id = t.id) JOIN competitions c ON m.competition_id = c.id GROUP BY c.code")
print("Teams pro Liga:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} Teams")
 
cur.execute("SELECT c.code, COUNT(m.id) FROM matches m JOIN competitions c ON m.competition_id = c.id WHERE m.status = 'FINISHED' GROUP BY c.code")
print("\nSpiele pro Liga:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} Spiele")
 
cur.close()
conn.close()
 