import aiosqlite
from loguru import logger
DATABASE_FILE = "data/subscriptions.db"


async def create_tables():
    logger.info("Creating tables...")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                nickname TEXT NOT NULL,
                UNIQUE(user_id, wallet_address)
            )
        ''')
        await db.commit()


async def add_subscription(user_id, wallet_address, nickname):
    logger.info(f"Adding subscription for user {user_id} to wallet {wallet_address} with nickname {nickname}")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, wallet_address, nickname) VALUES (?, ?, ?)",
            (user_id, wallet_address, nickname)
        )
        await db.commit()


async def get_subscriptions(user_id):
    logger.info(f"Getting subscriptions for user {user_id}")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        async with db.execute("SELECT wallet_address, nickname FROM subscriptions WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchall()


async def remove_subscription(user_id, wallet_address):
    logger.info(f"Removing subscription for user {user_id} from wallet {wallet_address}")
    async with aiosqlite.connect(DATABASE_FILE) as db:
        await db.execute("DELETE FROM subscriptions WHERE user_id = ? AND wallet_address = ?", (user_id, wallet_address))
        await db.commit()
