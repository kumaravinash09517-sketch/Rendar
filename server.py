import os
import random
from datetime import datetime
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests

app = Flask(__name__)

# SQLite Database Setup - चैट और यूजर डेटा सुरक्षित रखने के लिए
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# आपका आधिकारिक टेलीग्राम बॉट टोकन और आपकी चैट आईडी
TELEGRAM_BOT_TOKEN = "8970811998:AAG1pkIq7zWS1fZlnjN6vTMBviZ4xWKKtOc"
ADMIN_CHAT_ID = "7743339724"

# OTP स्टोर (मेमोरी में अस्थायी रूप से)
otp_store = {}


def send_telegram_message(chat_id, text, reply_markup=None):
    if not chat_id or chat_id == "YOUR_ADMIN_CHAT_ID":
        return
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )
    except Exception:
        pass


# 1. User Model - यूजर्स, फोन नंबर, डिवाइस लॉक और ब्लॉक स्टेटस के लिए
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    device_id = db.Column(db.String(120), unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=False)
    avatar_url = db.Column(db.String(255), nullable=True)
    is_online = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_blocked = db.Column(db.Boolean, default=False)
    block_type = db.Column(db.String(20), default="none")  # permanent / temporary


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


def generate_unique_user_id():
    while True:
        code = str(random.randint(100000, 999999))
        if not User.query.filter_by(user_id=code).first():
            return code


def serialize_user(u):
    return {
        "id": u.id,
        "user_id": u.user_id,
        "phone": u.phone,
        "device_id": u.device_id,
        "name": u.name,
        "avatar_url": u.avatar_url or "",
        "is_online": u.is_online,
        "last_login": str(u.last_login) if u.last_login else "",
        "is_blocked": u.is_blocked,
        "block_type": u.block_type
    }


# 🌐 होमपेज राउट (ब्राउज़र में लिंक खोलने पर 200 OK देने के लिए)
@app.route('/', methods=['GET'])
def home():
    return "Hello Sir Backend is Live and Running successfully!"


# 🩺 हेल्थ चेक राउट
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Backend is running fine"})


# 📲 फोन नंबर पर OTP भेजने का राउट
@app.route('/api/auth/send-otp', methods=['POST'])
def send_otp():
    data = request.json or {}
    phone = str(data.get('phone') or data.get('mobile') or '').strip()
    device_id = str(data.get('device_id') or data.get('deviceId') or '').strip()

    if not phone or len(phone) < 10:
        return jsonify({"error": "कृपया सही फोन नंबर दर्ज करें।"}), 400

    # चेक करें कि इस डिवाइस पर पहले से कोई दूसरा फोन नंबर तो लॉगिन नहीं है
    if device_id:
        existing_device_user = User.query.filter_by(device_id=device_id).first()
        if existing_device_user and existing_device_user.phone and existing_device_user.phone != phone:
            return jsonify({
                "error": "इस फोन में पहले से एक अकाउंट लॉगिन है। एक फोन में केवल एक ही अकाउंट चल सकता है।"
            }), 403

    otp_code = str(random.randint(1000, 9999))
    otp_store[phone] = otp_code

    # एडमिन टेलीग्राम पर OTP अलर्ट भेजें ताकि टेस्टिंग में आसानी रहे
    send_telegram_message(
        ADMIN_CHAT_ID,
        f"🔐 *OTP Request*\n📞 फोन: `{phone}`\n🔢 OTP: `{otp_code}`"
    )

    return jsonify({
        "status": "otp_sent",
        "message": f"OTP {phone} पर भेज दिया गया है।",
        "dev_otp": otp_code
    }), 200


