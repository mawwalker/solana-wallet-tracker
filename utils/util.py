import json
import datetime
import requests
from config.conf import http_api_config, gmgn_config
from loguru import logger

PUMP_FUN_ADDRESS = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

def parse_solana_transaction(transaction_data):  
    # Initialize the result dictionary  
    result = {  
        'trade_direction': None,  
        'who': None,  
        'token_amount': 0,  
        'token_id': None,  
        'sol_amount': 0  
    }  
  
    # Extract account keys  
    pre_token_balances = transaction_data['result']['meta']['preTokenBalances']  
    post_token_balances = transaction_data['result']['meta']['postTokenBalances']
    
    preBalances = transaction_data['result']['meta']['preBalances']
    postBalances = transaction_data['result']['meta']['postBalances']
    logMessages = transaction_data['result']['meta']['logMessages']
    pump_fun_str = f"Program {PUMP_FUN_ADDRESS} success"
    
    if pump_fun_str in logMessages:
        logger.info(f"Parsing pump.fun transaction")
        balance_change = [post - pre for pre, post in zip(preBalances, postBalances)][:4]
        result['who'] = post_token_balances[-1]['owner']
        result['token_id'] = post_token_balances[-1]['mint']
        if balance_change[0] > 0:
            # sell
            result['trade_direction'] = 'sell'
            
        else:
            # buy
            result['trade_direction'] = 'buy'
        result['token_amount'] = - balance_change[0]
        result['sol_amount'] = - balance_change[-1] / 1e9
        return result
        
  
    # Initialize dictionaries to track accountIndex and mint  
    pre_dict = {item['accountIndex']: item for item in pre_token_balances}  
    post_dict = {item['accountIndex']: item for item in post_token_balances}  
  
    token_amount_change = []  
    owner_times = {}
    
    sp_id = []
    # Calculate token amount changes  
    for account_index in set(pre_dict.keys()).union(post_dict.keys()):  
        pre_token = pre_dict.get(account_index, {'uiTokenAmount': {'uiAmount': 0}})  
        post_token = post_dict.get(account_index, {'uiTokenAmount': {'uiAmount': 0}})  
          
        owner = pre_token.get('owner', post_token.get('owner', ''))  
        pre_token_amount = pre_token['uiTokenAmount']['uiAmount']  
        post_token_amount = post_token['uiTokenAmount']['uiAmount']  
        
        if pre_token_amount == "None" or pre_token_amount is None:
            pre_token_amount = 0
        if post_token_amount == "None" or post_token_amount is None:
            post_token_amount = 0
  
        change = float(post_token_amount) - float(pre_token_amount)  
        if abs(change) > 1e-6:  
            token_amount_change.append({  
                'token_id': pre_token.get('mint', post_token.get('mint', '')),  
                'change': change,  
                'owner': owner,  
            })  
        owner_times[owner] = owner_times.get(owner, 0) + 1
        
        if owner_times[owner] == 2:
            sp_id.append(owner)
  
    # Determine the 'who' field, which appears only one time in token_amount_change  
    result['who'] = token_amount_change[-1]['owner']
  
    # 根据sp中的token数量变化，sol变化，确定交易方向、交易数量
    for change in token_amount_change:  
        token_id = change['token_id']
        change_amount = change['change']
        owner = change['owner']
        if owner in sp_id:
            if token_id == 'So11111111111111111111111111111111111111112':
                # sp卖出, 对应的是用户买入
                result['sol_amount'] = result['sol_amount'] + (- change_amount)
                # 保留3位小数
                result['sol_amount'] = round(result['sol_amount'], 3)
            else:
                result['token_id'] = token_id
                # 买入/卖出的token
                result['token_amount'] = result['token_amount'] + (- change_amount)
    
    if result['sol_amount'] < 0:
        result['trade_direction'] = 'buy'
    elif result['sol_amount'] > 0:
        result['trade_direction'] = 'sell'
    else:
        result['trade_direction'] = 'unknown'
  
    return result


