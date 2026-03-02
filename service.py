import json
import uuid
import os
import datetime
import hashlib
import threading
import base64
from typing import Optional, Dict, List
from fastapi import HTTPException, UploadFile
from fastapi.responses import Response, RedirectResponse
from io import BytesIO
from PIL import Image
import qrcode
from qrcode.constants import ERROR_CORRECT_H
from barcode import Code128
from barcode.writer import ImageWriter

from api_keys import create_api_key
from geo import geo_from_ip
from device import detect_device

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
MAX_DATA_LENGTH = 2000
MAX_LOGO_SIZE = 2 * 1024 * 1024
QR_STORE_FILE = "analytics/qr_store.json"
EVENT_LOG = "analytics/events.jsonl"
RATE_LIMIT_IP = {}
IP_RATE = 200

os.makedirs("analytics", exist_ok=True)
os.makedirs("static", exist_ok=True)

_lock = threading.Lock()


def _write(path, data):
    with _lock:
        with open(path, "w") as f:
            json.dump(data, f)


def load_qr_store() -> dict:
    if not os.path.exists(QR_STORE_FILE):
        return {}
    try:
        with open(QR_STORE_FILE) as f:
            return json.load(f)
    except:
        return {}


def save_qr_store(data: dict):
    _write(QR_STORE_FILE, data)


def new_qr_id() -> str:
    return str(uuid.uuid4())


def img_to_bytes(img: Image.Image) -> bytes:
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()


def is_valid_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def hash_ip(ip):
    return hashlib.sha256(ip.encode()).hexdigest() if ip else None


def rate_limit(ip):
    today = datetime.date.today().isoformat()
    record = RATE_LIMIT_IP.setdefault(hash_ip(ip), {})
    if record.get(today, 0) >= IP_RATE:
        raise HTTPException(429)
    record[today] = record.get(today, 0) + 1


