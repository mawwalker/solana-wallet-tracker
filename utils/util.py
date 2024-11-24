import json
import datetime
import time
import requests
from config.conf import http_api_config, gmgn_config, birdeye_key
from config.conf import (
    SOL,
    SOL_PROGRAM_ID,
    USDC,
    PUMP_PROGRAM_ADDRESS
)
from loguru import logger


def parse_transaction(transaction_data):
    """
    解析 Solana 交易信息，提取交易者、交易代币、代币数量、SOL 数量和交易方向。
    """
    result = {
        'trade_direction': None,
        'who': None,
        'token_amount': 0,
        'token_id': None,
        'sol_amount': 0
    }

    parsed_transaction = {
        # "owner": {
        #     "<token_id>": "<change_amount>"
        # },
        # ...
    }

    # 检查交易是否成功
    if transaction_data['result']['meta']['err'] is not None:
        logger.error("Transaction failed or has error.")
        return None

    # 获取交易签名者，即发起交易的钱包地址
    transaction = transaction_data['result']['transaction']
    message = transaction['message']
    account_keys = message['accountKeys']
    account_map = {}
    account_mint_map = {}
    signatures = transaction['signatures']

    logger.info(f"Parsing transaction, signatures: {signatures}")

    # 通常，第一个签名者是交易的发起者
    signer_pubkey = account_keys[0]['pubkey']
    result['who'] = signer_pubkey
    logger.info(f"Transaction initiated by: {signer_pubkey}")

    # 获取 token 余额变动
    pre_token_balances = transaction_data['result']['meta'].get('preTokenBalances', [])
    post_token_balances = transaction_data['result']['meta'].get('postTokenBalances', [])

    # 创建字典以便根据 accountIndex 快速查找
    pre_token_dict = {item['accountIndex']: item for item in pre_token_balances}
    post_token_dict = {item['accountIndex']: item for item in post_token_balances}

    # 遍历所有涉及的账户索引
    all_account_indexes = set(list(pre_token_dict.keys()) + list(post_token_dict.keys()))

    mint_token_address = ""

    for index in all_account_indexes:
        pre_token = next((item for item in pre_token_balances if item['accountIndex'] == index), None)
        post_token = next((item for item in post_token_balances if item['accountIndex'] == index), None)

        # 如果某个账户只有前余额或后余额，设置默认值
        if not pre_token:
            pre_token = {
                'mint': post_token['mint'],
                "owner": post_token['owner'],
                'uiTokenAmount': {'uiAmount': 0}
            }
        if not post_token:
            post_token = {
                'mint': pre_token['mint'],
                "owner": pre_token['owner'],
                'uiTokenAmount': {'uiAmount': 0}
            }

        owner = post_token['owner']
        if 'accountIndex' in post_token:
            account_index = post_token['accountIndex']
            token_account = account_keys[account_index]['pubkey']
            account_mint_map[token_account] = post_token['mint']
            account_map[token_account] = owner

        # 获取代币 mint
        token_address = pre_token['mint']
        if token_address != SOL and mint_token_address == "":
            mint_token_address = token_address
        pre_amount = float(pre_token['uiTokenAmount']['uiAmount'] or 0)
        post_amount = float(post_token['uiTokenAmount']['uiAmount'] or 0)

        # 过滤都是0的
        if pre_amount < 1e-5 and post_amount < 1e-5:
            continue

        amount_change = post_amount - pre_amount
        logger.info(f"Token: {token_address}, Amount change: {amount_change}, owner: {owner}")
        if owner not in parsed_transaction:
            parsed_transaction[owner] = {
                token_address: amount_change
            }
        else:
            parsed_transaction[owner][token_address] = amount_change

    logger.info(f"Parsed transaction: {parsed_transaction}")
    logger.info("Calculating trade direction and token amount...")

    inner_instructions = transaction_data['result']['meta'].get('innerInstructions', [])
    instructions = []
    for instruction in inner_instructions:
        instructions += instruction['instructions']

    # 判断是否有pump的instruction
    for instruction in instructions:
        if instruction['programId'] == PUMP_PROGRAM_ADDRESS:
            data_string = instruction['data']
            pump_fun_result = parse_pump_fun(data_string)
            if pump_fun_result:
                result['token_amount'] = float(pump_fun_result['tokenAmount']) / 1e6
                result['sol_amount'] = float(pump_fun_result['solAmount']) / 1e9
                result['trade_direction'] = 'buy' if pump_fun_result['isBuy'] else 'sell'
                result['token_id'] = mint_token_address
                return result

    program_instructions = transaction_data['result']['transaction']['message']['instructions']
    instructions += program_instructions

    # 解析 innerInstructions
    transfer_instructions = []

    close_account_queue = []
    for inner_instr in instructions:
        if 'parsed' in inner_instr:
            parsed_info = inner_instr['parsed']['info']
            # 增加一个例外：如果前面是closeAccount 类型，则接下来的transfer指令不记录，这个transfer是关闭账户的余额转移
            if inner_instr['parsed']['type'] == 'closeAccount':
                account_map[parsed_info['account']] = parsed_info['owner']
                close_account_queue.append(parsed_info)
                continue

            if inner_instr['parsed']['type'] == 'create':
                account_map[parsed_info['account']] = parsed_info['wallet']

            if inner_instr['parsed']['type'] == 'transfer' and len(close_account_queue) == 0 and inner_instr['program'] in ['spl-token', 'system']:
                # # 根据账户映射，找到实际账户所有者，destination, source都要转换
                # destination = account_map.get(parsed_info['destination'], parsed_info['destination'])
                # source = account_map.get(parsed_info['source'], parsed_info['source'])
                # inner_instr['parsed']['info']['destination'] = destination
                # inner_instr['parsed']['info']['source'] = source
                transfer_instructions.append(inner_instr)
            else:
                close_account_queue.pop(0) if len(close_account_queue) > 0 else None

    # 置换账户映射, 添加account mint 映射
    for transfer in transfer_instructions:
        transfer_info = transfer['parsed']['info']
        source = transfer_info['source']
        destination = transfer_info['destination']

        if source in account_mint_map:
            transfer['parsed']['info']['mint'] = account_mint_map[source]
        if destination in account_mint_map:
            transfer['parsed']['info']['mint'] = account_mint_map[destination]
        if transfer['program'] == 'system' and transfer['programId'] == SOL_PROGRAM_ID:
            transfer['parsed']['info']['mint'] = SOL

        if source in account_map:
            transfer_info['source'] = account_map[source]
        if destination in account_map:
            transfer_info['destination'] = account_map[destination]

    transfer_fee = transaction_data['result']['meta'].get('fee', 0) / 1e9
    logger.info(f"Transfer fee: {transfer_fee}")
    logger.info(f"Transfer instructions: {transfer_instructions} \n\n Account map: {account_map}")

    relevent_accounts = set(list(account_map.keys()) + list(account_map.values()))

    # 最后，计算交易者的代币变化情况
    for transfer in transfer_instructions:
        transfer_info = transfer['parsed']['info']
        source = transfer_info['source']
        destination = transfer_info['destination']
        mint = transfer_info['mint']
        if source not in relevent_accounts or destination not in relevent_accounts:
            continue

        if mint == SOL:
            if 'lamports' in transfer_info:
                amount = int(transfer_info['lamports']) / 1e9
            else:
                amount = int(transfer_info['amount']) / 1e9
            if signer_pubkey == source:
                result['sol_amount'] -= amount
            else:
                result['sol_amount'] += amount
        else:
            amount = int(transfer_info['amount']) / 1e6
            if signer_pubkey == source:
                result['token_amount'] -= amount
            else:
                result['token_amount'] += amount

    if result['token_amount'] < 0:
        result['trade_direction'] = 'sell'
    elif result['token_amount'] > 0:
        result['trade_direction'] = 'buy'
    else:
        result['trade_direction'] = 'unknown'

    result['token_id'] = mint_token_address

    return result


