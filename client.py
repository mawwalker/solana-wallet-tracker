import requests  
  
API_BASE_URL = "http://localhost:8000"  
  
def subscribe_wallet(wallet_address, nickname):  
    response = requests.post(f"{API_BASE_URL}/subscribe/", json={"wallet_address": wallet_address, "nickname": nickname})  
    return response.json()  
  
def list_subscriptions():  
    response = requests.get(f"{API_BASE_URL}/subscriptions/")  
    return response.json()  
  
def unsubscribe_wallet(wallet_address):  
    response = requests.delete(f"{API_BASE_URL}/unsubscribe/{wallet_address}")  
    return response.json()  
  
# 测试订阅钱包  
wallet_address = "D58bE6pcm4fbuMdySpNwoB4SQYoTHSDdbvfiFi2j3n4K"  
nickname = "食神群友D58"  
# print("Subscribing wallet:")  
# print(subscribe_wallet(wallet_address, nickname))  
  

print("\nCurrent subscriptions:")  
print(list_subscriptions())  
  

print("\nUnsubscribing wallet:")  
print(unsubscribe_wallet(wallet_address))  
  

print("\nCurrent subscriptions after unsubscribe:")  
print(list_subscriptions())  