def log_event(event):
    event["time"] = datetime.datetime.now().isoformat()
    with open(EVENT_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def load_logo(logo=None, file: UploadFile = None):
    try:
        if file:
            data = file.file.read()
            if len(data) > MAX_LOGO_SIZE:
                raise HTTPException(400)
            return Image.open(BytesIO(data)).convert("RGBA")

        if logo:
            try:
                return Image.open(BytesIO(base64.b64decode(logo))).convert("RGBA")
            except:
                pass

        if os.path.exists("static/logo.png"):
            return Image.open("static/logo.png").convert("RGBA")
    except:
        pass
    return None


def paste_logo(img, logo_img: Optional[Image.Image]):
    if not logo_img:
        return img
    size = 60
    logo_img = logo_img.resize((size, size))
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    white.paste(logo_img, (0, 0), mask=logo_img)
    img.paste(white, ((img.size[0] - size) // 2, (img.size[1] - size) // 2))
    return img


# ----------------------------------------------------
# QR RECORD
# ----------------------------------------------------
def create_qr_record(destination, expires_in, password, tags=None, template=None):
    qr_id = new_qr_id()
    store = load_qr_store()

    expiration = None
    if expires_in:
        expiration = (
            datetime.datetime.now() +
            datetime.timedelta(minutes=expires_in)
        ).isoformat()

    store[qr_id] = {
        "destination": destination,
        "created_at": datetime.datetime.now().isoformat(),
        "expires_at": expiration,
        "password": password,
        "scan_count": 0,
        "unique_ips": [],
        "geo": [],
        "versions": [destination],
        "tags": tags or [],
        "template": template,
        "active": True,
        "deleted": False,
        "webhook": None
    }
    save_qr_store(store)
    return qr_id


def generate_qr_image(qr_id, logo=None, file=None, request=None):
    base = str(request.base_url).rstrip("/")
    redirect_url = f"{base}/r/{qr_id}"

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(redirect_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = paste_logo(img, load_logo(logo, file))
    img.save(f"static/{qr_id}.png")
    return img

def generate_qr(data, expires_in, password, logo, file, request, template=None, webhook=None):
    if len(data) > MAX_DATA_LENGTH:
        raise HTTPException(400)
    if not is_valid_url(data):
        raise HTTPException(400)

    rate_limit(request.client.host)
    qr_id = create_qr_record(data, expires_in, password, template=template)
    store = load_qr_store()
    store[qr_id]["webhook"] = webhook
    save_qr_store(store)

    img = generate_qr_image(qr_id, logo, file, request)
    log_event({"type": "qr.generate", "qr_id": qr_id})
    return Response(content=img_to_bytes(img), media_type="image/png")


# ----------------------------------------------------
# REDIRECT + WEBHOOK
# ----------------------------------------------------
def _trigger_webhook(url, payload):
    if not url:
        return
    try:
        import requests
        requests.post(url, json=payload, timeout=2)
    except:
        pass


def redirect_qr_service(request, qr_id, access_key):
    store = load_qr_store()
    record = store.get(qr_id)

    if not record or record.get("deleted") or not record.get("active"):
        raise HTTPException(404)

    if record.get("expires_at") and datetime.datetime.now() > datetime.datetime.fromisoformat(record["expires_at"]):
        record["active"] = False
        save_qr_store(store)
        raise HTTPException(410)

    if record.get("password") and access_key != record.get("password"):
        raise HTTPException(403)

    ip = request.client.host if request.client else None
    geo = geo_from_ip(ip)
    device = detect_device(request.headers.get("user-agent"))

    record["scan_count"] += 1
    if ip and ip not in record["unique_ips"]:
        record["unique_ips"].append(ip)
    record["geo"].append(geo)

    store[qr_id] = record
    save_qr_store(store)

    payload = {
        "qr_id": qr_id,
        "ip": hash_ip(ip),
        "geo": geo,
        "device": device,
        "time": datetime.datetime.now().isoformat()
    }
    _trigger_webhook(record.get("webhook"), payload)

    log_event({"type": "scan", "qr_id": qr_id, **payload})

    return RedirectResponse(url=record["destination"])


# ----------------------------------------------------
# STATS
# ----------------------------------------------------
def get_qr_stats(qr_id):
    store = load_qr_store()
    record = store.get(qr_id)

    if not record:
        raise HTTPException(404)

    countries = {}
    for g in record.get("geo", []):
        countries[g.get("country", "Unknown")] = countries.get(g.get("country", "Unknown"), 0) + 1

    return {
        "qr_id": qr_id,
        "destination": record["destination"],
        "created_at": record["created_at"],
        "expires_at": record.get("expires_at"),
        "scan_count": record.get("scan_count", 0),
        "unique_scans": len(record.get("unique_ips", [])),
        "countries": countries,
        "versions": record.get("versions", []),
        "tags": record.get("tags", []),
        "template": record.get("template")
    }


# ----------------------------------------------------
# LIST / SEARCH
# ----------------------------------------------------
def list_qr(page=1, limit=50):
    store = load_qr_store()
    items = list(store.items())
    start = (page - 1) * limit
    return items[start:start + limit]


def search_qr(query):
    store = load_qr_store()
    return {
        k: v for k, v in store.items()
        if query.lower() in k.lower() or query.lower() in v.get("destination", "").lower()
    }


# ----------------------------------------------------
# EDIT / HISTORY
# ----------------------------------------------------
def edit_qr_service(qr_id, new_url):
    if not is_valid_url(new_url):
        raise HTTPException(400)

    store = load_qr_store()
    record = store.get(qr_id)
    if not record:
        raise HTTPException(404)

    record["destination"] = new_url
    record.setdefault("versions", []).append(new_url)

    store[qr_id] = record
    save_qr_store(store)

    log_event({"type": "qr.edit", "qr_id": qr_id})
    return {"status": "updated", "qr_id": qr_id}


def restore_qr_service(qr_id):
    store = load_qr_store()
    record = store.get(qr_id)

    if not record:
        raise HTTPException(404)

    record["active"] = True
    record["deleted"] = False
    store[qr_id] = record
    save_qr_store(store)

    log_event({"type": "qr.restore", "qr_id": qr_id})
    return {"status": "restored"}


def delete_qr_service(qr_id):
    store = load_qr_store()
    record = store.get(qr_id)

    if not record:
        raise HTTPException(404)

    record["deleted"] = True
    record["active"] = False
    store[qr_id] = record
    save_qr_store(store)

    img_path = f"static/{qr_id}.png"
    if os.path.exists(img_path):
        os.remove(img_path)

    log_event({"type": "qr.delete", "qr_id": qr_id})
    return {"status": "deleted"}


# ----------------------------------------------------
# TAGS
# ----------------------------------------------------
def add_qr_tag(qr_id, tag):
    store = load_qr_store()
    record = store.get(qr_id)
    if not record:
        raise HTTPException(404)

    record.setdefault("tags", []).append(tag)
    store[qr_id] = record
    save_qr_store(store)
    return {"status": "tagged"}


def get_qr_tags(qr_id):
    store = load_qr_store()
    record = store.get(qr_id)
    if not record:
        raise HTTPException(404)
    return record.get("tags", [])


# ----------------------------------------------------
# BARCODE
# ----------------------------------------------------
def generate_barcode(data, request):
    rate_limit(request.client.host)

    barcode = Code128(data, writer=ImageWriter())
    buffer = BytesIO()
    barcode.write(buffer)
    buffer.seek(0)

    log_event({"type": "barcode.generate"})
    return Response(content=buffer.getvalue(), media_type="image/png")


# ----------------------------------------------------
# WIFI QR
# ----------------------------------------------------
def generate_wifi_qr(ssid, password, security, logo, file, request):
    rate_limit(request.client.host)

    wifi_data = f"WIFI:S:{ssid};T:{security};P:{password};;"
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(wifi_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = paste_logo(img, load_logo(logo, file))
    qr_id = new_qr_id()
    img.save(f"static/{qr_id}.png")

    log_event({"type": "wifi.generate", "qr_id": qr_id})
    return Response(content=img_to_bytes(img), media_type="image/png")


# ----------------------------------------------------
# CONTACT QR
# ----------------------------------------------------
def create_contact_qr(name, phone, email):
    data = f"BEGIN:VCARD\nVERSION:3.0\nFN:{name}\nTEL:{phone}\nEMAIL:{email}\nEND:VCARD"
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_id = new_qr_id()
    img.save(f"static/{qr_id}.png")
    return Response(content=img_to_bytes(img), media_type="image/png")


# ----------------------------------------------------
# API KEYS
# ----------------------------------------------------
def create_api_key_service(owner, limit):
    return {"api_key": create_api_key(owner, limit)}


def daily_report():
    store = load_qr_store()

    return {
        "total_qr": len(store),
        "active": sum(1 for r in store.values() if r.get("active")),
        "deleted": sum(1 for r in store.values() if r.get("deleted")),
        "scans": sum(r.get("scan_count", 0) for r in store.values())
    }