def parse_pump_fun(data_string):
    url = "http://localhost:3000/decode"
    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "inscuction_data": data_string
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))
    if response.status_code != 200:
        return None
    
    # Response JSON: {'mint': 'AZBS3YHNuneocBDeEMdkGnVG3g2cLRxsjVy4hiwsEhat', 'solAmount': '10460498188', 'tokenAmount': '58175489836176', 'isBuy': False, 'user': '3tc4BVAdzjr1JpeZu6NAjLHyp4kK3iic7TexMBYGJ4Xk', 'timestamp': '1732397328', 'virtualSolReserves': '71028646376', 'virtualTokenReserves': '453197430552661', 'realSolReserves': '41028646376', 'realTokenReserves': '173297430552661'}

    return response.json()


def get_transaction(signature):
    # signature = log_dict["params"]["result"]["value"]["signature"]
    url = http_api_config['url']
    if 'ak' in http_api_config:
        headers = {
            "Content-Type": "application/json",
            http_api_config['ak']['header']: http_api_config['ak']['value']
        }
    else:
        headers = {
            "Content-Type": "application/json"
        }
    data = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}
        ]
    }
    for i in range(3):
        # 重试5次
        logger.info(f"invoke getTransaction: {i}, signature: {signature}, url: {url}, headers: {headers}, data: {data}")
        response = requests.post(url, headers=headers, data=json.dumps(data))
        logger.info(f"response: {response.text}")
        if response.status_code == 200 and response.json().get('result', None) is not None:
            break
        time.sleep(1)
    # response = requests.post(url, headers=headers, data=json.dumps(data))
    transaction_data = response.json()
    logger.info(f"original solana transaction info: {transaction_data}")

    return transaction_data


