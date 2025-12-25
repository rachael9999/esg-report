import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", 5432),
        user=os.getenv("PGUSER", "admin"),
        password=os.getenv("PGPASSWORD", "admin"),
        dbname=os.getenv("PGDATABASE", "postgres")
    )
