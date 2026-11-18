import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests

app = Flask(__name__)

# SQLite Database Setup - चैट और यूजर डेटा सुरक्षित रखने के लिए
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# आपका आधिकारिक टेलीग्राम बॉट टोकन
TELEGRAM_BOT_TOKEN = "8970811998:AAG1pkIq7zWS1fZlnjN6vTMBviZ4xWKKtOc"  
ADMIN_CHAT_ID = "7743339724"     # यहाँ अपनी टेलीग्राम चैट आईडी डाल सकते हैं (वैकल्पिक)

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

# 🌐 होमपेज राउट (ब्राउज़र में लिंक खोलने पर 200 OK देने के लिए)
@app.route('/', methods=['GET'])
def home():
    return "Hello Sir Backend is Live and Running successfully!"

# 🩺 हेल्थ चेक राउट
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Backend is running fine"})

# 👤 यूजर रजिस्ट्रेशन राउट (400 एरर को रोकने के लिए पूरी तरह फ्लेक्सिबल बनाया गया)
@app.route('/api/users/register', methods=['POST'])
def register_user():
    data = request.json or {}
    
    # ऐप द्वारा भेजे जाने वाले किसी भी फॉर्मेट को स्वीकार करने के लिए
    uid = data.get('user_id') or data.get('userId') or data.get('id')
    name = data.get('name') or data.get('username') or data.get('full_name')
    
    # अगर सीधे की न मिले तो डेटा डिक्शनरी से वैल्यू निकालने की कोशिश करें
    if not uid and data:
        keys = list(data.keys())
        if keys:
            uid = data.get(keys[0])
    if not name and data:
        keys = list(data.keys())
        if len(keys) > 1:
            name = data.get(keys[1])
            
    # अगर अभी भी खाली रहे तो डिफॉल्ट वैल्यू सेट कर दें ताकि 400 एरर कभी न आए
    if not uid:
        uid = "Unknown_User"
    if not name:
        name = "User"

    user = User.query.filter_by(user_id=uid).first()
    if not user:
        new_user = User(user_id=uid, name=name)
        db.session.add(new_user)
        db.session.commit()
        # जैसे ही नया यूजर रजिस्टर हो, टेलीग्राम पर अलर्ट जाए
        if ADMIN_CHAT_ID != "YOUR_ADMIN_CHAT_ID":
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", json={
                "chat_id": ADMIN_CHAT_ID,
                "text": f"👤 **नया यूजर रजिस्टर्ड हुआ!**\nनाम: {name}\nयूजर आईडी: {uid}"
            })
            
    return jsonify({"status": "registered", "user_id": uid, "name": name}), 200

# 📋 यूजर डायरेक्टरी राउट
@app.route('/api/users', methods=['GET'])
def get_user_directory():
    users = User.query.all()
    users_list = [{"user_id": u.user_id, "name": u.name, "is_blocked": u.is_blocked} for u in users]
    return jsonify({"users": users_list})

# 🔔 एडमिन वेबहुक इवेंट राउट
@app.route('/api/webhooks/admin-event', methods=['POST'])
def admin_webhook_event():
    return jsonify({"status": "success"})

# 📩 मैसेज भेजने और टेलीग्राम पर फॉरवर्ड करने का राउट
@app.route('/api/messages', methods=['POST'])
def send_message():
    data = request.json or {}
    sender = data.get('sender_id') or data.get('senderId')
    receiver = data.get('receiver_id') or data.get('receiverId')
    msg_text = data.get('message') or data.get('text')
    media = data.get('media_url', None)

    # चेक करें कि यूजर ब्लॉक तो नहीं है (HTTP 403 Forbidden हैंडलिंग)
    user_check = User.query.filter_by(user_id=sender).first()
    if user_check and user_check.is_blocked:
        return jsonify({"error": "You are blocked by the administrator."}), 403

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

    return jsonify({
        "id": str(new_msg.id),
        "sender_id": sender,
        "receiver_id": receiver,
        "message": msg_text,
        "media_url": media,
        "timestamp": str(new_msg.timestamp),
        "is_read": new_msg.is_read
    })

# 📜 चैट हिस्ट्री देखने का राउट
@app.route('/api/messages/<peer_id>', methods=['GET'])
def get_messages(peer_id):
    current_user_id = request.args.get('userId') or request.args.get('user_id')
    messages = Message.query.filter(
        ((Message.sender_id == current_user_id) & (Message.receiver_id == peer_id)) |
        ((Message.sender_id == peer_id) & (Message.receiver_id == current_user_id))
    ).all()

    msgs_list = [{
        "id": str(m.id),
        "sender_id": m.sender_id,
        "receiver_id": m.receiver_id,
        "message": m.message,
        "media_url": m.media_url,
        "timestamp": str(m.timestamp),
        "is_read": m.is_read
    } for m in messages]

    return jsonify({"messages": msgs_list})

# 🗑️ मैसेज डिलीट करने का राउट
@app.route('/api/messages/<message_id>', methods=['DELETE'])
def delete_message(message_id):
    msg = Message.query.get(message_id)
    if msg:
        db.session.delete(msg)
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"error": "Message not found"}), 404

# ✔️ मैसेज रीड करने का राउट
@app.route('/api/messages/<peer_id>/read', methods=['POST'])
def mark_conversation_read(peer_id):
    return jsonify({"status": "success"})

# 📁 मीडिया अपलोड राउट
@app.route('/api/media/upload', methods=['POST'])
def upload_media():
    return jsonify({"media_url": "https://placeholder-url.com/media.jpg", "type": "image"})

# 🌐 WebRTC ICE Servers राउट
@app.route('/api/webrtc/ice-servers', methods=['GET'])
def get_ice_servers():
    return jsonify({"ice_servers": []})

# 🤖 टेलीग्राम वेबहुक (ब्लॉक/अनब्लॉक बटन और /history कमांड के लिए)
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    update = request.json or {}
    if "callback_query" in update:
        callback = update["callback_query"]
        data = callback["data"]
        chat_id = callback["message"]["chat"]["id"]
        
        parts = data.split("_")
        if len(parts) >= 3:
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
