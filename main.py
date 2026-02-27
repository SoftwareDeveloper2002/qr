from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import Response, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import RedirectResponse
import qrcode
from qrcode.constants import ERROR_CORRECT_H
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image
from io import BytesIO
import base64
import os
import requests
import json
import datetime
import uuid

app = FastAPI(docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# IP-based rate limiting (no signup, no API key)
RATE_LIMIT_IP = {}
IP_RATE = 200  # requests per day per IP

def get_client_ip(request: Request):
    ip = request.headers.get("x-forwarded-for")
    return ip.split(",")[0].strip() if ip else request.client.host

def check_ip_limit(ip):
    today = datetime.date.today().isoformat()
    count = RATE_LIMIT_IP.get(ip, {}).get(today, 0)

    if count >= IP_RATE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    RATE_LIMIT_IP.setdefault(ip, {})[today] = count + 1

# Analytics
os.makedirs("analytics", exist_ok=True)

def log_event(event: dict):
    event["time"] = datetime.datetime.now().isoformat()
    with open("analytics/events.jsonl", "a") as f:
        f.write(json.dumps(event) + "\n")

def log_scan(qr_id, device=None, ip=None):
    log_event({"type": "scan", "qr_id": qr_id, "device": device, "ip": ip})

def new_qr_id():
    return str(uuid.uuid4())

def send_webhook(payload):
    url = os.getenv("QR_WEBHOOK_URL")
    if not url:
        return
    try:
        requests.post(url, json=payload, timeout=3)
    except:
        pass

@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/docs")
def docs(request: Request):
    return templates.TemplateResponse("documentation.html", {"request": request})

@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return HTMLResponse(str(exc.detail), status_code=exc.status_code)

def load_logo(logo: str = None, file: UploadFile = None):
    if file:
        return Image.open(file.file).convert("RGBA")
    if logo:
        try:
            return Image.open(BytesIO(base64.b64decode(logo))).convert("RGBA")
        except:
            pass
        try:
            resp = requests.get(logo, timeout=5)
            if resp.status_code == 200:
                return Image.open(BytesIO(resp.content)).convert("RGBA")
        except:
            pass
    if os.path.exists("static/logo.png"):
        return Image.open("static/logo.png").convert("RGBA")
    return None

def paste_logo(img, logo_img):
    if not logo_img:
        return img
    logo_size = 60
    logo_img = logo_img.resize((logo_size, logo_size))
    white_bg = Image.new("RGBA", (logo_size, logo_size), (255, 255, 255, 255))
    white_bg.paste(logo_img, (0, 0), mask=logo_img)
    pos = ((img.size[0] - logo_size) // 2, (img.size[1] - logo_size) // 2)
    img.paste(white_bg, pos)
    return img

@app.post("/api/generate-qr")
def api_generate_qr(
    data: str = Form(...),
    logo: str = Form(None),
    file: UploadFile = File(None),
    request: Request = None
):
    ip = get_client_ip(request)
    check_ip_limit(ip)

    qr_id = new_qr_id()
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    logo_img = load_logo(logo, file)
    img = paste_logo(img, logo_img)

    os.makedirs("static", exist_ok=True)
    img.save(f"static/{qr_id}.png")

    log_event({"type": "qr.generate", "qr_id": qr_id, "data_length": len(data)})
    return Response(content=img_to_bytes(img), media_type="image/png")

def img_to_bytes(img):
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer.getvalue()

@app.get("/qr/{qr_id}")
def view_qr(request: Request, qr_id: str):
    path = f"static/{qr_id}.png"
    if not os.path.exists(path):
        raise HTTPException(404, "QR not found")
    return templates.TemplateResponse("result.html", {"request": request, "image": f"/static/{qr_id}.png", "qr_id": qr_id})

@app.get("/qr/{qr_id}/scan")
def track_scan(request: Request, qr_id: str):
    device = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    log_scan(qr_id, device=device, ip=ip)
    send_webhook({"event": "qr.scan", "qr_id": qr_id, "ip": ip})
    return RedirectResponse(url="/")

@app.post("/api/generate-barcode")
def api_generate_barcode(data: str = Form(...), request: Request = None):
    ip = get_client_ip(request)
    check_ip_limit(ip)

    barcode_id = new_qr_id()
    barcode = Code128(data, writer=ImageWriter())
    buffer = BytesIO()
    barcode.write(buffer)
    buffer.seek(0)

    log_event({"type": "barcode.generate", "barcode_id": barcode_id})
    return Response(content=buffer.getvalue(), media_type="image/png")

@app.post("/api/generate-wifi-qr")
def api_generate_wifi_qr(
    ssid: str = Form(...),
    password: str = Form(...),
    security: str = Form("WPA"),
    logo: str = Form(None),
    file: UploadFile = File(None),
    request: Request = None
):
    ip = get_client_ip(request)
    check_ip_limit(ip)

    wifi_data = f"WIFI:S:{ssid};T:{security};P:{password};;"
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(wifi_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    logo_img = load_logo(logo, file)
    img = paste_logo(img, logo_img)

    qr_id = new_qr_id()
    img.save(f"static/{qr_id}.png")

    log_event({"type": "wifi.generate", "qr_id": qr_id, "ssid": ssid})
    return Response(content=img_to_bytes(img), media_type="image/png")

@app.post("/admin/login")
def admin_login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent")

    record = {
        "time": datetime.datetime.now().isoformat(),
        "ip": ip,
        "device": user_agent,
        "username": username
    }

    os.makedirs("logs", exist_ok=True)
    with open("logs/admin-login-attempts.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")

    return RedirectResponse(url="/admin/dashboard", status_code=302)

@app.get("/admin/dashboard")
def admin_dashboard(request: Request):
    logs = []
    if os.path.exists("logs/admin-login-attempts.jsonl"):
        with open("logs/admin-login-attempts.jsonl") as f:
            for line in f:
                try:
                    logs.append(json.loads(line))
                except:
                    pass
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "logs": list(reversed(logs))})

@app.get("/tests")
def test_page(request: Request):
    return templates.TemplateResponse("tests/test-endpoints.html", {"request": request})