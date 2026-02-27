from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from barcode import Code128
from barcode.writer import ImageWriter

from PIL import Image
from io import BytesIO
import base64
import os
import requests

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
# HELPER: LOAD LOGO FROM SOURCE
# ----------------------------------------------------
def load_logo(logo: str = None, file: UploadFile = None):
    """
    Returns PIL Image or None
    - logo (base64 or URL)
    - file upload
    - fallback to static/logo.png
    """

    # 1) Upload file (highest priority)
    if file:
        return Image.open(file.file).convert("RGBA")

    # 2) Base64 image
    if logo:
        try:
            logo_data = base64.b64decode(logo)
            return Image.open(BytesIO(logo_data)).convert("RGBA")
        except:
            pass

        # 3) URL image
        try:
            resp = requests.get(logo, timeout=5)
            if resp.status_code == 200:
                return Image.open(BytesIO(resp.content)).convert("RGBA")
        except:
            pass

    # 4) Default local logo
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

    # White square background
    white_bg = Image.new("RGBA", (logo_size, logo_size), (255, 255, 255, 255))
    white_bg.paste(logo_img, (0, 0), mask=logo_img)

    # Center position
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
# SSR BARCODE GENERATION (FORM -> RESULT)
# ----------------------------------------------------
@app.post("/generate-barcode")
def generate_barcode(request: Request, data: str = Form(...)):
    barcode = Code128(data, writer=ImageWriter())
    barcode.save("static/barcode")

    return templates.TemplateResponse("result.html", {
        "request": request,
        "image": "/static/barcode.png"
    })


# ----------------------------------------------------
# API BARCODE GENERATION (RETURN IMAGE)
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