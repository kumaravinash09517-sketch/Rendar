import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests

app = Flask(__name__)

# SQLite Database Setup - चैट और यूजर डेटा सुरक्षित रखने के लिए
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

TELEGRAM_BOT_TOKEN = "8970811998:AAG1pkIq7zWS1fZlnjN6vTMBviZ4xWKKtOc"  # आपका टेलीग्राम बॉट टोकन
ADMIN_CHAT_ID = "YOUR_ADMIN_CHAT_ID"     # यहाँ अपनी टेलीग्राम चैट आईडी डालें

# 1. User Model - यूजर्स और उनके ब्लॉक स्टेटस के लिए
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)
    block_type = db.Column(db.String(20), default="none") # permanent / temporary

# 2. Message Model - परमानेंट चैट हिस्ट्री सेव करने के लिए
class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.String(50), nullable=False)
    receiver_id = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=True)
    media_url = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_read = db.Column(db.Boolean, default=False)

with app.app_context():
    db.create_all()

# 🌐 नया होमपेज राउट (ताकि ब्राउज़र में खोलने पर 404 न आए)
@app.route('/', methods=['GET'])
def home():
    return "Hello Sir Backend is Live and Running successfully!"

# यूजर रजिस्ट्रेशन और लिस्ट अपडेट राउट
@app.route('/register', methods=['POST'])
def register_user():
    data = request.json
    uid = data.get('user_id')
    name = data.get('name')
    
    user = User.query.filter_by(user_id=uid).first()
    if not user:
        new_user = User(user_id=uid, name=name)
        db.session.add(new_user)
        db.session.commit()
        # जैसे ही कोई नया यूजर रजिस्टर हो, टेलीग्राम पर अलर्ट जाए
        if ADMIN_CHAT_ID != "YOUR_ADMIN_CHAT_ID":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                "chat_id": ADMIN_CHAT_ID,
                "text": f"👤 **नया यूजर रजिस्टर्ड हुआ!**\nनाम: {name}\nयूजर आईडी: {uid}"
            })
    return jsonify({"status": "registered"})

# मैसेज भेजने और टेलीग्राम पर फॉरवर्ड करने का राउट
@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    sender = data.get('sender_id')
    receiver = data.get('receiver_id')
    msg_text = data.get('message')
    media = data.get('media_url', None)

    # चेक करें कि यूजर ब्लॉक तो नहीं है
    user_check = User.query.filter_by(user_id=sender).first()
    if user_check and user_check.is_blocked:
        return jsonify({"error": "You are blocked by admin"}), 403

    # डेटाबेस में परमानेंट सेव करें
    new_msg = Message(sender_id=sender, receiver_id=receiver, message=msg_text, media_url=media)
    db.session.add(new_msg)
    db.session.commit()

    # टेलीग्राम पर चैट और ब्लॉक बटन भेजना
    if ADMIN_CHAT_ID != "YOUR_ADMIN_CHAT_ID":
        tg_text = f"📩 **नया मैसेज आया:**\n👤 यूजर आईडी: `{sender}`\n💬 मैसेज: {msg_text}"
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
            "chat_id": ADMIN_CHAT_ID,
            "text": tg_text,
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "🚫 Permanent Block", "callback_data": f"perm_block_{sender}"},
                        {"text": "⏱️ Temp Block", "callback_data": f"temp_block_{sender}"}
                    ],
                    [
                        {"text": "✅ Unblock", "callback_data": f"unblock_{sender}"}
                    ]
                ]
            }
        })

    return jsonify({"status": "success"})

# टेलीग्राम से जब एडमिन कमांड भेजे या यूजर की हिस्ट्री माँगे
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    update = request.json
    if "callback_query" in update:
        callback = update["callback_query"]
        data = callback["data"]
        chat_id = callback["message"]["chat"]["id"]
        
        parts = data.split("_")
        action = parts[0] + "_" + parts[1]
        target_user = parts[2]
        
        user = User.query.filter_by(user_id=target_user).first()
        if user:
            if action == "perm_block":
                user.is_blocked = True
                user.block_type = "permanent"
                msg = f"🚫 यूजर {target_user} को परमानेंट ब्लॉक कर दिया गया है।"
            elif action == "temp_block":
                user.is_blocked = True
                user.block_type = "temporary"
                msg = f"⏱️ यूजर {target_user} को कुछ समय के लिए ब्लॉक कर दिया गया है।"
            elif action == "unblock":
                user.is_blocked = False
                user.block_type = "none"
                msg = f"✅ यूजर {target_user} को अनब्लॉक कर दिया गया है।"
            db.session.commit()
        else:
            msg = "यूजर नहीं मिला।"

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
            "chat_id": chat_id,
            "text": msg
        })

    elif "message" in update:
        text = update["message"].get("text", "")
        chat_id = update["message"]["chat"]["id"]
        
        if text.startswith("/history"):
            parts = text.split(" ")
            if len(parts) > 1:
                target_id = parts[1]
                messages = Message.query.filter((Message.sender_id == target_id) | (Message.receiver_id == target_id)).all()
                
                if messages:
                    history_text = f"📜 **यूजर {target_id} की चैट हिस्ट्री:**\n\n"
                    for m in messages:
                        history_text += f"[{m.timestamp}] {m.sender_id} ➔ {m.receiver_id}: {m.message}\n"
                else:
                    history_text = f"इस यूजर ({target_id}) की कोई चैट हिस्ट्री नहीं मिली।"
                
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": history_text,
                    "parse_mode": "Markdown"
                })

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
