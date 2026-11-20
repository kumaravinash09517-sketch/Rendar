import os
import re
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
    media_url = db.Column(db.String(500), nullable=True)
    msg_type = db.Column(db.String(30), default="text")
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_label = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    is_read = db.Column(db.Boolean, default=False)


with app.app_context():
    db.create_all()


def generate_unique_user_id():
    while True:
        code = f"u_{random.randint(100000, 999999)}"
        if not User.query.filter_by(user_id=code).first():
            return code


def serialize_user(u):
    return {
        "id": u.id,
        "user_id": u.user_id,
        "userId": u.user_id,
        "phone": u.phone or "",
        "device_id": u.device_id or "",
        "deviceId": u.device_id or "",
        "name": u.name,
        "display_name": u.name,
        "displayName": u.name,
        "avatar_url": u.avatar_url or "",
        "avatarUrl": u.avatar_url or "",
        "is_online": bool(u.is_online),
        "isOnline": bool(u.is_online),
        "last_login": str(u.last_login) if u.last_login else "",
        "lastLogin": str(u.last_login) if u.last_login else "",
        "is_blocked": bool(u.is_blocked),
        "isBlocked": bool(u.is_blocked),
        "block_type": u.block_type
    }


def serialize_message(m):
    safe_text = m.message if m.message is not None else ""
    safe_media = m.media_url if m.media_url is not None else ""
    return {
        "id": str(m.id),
        "sender_id": m.sender_id,
        "senderId": m.sender_id,
        "receiver_id": m.receiver_id,
        "receiverId": m.receiver_id,
        "message": safe_text,
        "text": safe_text,
        "content": safe_text,
        "media_url": safe_media,
        "mediaUrl": safe_media,
        "msg_type": m.msg_type or "text",
        "type": m.msg_type or "text",
        "latitude": m.latitude,
        "longitude": m.longitude,
        "location_label": m.location_label or "",
        "locationLabel": m.location_label or "",
        "timestamp": str(m.timestamp) if m.timestamp else "",
        "is_read": bool(m.is_read),
        "isRead": bool(m.is_read)
    }


def _find_user_by_identifier(raw_query):
    q = str(raw_query or "").strip()
    if not q:
        return None

    user = User.query.filter(db.func.lower(User.user_id) == q.lower()).first()
    if user:
        return user

    norm_phone = normalize_phone(q)
    if norm_phone:
        user = User.query.filter_by(phone=norm_phone).first()
        if user:
            return user

    digits_only = re.sub(r"\D", "", q)
    if digits_only:
        all_users = User.query.all()
        for u in all_users:
            u_digits = re.sub(r"\D", "", str(u.phone or ""))
            uid_digits = re.sub(r"\D", "", str(u.user_id or ""))
            if (u_digits and (u_digits == digits_only or u_digits.endswith(digits_only) or digits_only.endswith(u_digits))) or (uid_digits and uid_digits == digits_only):
                return u

    return User.query.filter(db.func.lower(User.name).contains(q.lower())).first()


