
import psycopg2, os
DATABASE_URL = os.environ.get("DATABASE_URL")
def get_conn():
    return psycopg2.connect(DATABASE_URL)
