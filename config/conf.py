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
    "ak": {
        "header": os.getenv("HTTP_API_AK_HEADER", configs['http']["ak"]["header"]),
        "value": os.getenv("HTTP_API_AK_VALUE", configs['http']["ak"]["value"])
    }
}

gmgn_config = configs['gmgn']