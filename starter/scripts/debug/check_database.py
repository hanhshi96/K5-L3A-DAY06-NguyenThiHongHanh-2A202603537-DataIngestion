import os
import psycopg
from dotenv import load_dotenv

load_dotenv(".env", override=True)

database_url = os.getenv("DATABASE_URL")

with psycopg.connect(database_url) as conn:
    with conn.cursor() as cur:

        cur.execute("""
            SELECT format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = to_regclass('lab06_chunks')
              AND attname = 'embedding'
              AND NOT attisdropped
        """)

        result = cur.fetchone()

        print("EMBEDDING COLUMN TYPE:")
        print(result[0] if result else "TABLE/COLUMN NOT FOUND")

        cur.execute("""
            SELECT strategy, COUNT(*)
            FROM lab06_chunks
            GROUP BY strategy
            ORDER BY strategy
        """)

        print("\nEXISTING RECORDS:")
        rows = cur.fetchall()

        if rows:
            for row in rows:
                print(row)
        else:
            print("No records yet.")

print("\nDATABASE INSPECTION COMPLETED")