def _process_direct_login(data):
    raw_name = str(
        data.get('name') or data.get('username') or data.get('display_name') or data.get('displayName') or ''
    ).strip()
    raw_uid = str(
        data.get('user_id') or data.get('userId') or data.get('id') or ''
    ).strip()
    raw_phone = str(data.get('phone') or data.get('mobile') or '').strip()
    phone = normalize_phone(raw_phone) if raw_phone else None
    device_id = str(data.get('device_id') or data.get('deviceId') or '').strip() or None
    avatar_url = str(data.get('avatar_url') or data.get('avatarUrl') or data.get('photo_url') or '').strip()

    if not raw_name and not raw_uid and not phone:
        return jsonify({"error": "कृपया यूजरनेम या यूजर ID दर्ज करें।"}), 400

    # सिंगल-डिवाइस लॉक: एक डिवाइस पर केवल एक ही अकाउंट बाइंड रहेगा
    if device_id:
        device_owner = User.query.filter_by(device_id=device_id).first()
        if device_owner:
            same_account = (
                (raw_uid and device_owner.user_id.lower() == raw_uid.lower()) or
                (phone and device_owner.phone == phone) or
                (not raw_uid and not phone and raw_name and device_owner.name.lower() == raw_name.lower())
            )
            if not same_account:
                return jsonify({
                    "error": "इस डिवाइस पर पहले से एक अकाउंट लॉगिन है। एक डिवाइस में केवल एक ही अकाउंट चल सकता है।"
                }), 403

    user = None
    if raw_uid:
        user = User.query.filter(db.func.lower(User.user_id) == raw_uid.lower()).first()
    if not user and phone:
        user = User.query.filter_by(phone=phone).first()

    if user:
        if user.is_blocked:
            return jsonify({"error": "You are blocked by the administrator."}), 403
        if user.device_id and device_id and user.device_id != device_id:
            return jsonify({
                "error": "यह यूजर ID पहले से किसी अन्य डिवाइस से लॉक है।"
            }), 403
        if raw_name:
            user.name = raw_name
        if phone and not user.phone:
            user.phone = phone
        if device_id and not user.device_id:
            user.device_id = device_id
        if avatar_url:
            user.avatar_url = avatar_url
        user.is_online = True
        user.last_login = datetime.utcnow()
        db.session.commit()
    else:
        uid_to_use = raw_uid if raw_uid else generate_unique_user_id()
        existing_uid = User.query.filter(db.func.lower(User.user_id) == uid_to_use.lower()).first()
        if existing_uid:
            if existing_uid.is_blocked:
                return jsonify({"error": "You are blocked by the administrator."}), 403
            if existing_uid.device_id and device_id and existing_uid.device_id != device_id:
                return jsonify({
                    "error": "यह यूजर ID पहले से किसी अन्य डिवाइस से लॉक है।"
                }), 403
            user = existing_uid
            if raw_name:
                user.name = raw_name
            if phone and not user.phone:
                user.phone = phone
            if device_id and not user.device_id:
                user.device_id = device_id
            if avatar_url:
                user.avatar_url = avatar_url
            user.is_online = True
            user.last_login = datetime.utcnow()
            db.session.commit()
        else:
            final_name = raw_name if raw_name else uid_to_use
            user = User(
                user_id=uid_to_use,
                phone=phone,
                device_id=device_id,
                name=final_name,
                avatar_url=avatar_url or None,
                is_online=True,
                last_login=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()

            send_telegram_message(
                ADMIN_CHAT_ID,
                f"👤 *नया यूजर लॉगिन हुआ!*\nनाम: {user.name}\n🆔 आईडी: `{user.user_id}`"
            )

    user_dict = serialize_user(user)
    return jsonify({
        "status": "logged_in",
        "verified": True,
        "user": user_dict,
        "user_id": user.user_id,
        "userId": user.user_id,
        "name": user.name,
        "phone": user.phone or "",
        "avatar_url": user.avatar_url or ""
    }), 200


# 🌐 होमपेज राउट
@app.route('/', methods=['GET'])
def home():
    return "Hello Sir Backend is Live and Running successfully!"


# 🩺 हेल्थ चेक राउट
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "message": "Backend is running fine"})


# 🔐 डायरेक्ट Username + User ID लॉगिन राउट (बिना OTP)
@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    return _process_direct_login(request.json or {})


# 👤 यूजर रजिस्ट्रेशन / डायरेक्ट लॉगिन राउट
@app.route('/api/users/register', methods=['POST'])
def register_user():
    data = request.json or {}
    if not data.get('name') and not data.get('username') and not data.get('display_name') and not data.get('displayName') and data:
        keys = list(data.keys())
        if len(keys) > 1 and not data.get('user_id') and not data.get('userId'):
            data = dict(data)
            data['user_id'] = data.get(keys[0])
            data['name'] = data.get(keys[1])
    return _process_direct_login(data)


