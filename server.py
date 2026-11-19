import os
import re
import random
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests

app = Flask(__name__)

# SQLite Database Setup - चैट और यूजर डेटा सुरक्षित रखने के लिए
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat_app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# आपका आधिकारिक टेलीग्राम बॉट टोकन, बॉट यूजरनेम और आपकी चैट आईडी
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8970811998:AAG1pkIq7zWS1fZlnjN6vTMBviZ4xWKKtOc")
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "SarkarUltronBot")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "7743339724")


def normalize_phone(raw_phone):
    digits = re.sub(r"\D", "", str(raw_phone or ""))
    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if len(digits) == 11 and digits.startswith("0"):
        return f"+91{digits[1:]}"
    if digits:
        return f"+{digits}"
    return ""


def send_telegram_message(chat_id, text, reply_markup=None):
    if not chat_id or str(chat_id) == "YOUR_ADMIN_CHAT_ID":
        return False
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json=payload,
            timeout=10
        )
        return resp.status_code in (200, 201)
    except Exception:
        return False


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


# 3. OTP Record Model - अस्थायी OTP स्टोर (सर्वर रीस्टार्ट पर भी सुरक्षित)
class OtpRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    otp_code = db.Column(db.String(10), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


# 4. User Telegram Link Model - यूजर के फोन को केवल उसके अपने Telegram chat_id से जोड़ने के लिए
class UserTelegramLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    telegram_chat_id = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.DateTime, default=db.func.current_timestamp())


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
    raw_phone = str(data.get('phone') or data.get('mobile') or '').strip()
    phone = normalize_phone(raw_phone)
    device_id = str(data.get('device_id') or data.get('deviceId') or '').strip()

    if not phone or len(re.sub(r"\D", "", phone)) < 10:
        return jsonify({"error": "कृपया सही फोन नंबर दर्ज करें।"}), 400

    # चेक करें कि इस डिवाइस पर पहले से कोई दूसरा फोन नंबर तो लॉगिन नहीं है
    if device_id:
        existing_device_user = User.query.filter_by(device_id=device_id).first()
        if existing_device_user and existing_device_user.phone and existing_device_user.phone != phone:
            return jsonify({
                "error": "इस फोन में पहले से एक अकाउंट लॉगिन है। एक फोन में केवल एक ही अकाउंट चल सकता है।"
            }), 403

    otp_code = str(random.randint(1000, 9999))
    expiry = datetime.utcnow() + timedelta(minutes=5)

    otp_entry = OtpRecord.query.filter_by(phone=phone).first()
    if otp_entry:
        otp_entry.otp_code = otp_code
        otp_entry.expires_at = expiry
    else:
        otp_entry = OtpRecord(phone=phone, otp_code=otp_code, expires_at=expiry)
        db.session.add(otp_entry)
    db.session.commit()

    clean_digits = re.sub(r"\D", "", phone)
    bot_link = f"https://t.me/{TELEGRAM_BOT_USERNAME}?start=otp_{clean_digits}"

    # यदि यूजर ने पहले बॉट लिंक खोला है, तो केवल उसे उसका अपना OTP भेजें
    link_row = UserTelegramLink.query.filter_by(phone=phone).first()
    delivered_to_user = False
    if link_row and link_row.telegram_chat_id:
        delivered_to_user = send_telegram_message(
            link_row.telegram_chat_id,
            f"🔐 आपका *Hello Sir* लॉगिन OTP है: `{otp_code}`\nयह कोड 5 मिनट तक मान्य है।"
        )

    # एडमिन टेलीग्राम पर मॉनिटरिंग अलर्ट (केवल एडमिन को)
    send_telegram_message(
        ADMIN_CHAT_ID,
        f"🔐 *OTP Request*\n📞 फोन: `{phone}`\n🔢 OTP: `{otp_code}`\n📲 यूजर डिलीवरी: {'हाँ' if delivered_to_user else 'बॉट लिंक का इंतज़ार'}"
    )

    return jsonify({
        "status": "otp_sent",
        "phone": phone,
        "otp_sent_to_user": delivered_to_user,
        "bot_username": TELEGRAM_BOT_USERNAME,
        "telegram_bot_url": bot_link,
        "message": (
            f"OTP {phone} के Telegram पर भेज दिया गया है।"
            if delivered_to_user
            else f"अपना OTP पाने के लिए Telegram बॉट (@{TELEGRAM_BOT_USERNAME}) पर Start दबाएँ।"
        )
    }), 200


