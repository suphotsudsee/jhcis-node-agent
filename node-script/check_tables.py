import mysql.connector

conn = mysql.connector.connect(host='localhost', port=3333, user='root', password='123456', database='jhcisdb')
cursor = conn.cursor()

# Check for ovst table
cursor.execute("SHOW TABLES LIKE '%ovst%'")
tables = cursor.fetchall()
print('Tables matching ovst:')
for t in tables:
    print(f'  - {t[0]}')

# Check for visit related tables
cursor.execute("SHOW TABLES LIKE '%visit%'")
tables = cursor.fetchall()
print('\nTables matching visit:')
for t in tables[:10]:
    print(f'  - {t[0]}')

# Check for op related tables
cursor.execute("SHOW TABLES LIKE '%op%'")
tables = cursor.fetchall()
print('\nTables matching op (first 10):')
for t in tables[:10]:
    print(f'  - {t[0]}')

# Check for patient related tables
cursor.execute("SHOW TABLES LIKE '%patient%'")
tables = cursor.fetchall()
print('\nTables matching patient:')
for t in tables[:10]:
    print(f'  - {t[0]}')

conn.close()