def log2trasaction_parse(signature):
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
            {"encoding": "json", "maxSupportedTransactionVersion": 0}
        ]
    }
    response = requests.post(url, headers=headers, data=json.dumps(data))
    transaction_data = response.json()
    logger.info(f"original solana transaction info: {transaction_data}")
    
    return parse_solana_transaction(transaction_data)

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
    result['houlder_count'] = token_info['data']['token']['holder_count']
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

def log2telegram_message(log_dict, user_alias):
    signature = log_dict["params"]["result"]["value"]["signature"]
    
    error = log_dict['params']['result']['value']['err']
    if error is not None and error != "None":
        return None
    
    logger.info(f"signature: {signature}")
    transaction_data = log2trasaction_parse(signature)
    logger.info(f"parsed transaction_data: {transaction_data}")
    
    token_id = transaction_data['token_id']
    token_info = gmgn_info(token_id)
    
    burn_symbol = "✅" if token_info['burn_status'] else "❌"
    renounced_mint_symbol = "✅" if token_info['renounced_mint'] else "❌"
    renounced_freeze_account_symbol = "✅" if token_info['renounced_freeze_account'] else "❌"
    if transaction_data['trade_direction'] == 'buy':
        message = f"[{user_alias}](https://solscan.io/account/{transaction_data['who']}) New BUY: [solscan](https://solscan.io/tx/{signature}) \n" \
                  f"Swapped {abs(transaction_data['sol_amount'])} 💵 SOL for {abs(transaction_data['token_amount']):.3f} 💸 [{token_info['symbol']}]({token_info['name']}) \n" \
                  f"Security: Burn {burn_symbol} | Mint {renounced_mint_symbol} | Freeze {renounced_freeze_account_symbol} \n" \
                  f"MC: {format_number(token_info['market_cap'])} | Price: {token_info['price']} | HC: {token_info['houlder_count']} \n" \
                  f"🔗 Trade: [Trojan](https://t.me/solana_trojanbot?start=r-marcle253818-{token_id}) [GMGN](https://t.me/GMGN_sol_bot?start={token_id}) [Pepe](https://t.me/pepeboost_sol06_bot?start=ref_0nh46x_ca_{token_id}) \n" \
                  f"🔗 Chart: [GMGN](https://gmgn.ai/sol/token/{token_id}) \n" \
                  f"ca: `{token_id}`\n"
    elif transaction_data['trade_direction'] == 'sell':
        message = f"[{user_alias}](https://solscan.io/account/{transaction_data['who']}) New SELL: [solscan](https://solscan.io/tx/{signature}) \n" \
                  f"Swapped {abs(transaction_data['token_amount']):.3f} 💸 [{token_info['symbol']}({token_info['name']})] for {abs(transaction_data['sol_amount'])} 💵 SOL \n" \
                  f"Security: Burn {burn_symbol} | Mint {renounced_mint_symbol} | Freeze {renounced_freeze_account_symbol} \n" \
                  f"MC: {format_number(token_info['market_cap'])} | Price: {token_info['price']} | HC: {token_info['houlder_count']} \n" \
                  f"🔗 Trade: [Trojan](https://t.me/solana_trojanbot?start=r-marcle253818-{token_id}) | [GMGN](https://t.me/GMGN_sol_bot?start={token_id}) | [Pepe](https://t.me/pepeboost_sol06_bot?start=ref_0nh46x_ca_{token_id}) \n" \
                  f"🔗 Chart: [GMGN](https://gmgn.ai/sol/token/{token_id}) \n" \
                  f"ca: `{token_id}`\n"
    else:
        message = f"[{user_alias}](https://solscan.io/account/{transaction_data['who']}) New Transaction: [solscan](https://solscan.io/tx/{signature}) \n"
    
    logger.info(f"telegram message: {message}")
    return message

if __name__ == '__main__':
    json_dict = json.loads(open("transaction1.json").read())
    result = parse_solana_transaction(json_dict)
    print(result)