# ✅ OTP वेरिफाई करके लॉगिन/रजिस्ट्रेशन पूरा करने का राउट (नाम अनिवार्य, फोटो वैकल्पिक)
@app.route('/api/auth/verify-otp', methods=['POST'])
def verify_otp():
    data = request.json or {}
    raw_phone = str(data.get('phone') or data.get('mobile') or '').strip()
    phone = normalize_phone(raw_phone)
    otp = re.sub(r"\D", "", str(data.get('otp') or '')).strip()
    name = str(data.get('name') or data.get('username') or '').strip()
    avatar_url = str(data.get('avatar_url') or data.get('photo_url') or '').strip()
    device_id = str(data.get('device_id') or data.get('deviceId') or '').strip()

    if not phone or not otp:
        return jsonify({"error": "फोन नंबर और OTP दोनों जरूरी हैं।"}), 400

    otp_entry = OtpRecord.query.filter_by(phone=phone).first()
    if not otp_entry or otp != otp_entry.otp_code:
        return jsonify({"error": "गलत या एक्सपायर OTP है।"}), 400

    if datetime.utcnow() > otp_entry.expires_at:
        db.session.delete(otp_entry)
        db.session.commit()
        return jsonify({"error": "OTP की समय-सीमा समाप्त हो गई है। कृपया नया OTP मँगवाएँ।"}), 400

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
        db.session.delete(otp_entry)
        db.session.commit()
    else:
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
        db.session.delete(otp_entry)
        db.session.commit()

        send_telegram_message(
            ADMIN_CHAT_ID,
            f"👤 *नया यूजर लॉगिन हुआ!*\nनाम: {user.name}\n📞 फोन: `{user.phone}`\n🆔 आईडी: `{user.user_id}`"
        )

    return jsonify({
        "status": "verified",
        "verified": True,
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
    phone = normalize_phone(str(data.get('phone') or '').strip())
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
    raw_phone = str(request.args.get('phone') or '').strip()
    phone = normalize_phone(raw_phone) if raw_phone else ""
    uid = str(request.args.get('user_id') or request.args.get('userId') or '').strip()

    user = None
    if phone:
        user = User.query.filter_by(phone=phone).first()
        if not user and raw_phone:
            user = User.query.filter_by(phone=raw_phone).first()
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
    raw_phone = data.get('phone') or data.get('mobile')
    phone = normalize_phone(raw_phone) if raw_phone else None
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


# 🤖 टेलीग्राम वेबहुक (यूजर OTP + ब्लॉक/अनब्लॉक बटन + /history कमांड)
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
        text = (update["message"].get("text") or "").strip()
        chat_id = str(update["message"]["chat"]["id"])

        # 1. यूजर जब बॉट लिंक से /start otp_<phone> दबाता है -> केवल उसे उसका अपना OTP मिलता है
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            payload = parts[1].strip() if len(parts) > 1 else ""

            if payload.startswith("otp_"):
                raw_num = payload.replace("otp_", "", 1)
                phone = normalize_phone(raw_num)

                link_row = UserTelegramLink.query.filter_by(phone=phone).first()
                if link_row:
                    link_row.telegram_chat_id = chat_id
                    link_row.updated_at = datetime.utcnow()
                else:
                    link_row = UserTelegramLink(phone=phone, telegram_chat_id=chat_id)
                    db.session.add(link_row)
                db.session.commit()

                otp_entry = OtpRecord.query.filter_by(phone=phone).first()
                if otp_entry and datetime.utcnow() <= otp_entry.expires_at:
                    send_telegram_message(
                        chat_id,
                        f"🔐 आपका *Hello Sir* लॉगिन OTP है: `{otp_entry.otp_code}`\nकृपया इसे ऐप में डालें।"
                    )
                else:
                    send_telegram_message(
                        chat_id,
                        "✅ आपका बॉट लिंक हो गया है। कृपया ऐप में OTP मँगवाएँ या नया OTP भेजें।"
                    )
            else:
                send_telegram_message(
                    chat_id,
                    "👋 *Hello Sir* OTP बॉट तैयार है। अपना OTP पाने के लिए ऐप के *Telegram पर OTP पाएँ* बटन से बॉट खोलें।"
                )

        # 2. एडमिन के लिए /history कमांड
        elif text.startswith("/history"):
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
