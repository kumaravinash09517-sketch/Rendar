import os
import time
import json
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
USERS_FILE = "users.json"
MESSAGES_FILE = "messages.json"
BLOCKED_FILE = "blocked.json"

def load_data(file, default):
    if os.path.exists(file):
        try:
            with open(file, "r") as f:
                return json.load(f)
        except:
            return default
    return default

def save_data(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

users = load_data(USERS_FILE, {})
messages = load_data(MESSAGES_FILE, [])
blocked_users = load_data(BLOCKED_FILE, [])

# आपका टोकन यहाँ सीधे फिक्स कर दिया गया है
TELEGRAM_TOKEN = "8839310378:AAHyFTE4SFwJ5AxFdRFIG1f_w2detVfNXBU"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# बोट कनेक्शन चेक करना
res = requests.get(f"{BASE_URL}/getMe").json()
if res.get("ok"):
    print(f"[✔] Successfully Connected to Telegram Bot: @{res['result']['username']}")
else:
    print("[✘] Telegram Token Error!")

@app.route('/')
def home():
    return "Hello Sir - Global Chat Server is Live!"

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    uid = data.get("user_id")
    name = data.get("name")
    if uid in blocked_users:
        return jsonify({"status": "blocked"}), 403
    users[uid] = {"name": name, "time": time.time()}
    save_data(USERS_FILE, users)
    return jsonify({"status": "success", "users": users})

@app.route('/send', methods=['POST'])
def send():
    data = request.json
    sender = data.get("sender")
    receiver = data.get("receiver")
    text = data.get("text")
    
    if sender in blocked_users:
        return jsonify({"status": "blocked"}), 403
        
    msg = {"sender": sender, "receiver": receiver, "text": text, "time": time.time()}
    messages.append(msg)
    save_data(MESSAGES_FILE, messages)
    
    return jsonify({"status": "sent"})

@app.route('/get', methods=['GET'])
def get():
    return jsonify({"messages": messages, "users": users})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
