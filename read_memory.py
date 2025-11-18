import sqlite3

# Connect to the database file
conn = sqlite3.connect("memory.db")
cur = conn.cursor()
cur.execute("SELECT * FROM memories")
rows = cur.fetchall()
for row in rows:
    print(row)