def format_price(price):
    # 将浮点数转换为字符串，并找到第一个非零数字的位置
    price_str = "{:.10e}".format(price)
    parts = price_str.split("e")
    mantissa = parts[0].rstrip('0')
    exponent = int(parts[1])

    if exponent < -4:
        # 保留4位有效数字，并格式化前面的0
        significant_digits = mantissa.replace('.', '')[:4]
        leading_zeros = abs(exponent) - 1
        formatted_price = f"0.0{{{leading_zeros}}}{significant_digits}"
    else:
        # 直接格式化为4位有效数字
        formatted_price = "{:.4g}".format(price)

    return formatted_price


def format_token_num(num):
    ''' 格式化token数字，增加逗号显示
    例如： 1000000 -> 1,000,000
    '''
    # 先取三位小数
    num = round(abs(num), 3)

    return "{:,}".format(num)


def format_number(num):
    """
    将浮点数格式化为一般数字、千(K)、百万(M)、十亿(B)的形式

    :param num: 浮点数
    :return: 格式化后的字符串
    """
    if num < 1_000:
        return f"{num:.0f}"  # 不保留小数
    elif num < 1_000_000:
        return f"{num / 1_000:.2f}K"
    elif num < 1_000_000_000:
        return f"{num / 1_000_000:.2f}M"
    else:
        return f"{num / 1_000_000_000:.2f}B"


