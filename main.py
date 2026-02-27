from fastapi import FastAPI, Request, Form, File, UploadFile
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

app = FastAPI(docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# ----------------------------------------------------
# SSR PAGES
# ----------------------------------------------------
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/docs")
def docs(request: Request):
    return templates.TemplateResponse("documentation.html", {"request": request})


# ----------------------------------------------------
# 404 HANDLER (CUSTOM PAGE)
# ----------------------------------------------------
@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "404.html",
            {"request": request},
            status_code=404
        )

    return HTMLResponse(str(exc.detail), status_code=exc.status_code)


# ----------------------------------------------------
# HELPER: LOAD LOGO FROM SOURCE
# ----------------------------------------------------
def load_logo(logo: str = None, file: UploadFile = None):
    """
    Returns PIL Image or None
    - logo (base64 or URL)
    - file upload
    - fallback to static/logo.png
    """

    if file:
        return Image.open(file.file).convert("RGBA")

    if logo:
        try:
            logo_data = base64.b64decode(logo)
            return Image.open(BytesIO(logo_data)).convert("RGBA")
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


# ----------------------------------------------------
# HELPER: PASTE LOGO WITH WHITE BACKGROUND
# ----------------------------------------------------
def paste_logo(img, logo_img):
    if not logo_img:
        return img

    logo_size = 60
    logo_img = logo_img.resize((logo_size, logo_size))

    white_bg = Image.new("RGBA", (logo_size, logo_size), (255, 255, 255, 255))
    white_bg.paste(logo_img, (0, 0), mask=logo_img)

    pos = (
        (img.size[0] - logo_size) // 2,
        (img.size[1] - logo_size) // 2
    )

    img.paste(white_bg, pos)
    return img


# ----------------------------------------------------
# QR GENERATION (SSR FORM -> RESULT PAGE)
# ----------------------------------------------------
@app.post("/generate-qr")
def generate_qr(request: Request, data: str = Form(...)):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    logo = load_logo()
    img = paste_logo(img, logo)

    os.makedirs("static", exist_ok=True)
    img.save("static/qr.png")

    return templates.TemplateResponse("result.html", {
        "request": request,
        "image": "/static/qr.png"
    })


# ----------------------------------------------------
# API QR GENERATION (RETURN IMAGE)
# ----------------------------------------------------
@app.post("/api/generate-qr")
def api_generate_qr(
    data: str = Form(...),
    logo: str = Form(None),
    file: UploadFile = File(None)
):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    logo_img = load_logo(logo, file)
    img = paste_logo(img, logo_img)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/png")


# ----------------------------------------------------
# SSR BARCODE GENERATION
# ----------------------------------------------------
@app.post("/generate-barcode")
def generate_barcode(request: Request, data: str = Form(...)):
    barcode = Code128(data, writer=ImageWriter())
    os.makedirs("static", exist_ok=True)
    barcode.save("static/barcode")

    return templates.TemplateResponse("result.html", {
        "request": request,
        "image": "/static/barcode.png"
    })


# ----------------------------------------------------
# API BARCODE GENERATION
# ----------------------------------------------------
@app.post("/api/generate-barcode")
def api_generate_barcode(data: str = Form(...)):
    barcode = Code128(data, writer=ImageWriter())

    buffer = BytesIO()
    barcode.write(buffer)
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/png")


# ----------------------------------------------------
# API WIFI QR GENERATION (WITH OPTIONAL LOGO)
# ----------------------------------------------------
@app.post("/api/generate-wifi-qr")
def api_generate_wifi_qr(
    ssid: str = Form(...),
    password: str = Form(...),
    security: str = Form("WPA"),
    logo: str = Form(None),
    file: UploadFile = File(None)
):
    wifi_data = f"WIFI:S:{ssid};T:{security};P:{password};;"

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(wifi_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    logo_img = load_logo(logo, file)
    img = paste_logo(img, logo_img)

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/png")


# ----------------------------------------------------
# ADMIN LOGIN (LOG VISITOR INFO)
# ----------------------------------------------------
def get_client_ip(request: Request):
    # If behind proxy (Cloudflare, nginx, etc.)
    ip = request.headers.get("x-forwarded-for")
    if ip:
        return ip.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


# ----------------------------------------------------
# ADMIN LOGIN PAGE (SHOW FORM)
# ----------------------------------------------------
@app.get("/admin/login")
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})


# ----------------------------------------------------
# ADMIN LOGIN SUBMIT (LOG + REDIRECT)
# ----------------------------------------------------
@app.post("/admin/login")
def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        time = datetime.datetime.now().isoformat()

        # ISP info
        isp_info = {}
        try:
            resp = requests.get(f"https://ipinfo.io/{ip}/json", timeout=3)
            if resp.status_code == 200:
                isp_info = resp.json()
        except:
            isp_info = {}

        record = {
            "time": time,
            "ip": ip,
            "device": user_agent,
            "isp": isp_info.get("org"),
            "city": isp_info.get("city"),
            "region": isp_info.get("region"),
            "country": isp_info.get("country"),
            "username": username
        }

        os.makedirs("logs", exist_ok=True)

        with open("logs/admin-login-attempts.jsonl", "a") as f:
            f.write(json.dumps(record) + "\n")

    except Exception as e:
        print("Logging error:", e)

    # redirect to dashboard
    return RedirectResponse(url="/admin/dashboard", status_code=302)

@app.get("/admin/dashboard")
def admin_dashboard(request: Request):
    logs = []

    log_file = "logs/admin-login-attempts.jsonl"

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            for line in f:
                try:
                    logs.append(json.loads(line))
                except:
                    pass

    # newest first
    logs = list(reversed(logs))

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "logs": logs
        }
    )