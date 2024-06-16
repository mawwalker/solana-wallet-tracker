import json  
import websockets  
import asyncio
import traceback
from loguru import logger
import aiosqlite
import signal
from databases.database import add_subscription, get_subscriptions, remove_subscription, DATABASE_FILE
from utils.util import log2telegram_message
from config.conf import wss_config
  
class WalletSubscriptionManager:  
    def __init__(self):  
        self.subscriptions = {}  # 使用(user_id, wallet_address)作为键  
  
    async def subscribe_to_wallet_events(self, user_id, wallet_address, nickname, bot, restore=False):
        logger.info(f"Subscribing to wallet: {wallet_address} with nickname: {nickname}, for user {user_id}")  
        # 添加到数据库
        if not restore:
            await add_subscription(user_id, wallet_address, nickname)  
        websocket_url = wss_config['url']
        while True:  # Infinite loop to reconnect in case the connection drops
            try:
                async with websockets.connect(websocket_url) as websocket:  
                    subscribe_request = {  
                        "jsonrpc": "2.0",  
                        "id": 1,  
                        "method": "logsSubscribe",  
                        "params": [  
                            {"mentions": [wallet_address]},  
                            {"commitment": "finalized"}  
                        ]  
                    }
                    logger.info(f"Sending subscription request: {subscribe_request}")
                    await websocket.send(json.dumps(subscribe_request))  
                    logger.info(f"Subscribed to wallet: {wallet_address} for user {user_id}")
                    while True:  # Listen for incoming messages  
                        response = await websocket.recv()  
                        event_data = json.loads(response)
                        event_keys = list(event_data.keys())
                        if event_keys == ['jsonrpc', 'result', 'id']:
                            logger.info(f"Received subscription confirmation: {event_data}")
                            continue
                        
                        try:
                            logger.info(f"Received transaction for wallet: {wallet_address}, nickname: {nickname}.")
                            message = log2telegram_message(event_data, nickname)
                            if not message:
                                logger.info(f"Skipping error message: {event_data}")
                                continue
                        except Exception as e:
                            logger.info(f"Error when parsing log: {event_data}")
                            logger.error(f"Error parsing message: {e}")
                            traceback.print_exc()
                            continue
                        await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown", disable_web_page_preview=True)  
  
            except websockets.exceptions.ConnectionClosedError: 
                logger.info(f"Connection to {websocket_url} closed. Reconnecting...") 
                await asyncio.sleep(1)  # Wait a second before reconnecting
            # finally:
            #     self.subscriptions.pop((user_id, wallet_address), None)  
    async def is_subscribed(self, user_id, wallet_address):  
        # 检查是否已订阅  
        return (user_id, wallet_address) in self.subscriptions   
  
    def add_subscription_task(self, user_id, wallet_address, task):  
        # 将任务添加到订阅字典中  
        self.subscriptions[(user_id, wallet_address)] = task  
    async def unsubscribe_wallet(self, user_id, wallet_address):  
        # 从数据库中移除订阅  
        await remove_subscription(user_id, wallet_address)  
        # 取消任务  
        task = self.subscriptions.pop((user_id, wallet_address), None)  
        if task:  
            task.cancel()  
            await asyncio.gather(task, return_exceptions=True)

    async def restore_subscriptions(self, bot):  
        # 从数据库中获取所有订阅  
        async with aiosqlite.connect(DATABASE_FILE) as db:  
            async with db.execute("SELECT user_id, wallet_address, nickname FROM subscriptions") as cursor:  
                subscriptions = await cursor.fetchall()  
        logger.info(f"Restoring subscriptions from database: {subscriptions}")
        # 对每个订阅启动监听  
        for user_id, wallet_address, nickname in subscriptions:  
            if (user_id, wallet_address) not in self.subscriptions:  
                task = asyncio.create_task(  
                    self.subscribe_to_wallet_events(user_id, wallet_address, nickname, bot, restore=True)  
                )  
                self.add_subscription_task(user_id, wallet_address, task)
        logger.info(f"Restored subscriptions from database. Listening for subscription list: {self.subscriptions}")