# 🖼️ प्रोफाइल फोटो / नाम अपडेट राउट
@app.route('/api/users/profile', methods=['POST', 'PUT'])
def update_profile():
    data = request.json or {}
    uid = str(data.get('user_id') or data.get('userId') or '').strip()
    phone = normalize_phone(str(data.get('phone') or '').strip())
    name = data.get('name')
    avatar_url = data.get('avatar_url') or data.get('avatarUrl')

    user = None
    if uid:
        user = User.query.filter(db.func.lower(User.user_id) == uid.lower()).first()
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


# 🔍 फोन नंबर, नाम या ID से तुरंत यूजर ढूँढने का राउट
@app.route('/api/users/find', methods=['GET'])
def find_user():
    raw_q = str(
        request.args.get('q') or
        request.args.get('query') or
        request.args.get('phone') or
        request.args.get('user_id') or
        request.args.get('userId') or
        request.args.get('id') or
        ''
    ).strip()

    if not raw_q:
        users = User.query.order_by(User.last_login.desc()).all()
        users_list = [serialize_user(u) for u in users]
        return jsonify({"found": len(users_list) > 0, "users": users_list}), 200

    q_lower = raw_q.lower()
    digits_only = re.sub(r"\D", "", raw_q)
    norm_phone = normalize_phone(raw_q)

    matched = []
    for u in User.query.order_by(User.last_login.desc()).all():
        uid_str = str(u.user_id or "")
        name_str = str(u.name or "")
        phone_str = str(u.phone or "")
        u_digits = re.sub(r"\D", "", phone_str)
        uid_digits = re.sub(r"\D", "", uid_str)

        if (
            q_lower in uid_str.lower() or
            q_lower in name_str.lower() or
            (norm_phone and phone_str == norm_phone) or
            (digits_only and u_digits and (digits_only in u_digits or u_digits.endswith(digits_only))) or
            (digits_only and uid_digits and (digits_only in uid_digits or uid_digits.endswith(digits_only)))
        ):
            matched.append(serialize_user(u))

    if not matched:
        return jsonify({"found": False, "users": [], "error": "इस नाम/नंबर/आईडी से कोई यूजर नहीं मिला।"}), 404

    return jsonify({
        "found": True,
        "user": matched[0],
        "users": matched
    }), 200


# 🔍 वैकल्पिक सर्च राउट
@app.route('/api/users/search', methods=['GET'])
def search_users():
    return find_user()


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
    sender = str(data.get('sender_id') or data.get('senderId') or '').strip()
    receiver = str(data.get('receiver_id') or data.get('receiverId') or '').strip()
    msg_text = str(
        data.get('message') if data.get('message') is not None else
        (data.get('text') if data.get('text') is not None else (data.get('content') or ''))
    )
    media = str(data.get('media_url') or data.get('mediaUrl') or '').strip() or None
    msg_type = str(data.get('msg_type') or data.get('type') or ('image' if media else 'text')).strip()
    lat = data.get('latitude')
    lng = data.get('longitude')
    loc_label = str(data.get('location_label') or data.get('locationLabel') or '').strip() or None

    if not sender or not receiver:
        return jsonify({"error": "sender_id और receiver_id जरूरी हैं।"}), 400

    user_check = User.query.filter_by(user_id=sender).first()
    if user_check and user_check.is_blocked:
        return jsonify({"error": "You are blocked by the administrator."}), 403

    new_msg = Message(
        sender_id=sender,
        receiver_id=receiver,
        message=msg_text,
        media_url=media,
        msg_type=msg_type,
        latitude=float(lat) if lat is not None and str(lat).strip() != "" else None,
        longitude=float(lng) if lng is not None and str(lng).strip() != "" else None,
        location_label=loc_label
    )
    db.session.add(new_msg)
    db.session.commit()

    if ADMIN_CHAT_ID != "YOUR_ADMIN_CHAT_ID":
        preview_text = msg_text or loc_label or media or "(मीडिया/लोकेशन)"
        tg_text = f"📩 *नया मैसेज आया:*\n👤 यूजर आईडी: `{sender}` ➔ `{receiver}`\n💬 मैसेज: {preview_text}"
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

    return jsonify(serialize_message(new_msg)), 200


