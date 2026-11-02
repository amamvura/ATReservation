import os

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# open=False so FastAPI's lifespan controls startup/shutdown.
# check=... tests a connection before handing it out, which matters on Neon
# because idle connections get closed.
pool = ConnectionPool(
    DATABASE_URL,
    kwargs={"row_factory": dict_row},
    check=ConnectionPool.check_connection,
    open=False,
)