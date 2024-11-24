import json
import websockets
from websockets.asyncio.client import connect as ws_connect
import asyncio
import traceback
from loguru import logger
import aiosqlite
from databases.database import add_subscription, remove_subscription, DATABASE_FILE
from utils.util import log2telegram_message
from config.conf import wss_config


class WalletSubscriptionManager:
    def __init__(self):
        self.subscriptions = {}  # 使用(wallet_address)作为键，值为(user_id, nickname, subscription_id)
        self.websocket = None
        self.bot = None
        self.websocket_connected = asyncio.Event()

    async def connect_websocket(self):
        '''
        '''
        websocket_url = wss_config['url']
        logger.info(f"Connecting to WebSocket at {websocket_url}")
        while True:
            try:
                self.websocket = await ws_connect(websocket_url)
                logger.info(f"Connected to WebSocket at {websocket_url}")
                self.websocket_connected.set()
                await self.listen_to_websocket()
            except websockets.exceptions.ConnectionClosedError:
                logger.info(f"Connection to {websocket_url} closed. Reconnecting...")
                await asyncio.sleep(1)

    async def listen_to_websocket(self):
        while True:
            response = await self.websocket.recv()
            logger.info(f"Received message: {response}")
            event_data = json.loads(response)
            event_keys = list(event_data.keys())
            if event_keys == ['jsonrpc', 'result', 'id']:
                # logger.info(f"Received subscription confirmation: {event_data}")
                subscription_id = event_data['result']
                for wallet_address, (user_id, nickname, sub_id) in self.subscriptions.items():
                    if sub_id is None:
                        self.subscriptions[wallet_address] = (user_id, nickname, subscription_id)
                        break
                continue

            try:
                # wallet_address = event_data['params']['result']['value']['account']
                # user_id, nickname, _ = self.subscriptions.get(wallet_address, (None, None, None))
                # logger.info(f"Received transaction: {event_data}; \n Subscriptions: {self.subscriptions}")
                message = log2telegram_message(event_data, self.subscriptions)
                if not message:
                    logger.info(f"Skipping error message: {event_data}")
                    continue
                await self.bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown", disable_web_page_preview=True)
            except Exception as e:
                logger.info(f"Error when parsing log: {event_data}")
                logger.error(f"Error parsing message: {e}")
                traceback.print_exc()
                continue

    async def subscribe_to_wallet(self, user_id, wallet_address, nickname, bot, restore=False):
        self.bot = bot
        logger.info(f"Subscribing to wallet: {wallet_address} with nickname: {nickname}, for user {user_id}")
        if not restore:
            await add_subscription(user_id, wallet_address, nickname)
        self.subscriptions[wallet_address] = (user_id, nickname, None)

        subscribe_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [wallet_address]},
                {"commitment": "confirmed"}
            ]
        }
        await self.websocket.send(json.dumps(subscribe_request))
        logger.info(f"Sent subscription request for wallet: {wallet_address}")

    async def unsubscribe_wallet(self, user_id, wallet_address):
        logger.info(f"Unsubscribing from wallet: {wallet_address} for user {user_id}")
        await remove_subscription(user_id, wallet_address)
        _, _, subscription_id = self.subscriptions.get(wallet_address, (None, None, None))
        if subscription_id:
            unsubscribe_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsUnsubscribe",
                "params": [subscription_id]
            }
            await self.websocket.send(json.dumps(unsubscribe_request))
            logger.info(f"Sent unsubscription request for wallet: {wallet_address}")
        self.subscriptions.pop(wallet_address, None)

    async def restore_subscriptions(self, bot):
        self.bot = bot
        async with aiosqlite.connect(DATABASE_FILE) as db:
            async with db.execute("SELECT user_id, wallet_address, nickname FROM subscriptions") as cursor:
                subscriptions = await cursor.fetchall()
        logger.info(f"Restoring subscriptions from database: {subscriptions}")
        for user_id, wallet_address, nickname in subscriptions:
            if wallet_address not in self.subscriptions:
                await self.subscribe_to_wallet(user_id, wallet_address, nickname, bot, restore=True)
        logger.info(f"Restored subscriptions from database. Listening for subscription list: {self.subscriptions}")

    async def handle_external_message(self, data):
        action = data.get('action')
        user_id = data.get('user_id')
        wallet_address = data.get('wallet_address')
        nickname = data.get('nickname')
        if action == 'subscribe':
            await self.subscribe_to_wallet(user_id, wallet_address, nickname, self.bot)
        elif action == 'unsubscribe':
            await self.unsubscribe_wallet(user_id, wallet_address)

    async def is_subscribed(self, user_id, wallet_address):
        return wallet_address in self.subscriptions

    async def start(self, bot):
        self.bot = bot
        await self.restore_subscriptions(bot)
        await self.connect_websocket()
