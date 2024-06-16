from telegram import Update, Bot
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes, Updater
import asyncio 
from loguru import logger
import threading 
from wallet_subscription_manager import WalletSubscriptionManager  
from databases.database import create_tables, get_subscriptions
from config.conf import bot_token
  
TELEGRAM_TOKEN = bot_token
ALLOWED_USER_IDS = [6573081218]
  
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  
    logger.info(f"User {update.effective_user.id} started the bot.")
    if update.effective_user.id in ALLOWED_USER_IDS:  
        await update.message.reply_text('Welcome to the Wallet Subscription Bot! Use /add, /list, /rm commands.')  
    else:
        await update.message.reply_text('You are not allowed to use this command.')
  
async def add_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  
    logger.info(f"User {update.effective_user.id} entering add_wallet.")
    if update.effective_user.id in ALLOWED_USER_IDS:  
        args = context.args  
        if len(args) == 2:  
            wallet_address, nickname = args  
            if not await manager.is_subscribed(update.effective_user.id, wallet_address):  
                task = asyncio.create_task(manager.subscribe_to_wallet_events(update.effective_user.id, wallet_address, nickname, context.bot))  
                manager.add_subscription_task(update.effective_user.id, wallet_address, task)  
                await update.message.reply_text(f'Subscribed to wallet: {wallet_address} with nickname: {nickname}')  
            else:  
                await update.message.reply_text('Wallet is already subscribed.') 
        else:  
            await update.message.reply_text('Usage: /add <wallet_address> <nickname>')  
    else:
        await update.message.reply_text('You are not allowed to use this command.')
  
async def list_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
    logger.info(f"User {update.effective_user.id} entering list_wallets.")
    if update.effective_user.id in ALLOWED_USER_IDS:  
        subscriptions = await get_subscriptions(update.effective_user.id)  
        message = '\n'.join([f'{nickname}: {wallet_address}' for wallet_address, nickname in subscriptions])  
        await update.message.reply_text(f'Current subscriptions:\n{message}' if message else 'No subscriptions found.')
    else:
        await update.message.reply_text('You are not allowed to use this command.')
  
async def remove_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: 
    logger.info(f"User {update.effective_user.id} removed a wallet.") 
    if update.effective_user.id in ALLOWED_USER_IDS:  
        wallet_address = context.args[0] if context.args else None  
        if wallet_address:  
            await manager.unsubscribe_wallet(update.effective_user.id, wallet_address)  
            await update.message.reply_text(f'Unsubscribed from wallet: {wallet_address}')  
        else:  
            await update.message.reply_text('Usage: /rm <wallet_address>')  
    else:
        await update.message.reply_text('You are not allowed to use this command.')


def run_asyncio_coroutine(coroutine, loop):  
    asyncio.set_event_loop(loop)  
    loop.run_until_complete(coroutine)  
  
def main() -> None:  
    # 创建事件循环  
    loop = asyncio.new_event_loop()  
    asyncio.set_event_loop(loop)  
  
    # 在事件循环中运行 create_tables()  
    loop.run_until_complete(create_tables())  
  
    logger.info("Table created, starting bot")  
  
    # 创建 Application 实例并添加处理程序  
    application = Application.builder().token(TELEGRAM_TOKEN).build()  
    application.add_handler(CommandHandler("start", start))  
    application.add_handler(CommandHandler("add", add_wallet))  
    application.add_handler(CommandHandler("list", list_wallets))  
    application.add_handler(CommandHandler("rm", remove_wallet))  
    
    commands = [BotCommand(command="/start", description="Start the bot"),  
                BotCommand(command="/add", description="/add <wallet_address> <nickname> to subscribe to a wallet"),  
                BotCommand(command="/list", description="List wallet subscriptions"),  
                BotCommand(command="/rm", description="/rm <wallet_address> to unsubscribe from a wallet")]
    result = loop.run_until_complete(application.bot.set_my_commands(commands))
    logger.info(f"Commands set: {result}")
  
    # 在主线程的事件循环中启动 restore_subscriptions()  
    loop.run_until_complete(manager.restore_subscriptions(application.bot))  
  
    # 在子线程中运行 bot 的事件循环  
    threading.Thread(target=run_asyncio_coroutine, args=(application.run_polling(), loop)).start()   
  
if __name__ == '__main__':  
    manager = WalletSubscriptionManager()  
    main()   