# ✅ OTP वेरिफाई करके लॉगिन/रजिस्ट्रेशन पूरा करने का राउट (नाम अनिवार्य, फोटो वैकल्पिक)
@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json or {}
    phone = str(data.get('phone') or data.get('mobile') or '').strip()
    otp = str(data.get('otp') or '').strip()
    name = str(data.get('name') or data.get('username') or '').strip()
    avatar_url = str(data.get('avatar_url') or data.get('photo_url') or '').strip()
    device_id = str(data.get('device_id') or data.get('deviceId') or '').strip()

    if not phone or not otp:
        return jsonify({"error": "फोन नंबर और OTP दोनों जरूरी हैं।"}), 400

    expected_otp = otp_store.get(phone)
    if not expected_otp or otp != expected_otp:
        return jsonify({"error": "गलत या एक्सपायर OTP है।"}), 400

    # चेक करें कि डिवाइस पर पहले से कोई दूसरा नंबर तो नहीं है
    if device_id:
        device_owner = User.query.filter_by(device_id=device_id).first()
        if device_owner and device_owner.phone and device_owner.phone != phone:
            return jsonify({
                "error": "इस फोन में पहले से एक आईडी लॉगिन है। एक फोन में केवल एक ही लॉगिन हो सकता है।"
            }), 403

    user = User.query.filter_by(phone=phone).first()
    if user:
        if user.is_blocked:
            return jsonify({"error": "यह अकाउंट ब्लॉक कर दिया गया है।"}), 403
        # नाम अपडेट करना हो तो (खाली न हो)
        if name:
            user.name = name
        elif not user.name:
            return jsonify({"error": "नाम लिखना जरूरी है।"}), 400

        if avatar_url:
            user.avatar_url = avatar_url
        if device_id and not user.device_id:
            user.device_id = device_id
        user.is_online = True
        user.last_login = datetime.utcnow()
        db.session.commit()
    else:
        # नए यूजर के लिए नाम लिखना अनिवार्य है, फोटो बाद में भी सेट हो सकती है
        if not name:
            return jsonify({"error": "कृपया अपना नाम लिखें (फोटो बाद में भी लगा सकते हैं)।"}), 400

        new_uid = generate_unique_user_id()
        user = User(
            user_id=new_uid,
            phone=phone,
            device_id=device_id or None,
            name=name,
            avatar_url=avatar_url or None,
            is_online=True,
            last_login=datetime.utcnow()
        )
        db.session.add(user)
        db.session.commit()

        send_telegram_message(
            ADMIN_CHAT_ID,
            f"👤 *नया यूजर लॉगिन हुआ!*\nनाम: {user.name}\n📞 फोन: `{user.phone}`\n🆔 आईडी: `{user.user_id}`"
        )

    otp_store.pop(phone, None)
    return jsonify({
        "status": "verified",
        "user": serialize_user(user),
        "user_id": user.user_id,
        "name": user.name,
        "phone": user.phone,
        "avatar_url": user.avatar_url or ""
    }), 200


# 🖼️ प्रोफाइल फोटो (बाद में भी सेट या एडिट करने के लिए) अपडेट राउट
@app.route('/api/users/profile', methods=['POST', 'PUT'])
def update_profile():
    data = request.json or {}
    uid = str(data.get('user_id') or data.get('userId') or '').strip()
    phone = str(data.get('phone') or '').strip()
    name = data.get('name')
    avatar_url = data.get('avatar_url')

    user = None
    if uid:
        user = User.query.filter_by(user_id=uid).first()
    if not user and phone:
        user = User.query.filter_by(phone=phone).first()

    if not user:
        return jsonify({"error": "यूजर नहीं मिला।"}), 404

    if name is not None:
        clean_name = str(name).strip()
        if not clean_name:
            return jsonify({"error": "नाम खाली नहीं हो सकता।"}), 400
        user.name = clean_name

    if avatar_url is not None:
        user.avatar_url = str(avatar_url).strip() or None

    db.session.commit()
    return jsonify({
        "status": "updated",
        "user": serialize_user(user)
    }), 200


# 🔍 फोन नंबर या ID से सीधे यूजर ढूँढने का राउट (भले ही लिस्ट में पहले से न दिख रहा हो)
@app.route('/api/users/find', methods=['GET'])
def find_user():
    phone = str(request.args.get('phone') or '').strip()
    uid = str(request.args.get('user_id') or request.args.get('userId') or '').strip()

    user = None
    if phone:
        user = User.query.filter_by(phone=phone).first()
    elif uid:
        user = User.query.filter_by(user_id=uid).first()

    if not user:
        return jsonify({"found": False, "error": "इस नंबर/आईडी से कोई यूजर नहीं मिला।"}), 404

    return jsonify({
        "found": True,
        "user": serialize_user(user)
    }), 200


