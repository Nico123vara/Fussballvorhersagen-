import psycopg2
import os

def get_connection():
    database_url = os.environ.get('DATABASE_URL', None)
    if database_url:
        return psycopg2.connect(database_url)
    return psycopg2.connect(
        host='localhost', port=5432,
        dbname='fussball', user='fussball', password='fussball_pw'
    )

conn = get_connection()
cur  = conn.cursor()

cur.execute("""
    CREATE TABLE IF NOT EXISTS models (
        name       TEXT PRIMARY KEY,
        data       BYTEA,
        created_at TIMESTAMP DEFAULT now()
    )
""")

conn.commit()
print("Tabelle 'models' erstellt!")
cur.close()
conn.close()
