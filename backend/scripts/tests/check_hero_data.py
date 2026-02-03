import sqlite3
conn = sqlite3.connect('keepgaining.db')
cursor = conn.cursor()
cursor.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(*) FROM candle_data WHERE symbol = 'NSE:HEROMOTOCO-EQ'")
print('Hero data:', cursor.fetchone())
cursor.execute("SELECT DISTINCT symbol FROM candle_data WHERE symbol LIKE '%HERO%'")
print('Hero symbols:', [row[0] for row in cursor.fetchall()])
conn.close()