# 👤 यूजर रजिस्ट्रेशन राउट (400 एरर को रोकने के लिए पूरी तरह फ्लेक्सिबल + डिवाइस लॉक के साथ)
@app.route('/api/users/register', methods=['POST'])
def register_user():
    data = request.json or {}

    uid = data.get('user_id') or data.get('userId') or data.get('id')
    name = data.get('name') or data.get('username') or data.get('full_name')
    phone = data.get('phone') or data.get('mobile')
    device_id = data.get('device_id') or data.get('deviceId')
    avatar_url = data.get('avatar_url') or data.get('photo_url')

    if not uid and data:
        keys = list(data.keys())
        if keys:
            uid = data.get(keys[0])
    if not name and data:
        keys = list(data.keys())
        if len(keys) > 1:
            name = data.get(keys[1])

    if not uid:
        uid = generate_unique_user_id()
    if not name or not str(name).strip():
        return jsonify({"error": "नाम लिखना जरूरी है।"}), 400

    uid = str(uid).strip()
    name = str(name).strip()
    phone = str(phone).strip() if phone else None
    device_id = str(device_id).strip() if device_id else None

    if device_id:
        device_user = User.query.filter_by(device_id=device_id).first()
        if device_user and device_user.user_id != uid and (not phone or device_user.phone != phone):
            return jsonify({
                "error": "इस फोन में पहले से एक आईडी लॉगिन है। एक फोन में केवल एक ही अकाउंट हो सकता है।"
            }), 403

    user = User.query.filter_by(user_id=uid).first()
    if not user and phone:
        user = User.query.filter_by(phone=phone).first()

    if not user:
        new_user = User(
            user_id=uid,
            phone=phone,
            device_id=device_id,
            name=name,
            avatar_url=str(avatar_url).strip() if avatar_url else None,
            is_online=True,
            last_login=datetime.utcnow()
        )
        db.session.add(new_user)
        db.session.commit()
        send_telegram_message(
            ADMIN_CHAT_ID,
            f"👤 *नया यूजर रजिस्टर्ड हुआ!*\nनाम: {name}\nयूजर आईडी: `{uid}`"
        )
        return jsonify(serialize_user(new_user) | {"status": "registered"}), 200
    else:
        user.name = name
        if phone and not user.phone:
            user.phone = phone
        if device_id and not user.device_id:
            user.device_id = device_id
        if avatar_url:
            user.avatar_url = str(avatar_url).strip()
        user.is_online = True
        user.last_login = datetime.utcnow()
        db.session.commit()
        return jsonify(serialize_user(user) | {"status": "registered"}), 200


# 📋 यूजर डायरेक्टरी राउट (सभी लॉगिन किए हुए यूजर्स की पूरी लिस्ट)
@app.route('/api/users', methods=['GET'])
def get_user_directory():
    users = User.query.order_by(User.last_login.desc()).all()
    users_list = [serialize_user(u) for u in users]
    return jsonify({"users": users_list, "count": len(users_list)})


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

    user_check = User.query.filter_by(user_id=sender).first()
    if user_check and user_check.is_blocked:
        return jsonify({"error": "You are blocked by the administrator."}), 403

    new_msg = Message(sender_id=sender, receiver_id=receiver, message=msg_text, media_url=media)
    db.session.add(new_msg)
    db.session.commit()

    if ADMIN_CHAT_ID != "YOUR_ADMIN_CHAT_ID":
        tg_text = f"📩 *नया मैसेज आया:*\n👤 यूजर आईडी: `{sender}`\n💬 मैसेज: {msg_text}"
        send_telegram_message(
            ADMIN_CHAT_ID,
            tg_text,
            reply_markup={
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
        )

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

            send_telegram_message(chat_id, msg)

    elif "message" in update:
        text = update["message"].get("text", "")
        chat_id = update["message"]["chat"]["id"]

        if text.startswith("/history"):
            parts = text.split(" ")
            if len(parts) > 1:
                target_id = parts[1]
                messages = Message.query.filter(
                    (Message.sender_id == target_id) | (Message.receiver_id == target_id)
                ).all()

                if messages:
                    history_text = f"📜 *यूजर {target_id} की चैट हिस्ट्री:*\n\n"
                    for m in messages:
                        history_text += f"[{m.timestamp}] {m.sender_id} ➔ {m.receiver_id}: {m.message}\n"
                else:
                    history_text = f"इस यूजर ({target_id}) की कोई चैट हिस्ट्री नहीं मिली।"

                send_telegram_message(chat_id, history_text)

    return jsonify({"status": "ok"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