# 📜 चैट हिस्ट्री देखने का राउट
@app.route('/api/messages/<peer_id>', methods=['GET'])
def get_messages(peer_id):
    current_user_id = str(request.args.get('userId') or request.args.get('user_id') or '').strip()
    if current_user_id:
        messages = Message.query.filter(
            ((Message.sender_id == current_user_id) & (Message.receiver_id == peer_id)) |
            ((Message.sender_id == peer_id) & (Message.receiver_id == current_user_id))
        ).order_by(Message.id.asc()).all()
    else:
        messages = Message.query.filter(
            (Message.sender_id == peer_id) | (Message.receiver_id == peer_id)
        ).order_by(Message.id.asc()).all()

    msgs_list = [serialize_message(m) for m in messages]
    return jsonify({"messages": msgs_list}), 200


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
    data = request.json or {}
    reader_id = str(data.get('user_id') or data.get('userId') or request.args.get('userId') or '').strip()
    query = Message.query.filter(Message.sender_id == peer_id)
    if reader_id:
        query = query.filter(Message.receiver_id == reader_id)
    query.update({"is_read": True}, synchronize_session=False)
    db.session.commit()
    return jsonify({"status": "success"})


# 📁 मीडिया अपलोड राउट
@app.route('/api/media/upload', methods=['POST'])
def upload_media():
    if request.files and 'file' in request.files:
        f = request.files['file']
        os.makedirs("uploads", exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", f.filename or "media.jpg")
        save_path = os.path.join("uploads", safe_name)
        f.save(save_path)
        base_url = request.host_url.rstrip("/")
        return jsonify({"media_url": f"{base_url}/uploads/{safe_name}", "url": f"{base_url}/uploads/{safe_name}", "type": "image"}), 200

    data = request.json or {}
    url = str(data.get('media_url') or data.get('url') or "https://placeholder-url.com/media.jpg").strip()
    return jsonify({"media_url": url, "url": url, "type": "image"}), 200


# 🌐 WebRTC ICE Servers राउट
@app.route('/api/webrtc/ice-servers', methods=['GET'])
def get_ice_servers():
    return jsonify({
        "ice_servers": [
            {"urls": "stun:stun.l.google.com:19302"},
            {"urls": "stun:stun1.l.google.com:19302"}
        ]
    }), 200


# 🤖 टेलीग्राम वेबहुक (ब्लॉक/अनब्लॉक बटन + /history कमांड)
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
            target_user = "_".join(parts[2:])

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

        if text.startswith("/start"):
            send_telegram_message(
                chat_id,
                "👋 *Hello Sir* एडमिन/नोटिफिकेशन बॉट तैयार है। लॉगिन सीधे ऐप में Username और User ID से किया जा सकता है।"
            )

        elif text.startswith("/history"):
            parts = text.split(" ", 1)
            if len(parts) > 1:
                target_id = parts[1].strip()
                messages = Message.query.filter(
                    (Message.sender_id == target_id) | (Message.receiver_id == target_id)
                ).order_by(Message.id.asc()).all()

                if messages:
                    history_text = f"📜 *यूजर {target_id} की चैट हिस्ट्री:*\n\n"
                    for m in messages:
                        history_text += f"[{m.timestamp}] {m.sender_id} ➔ {m.receiver_id}: {m.message or m.media_url or m.location_label or ''}\n"
                else:
                    history_text = f"इस यूजर ({target_id}) की कोई चैट हिस्ट्री नहीं मिली।"

                send_telegram_message(chat_id, history_text)

    return jsonify({"status": "ok"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
