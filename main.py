from fastapi import FastAPI, Request, Form
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

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# ----------------------------------------------------
# SSR PAGES
# ----------------------------------------------------
@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/docss")
def docs(request: Request):
    return templates.TemplateResponse("documentation.html", {"request": request})

# ----------------------------------------------------
# QR GENERATION (SSR Form)
# ----------------------------------------------------
@app.post("/generate-qr")
def generate_qr(request: Request, data: str = Form(...)):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Add default logo if exists
    if os.path.exists("static/logo.png"):
        logo = Image.open("static/logo.png")
        logo = logo.resize((60, 60))

        pos = (
            (img.size[0] - logo.size[0]) // 2,
            (img.size[1] - logo.size[1]) // 2
        )

        img.paste(logo, pos, mask=logo if logo.mode in ("RGBA", "LA") else None)

    img_path = "static/qr.png"
    img.save(img_path)

    return templates.TemplateResponse("result.html", {
        "request": request,
        "image": "/static/qr.png"
    })

# ----------------------------------------------------
# QR GENERATION (REST API) — with optional logo
# ----------------------------------------------------
@app.post("/api/generate-qr")
def api_generate_qr(data: str = Form(...), logo: str = Form(None)):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Load logo (base64 or default)
    logo_img = None

    if logo:
        try:
            logo_data = base64.b64decode(logo)
            logo_img = Image.open(BytesIO(logo_data))
        except:
            logo_img = None

    if logo_img is None and os.path.exists("static/logo.png"):
        logo_img = Image.open("static/logo.png")

    # Paste logo if available
    if logo_img:
        logo_img = logo_img.resize((60, 60))

        pos = (
            (img.size[0] - logo_img.size[0]) // 2,
            (img.size[1] - logo_img.size[1]) // 2
        )

        img.paste(
            logo_img,
            pos,
            mask=logo_img if logo_img.mode in ("RGBA", "LA") else None
        )

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/png")

# ----------------------------------------------------
# BARCODE GENERATION (SSR)
# ----------------------------------------------------
@app.post("/generate-barcode")
def generate_barcode(request: Request, data: str = Form(...)):
    barcode = Code128(data, writer=ImageWriter())
    img_path = "static/barcode"
    barcode.save(img_path)

    return templates.TemplateResponse("result.html", {
        "request": request,
        "image": "/static/barcode.png"
    })

# ----------------------------------------------------
# BARCODE GENERATION (REST API)
# ----------------------------------------------------
@app.post("/api/generate-barcode")
def api_generate_barcode(data: str = Form(...)):
    barcode = Code128(data, writer=ImageWriter())

    buffer = BytesIO()
    barcode.write(buffer)
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/png")

# ----------------------------------------------------
# WIFI QR GENERATION (API)
# ----------------------------------------------------
@app.post("/api/generate-wifi-qr")
def api_generate_wifi_qr(
    ssid: str = Form(...),
    password: str = Form(...),
    security: str = Form("WPA")
):
    wifi_data = f"WIFI:S:{ssid};T:{security};P:{password};;"

    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_H)
    qr.add_data(wifi_data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return Response(content=buffer.getvalue(), media_type="image/png")