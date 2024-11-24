import yaml
import os
import dotenv


dotenv.load_dotenv()


def load_config():
    with open(os.path.join(os.path.dirname(__file__), 'config.yaml')) as f:
        return yaml.safe_load(f)


configs = load_config()


bot_token = os.getenv("BOT_TOKEN", configs['bot_token'])


wss_config = {"url": os.getenv("WSS_URL", configs['wss']["url"])}


http_api_config = {
    "url": os.getenv("HTTP_API_URL", configs['http']["url"]),
    # "ak": {
    #     "header": os.getenv("HTTP_API_AK_HEADER", None),
    #     "value": os.getenv("HTTP_API_AK_VALUE", None)
    # }
}

HTTP_API_AK_HEADER = os.getenv("HTTP_API_AK_HEADER", None)
HTTP_API_AK_VALUE = os.getenv("HTTP_API_AK_VALUE", None)
if HTTP_API_AK_HEADER and HTTP_API_AK_VALUE:
    http_api_config["ak"] = {
        "header": HTTP_API_AK_HEADER,
        "value": HTTP_API_AK_VALUE
    }


gmgn_config = configs['gmgn']


birdeye_key = os.getenv("BIRDEYE_KEY", None)

PUMP_PROGRAM_ADDRESS = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SOL = "So11111111111111111111111111111111111111112"
SOL_PROGRAM_ID = "11111111111111111111111111111111"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

RAYDIUM_ADDRESSES = ["CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
                     "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
                     "5quBtoiQqxF9Jv6KYKctB59NT3gtJD2Y65kdnB1Uev3h",
                     "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
                     ]

JUPITER_ADDRESSES = ["JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"]