def gmgn_info(token_id, chain="sol"):
    gmgn_info_url = gmgn_config['token_info'][chain]['url']
    url = f"{gmgn_info_url}/{token_id}"
    headers = {
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    token_info = response.json()
    logger.info(f"gmgn original token info: {token_info}")
    result = {}
    result['symbol'] = token_info['data']['token']['symbol']
    result['name'] = token_info['data']['token']['name']
    result['launchpad'] = token_info['data']['token'].get('launchpad', None)
    result['market_cap'] = token_info['data']['token']['market_cap']
    result['holder_count'] = token_info['data']['token']['holder_count']
    open_timestamp = token_info['data']['token']['open_timestamp']
    open_time_str = datetime.datetime.fromtimestamp(open_timestamp).strftime("%Y-%m-%d %H:%M:%S") if open_timestamp else ""
    result['open_time'] = open_time_str
    socials = token_info['data']['token']['social_links']
    top_10_holder_rate = token_info['data']['token']['top_10_holder_rate']
    renounced_mint = token_info['data']['token']['renounced_mint']
    renounced_freeze_account = token_info['data']['token']['renounced_freeze_account']
    burn_status = token_info['data']['token']['burn_status']

    result['socials'] = socials
    result['top_10_holder_rate'] = top_10_holder_rate
    result['renounced_mint'] = renounced_mint
    result['renounced_freeze_account'] = renounced_freeze_account
    result['burn_status'] = burn_status
    result['price'] = format_price(token_info['data']['token']['price'])

    return result


def birdeye_tokeninfo(token_address):
    # {
    #     "data": {
    #         "address": "So11111111111111111111111111111111111111112",
    #         "symbol": "SOL",
    #         "name": "Wrapped SOL",
    #         "decimals": 9,
    #         "extensions": {
    #         "coingecko_id": "solana",
    #         "website": "https://solana.com/",
    #         "twitter": "https://twitter.com/solana",
    #         "discord": "https://discordapp.com/invite/pquxPsq",
    #         "medium": "https://medium.com/solana-labs"
    #         },
    #         "logo_uri": "https://img.fotofolio.xyz/?url=https%3A%2F%2Fraw.githubusercontent.com%2Fsolana-labs%2Ftoken-list%2Fmain%2Fassets%2Fmainnet%2FSo11111111111111111111111111111111111111112%2Flogo.png"
    #     },
    #     "success": true
    #     }

    url = f"https://public-api.birdeye.so/defi/v3/token/meta-data/single?address={token_address}"
    headers = {
        "accept": "application/json",
        "X-API-KEY": birdeye_key
    }
    for i in range(5):
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.json().get('data', None) is not None:
            break
        else:
            logger.info(f"birdeye token info failed, retrying... {i}, response: {response.text}")
        time.sleep(1)
    results = response.json()
    logger.info(f"birdeye token info: {results}")
    if 'data' not in results or results['data'] is None:
        return {
            "symbol": "Unknown",
            "name": "Unknown",
        }
    return results['data']


def birdeye_price(token_address):
    url = f"https://public-api.birdeye.so/defi/v3/token/market-data?address={token_address}"

    headers = {
        "accept": "application/json",
        "X-API-KEY": birdeye_key
    }

    for i in range(5):
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.json().get('data', None) is not None:
            break
        else:
            logger.info(f"birdeye price failed, retrying... {i}, response: {response.text}")
        time.sleep(1)
    results = response.json()
    # {
    #     "data": {
    #         "address": "So11111111111111111111111111111111111111112",
    #         "price": 234.49216712475877,
    #         "liquidity": 23893149511.698532,
    #         "supply": 588673669.8762643,
    #         "marketcap": 138039364578.57004,
    #         "circulating_supply": 474627553.5539518,
    #         "circulating_marketcap": 111296443609.98866
    #     },
    #     "success": true
    #     }
    if 'data' not in results or results['data'] is None:
        return {
            "price": 0,
            "marketcap": 0,
            "holder_count": 0
        }
    return results['data']


def birdeye(token_address):
    if token_address == '':
        return None
    token_info = birdeye_tokeninfo(token_address)
    if not token_info:
        return None
    price_info = birdeye_price(token_address)
    token_info.update(price_info)
    return token_info


# def log2telegram_message_gmgn(log_dict, user_alias):
#     signature = log_dict["params"]["result"]["value"]["signature"]

#     error = log_dict['params']['result']['value']['err']
#     if error is not None and error != "None":
#         return None

#     logger.info(f"signature: {signature}")
#     transaction_data = log2trasaction_parse(signature)
#     logger.info(f"parsed transaction_data: {transaction_data}")

#     token_id = transaction_data['token_id']
#     # token_info = gmgn_info(token_id)
#     token_info = birdeye_info(token_id)

#     burn_symbol = "✅" if token_info['burn_status'] else "❌"
#     renounced_mint_symbol = "✅" if token_info['renounced_mint'] else "❌"
#     renounced_freeze_account_symbol = "✅" if token_info['renounced_freeze_account'] else "❌"
#     if transaction_data['trade_direction'] == 'buy':
#         message = f"[{user_alias}](https://solscan.io/account/{transaction_data['who']}) New BUY: [solscan](https://solscan.io/tx/{signature}) \n" \
#                   f"Swapped {abs(transaction_data['sol_amount'])} 💵 SOL for {abs(transaction_data['token_amount']):.3f} 💸 [{token_info['symbol']}]({token_info['name']}) \n" \
#                   f"Security: Burn {burn_symbol} | Mint {renounced_mint_symbol} | Freeze {renounced_freeze_account_symbol} \n" \
#                   f"MC: {format_number(token_info['market_cap'])} | Price: {token_info['price']} | HC: {token_info['holder_count']} \n" \
#                   f"🔗 Trade: [Trojan](https://t.me/solana_trojanbot?start=r-marcle253818-{token_id}) [GMGN](https://t.me/GMGN_sol_bot?start={token_id}) [Pepe](https://t.me/pepeboost_sol06_bot?start=ref_0nh46x_ca_{token_id}) \n" \
#                   f"🔗 Chart: [GMGN](https://gmgn.ai/sol/token/{token_id}) \n" \
#                   f"ca: `{token_id}`\n"
#     elif transaction_data['trade_direction'] == 'sell':
#         message = f"[{user_alias}](https://solscan.io/account/{transaction_data['who']}) New SELL: [solscan](https://solscan.io/tx/{signature}) \n" \
#                   f"Swapped {abs(trbirdeye_info

def log2telegram_message(log_dict, subscription_dict):
    signature = log_dict["params"]["result"]["value"]["signature"]

    error = log_dict['params']['result']['value']['err']
    if error is not None and error != "None":
        return None

    logger.info(f"signature: {signature}")
    # transaction_data = log2trasaction_parse(signature)
    transaction_data = parse_transaction(get_transaction(signature))
    logger.info(f"parsed transaction_data: {transaction_data}")

    wallet_address = transaction_data['who']

    user_id, nickname, _ = subscription_dict.get(wallet_address, (None, None, None))

    token_id = transaction_data['token_id']

    token_info = birdeye(token_id)
    if not token_info:
        return None

    trade_direction_symbol = "💸"
    if transaction_data['trade_direction'] == "buy":
        trade_direction_symbol = "BUY🟩"
    elif transaction_data['trade_direction'] == "sell":
        trade_direction_symbol = "SELL🟥"

    message = f"{trade_direction_symbol} [{nickname}](https://solscan.io/account/{wallet_address}): [solscan](https://solscan.io/tx/{signature}) \n" \
              f"Swapped {abs(transaction_data['sol_amount'])} **SOL** for {format_token_num(transaction_data['token_amount'])} 💸 **[{token_info['symbol']}({token_info['name']})](https://gmgn.ai/sol/token/{token_id})** \n" \
              f"MC: {format_number(token_info['marketcap'])} | Price: {format_price(token_info['price'])} \n" \
              f"🔗 Trade: [Trojan](https://t.me/solana_trojanbot?start=r-marcle253818-{token_id}) | [GMGN](https://t.me/GMGN_sol_bot?start={token_id}) | [Pepe](https://t.me/pepeboost_sol06_bot?start=ref_0nh46x_ca_{token_id}) \n" \
              f"🔗 Chart: [GMGN](https://gmgn.ai/sol/token/{token_id}) \n" \
              f"ca: `{token_id}`\n"
    return message
