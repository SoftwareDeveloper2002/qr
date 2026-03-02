from fastapi import FastAPI, Request, Form, File, UploadFile
from fastapi.responses import Response, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from service import (
    generate_qr,
    redirect_qr_service,
    get_qr_stats,
    edit_qr_service,
    delete_qr_service,
    generate_barcode,
    generate_wifi_qr,
    create_api_key_service,
    list_qr,
    search_qr,
    daily_report,
    restore_qr_service,
    add_qr_tag,
    get_qr_tags,
    create_contact_qr,
)

app = FastAPI(docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/docs")
def docs(request: Request):
    return templates.TemplateResponse("documentation.html", {"request": request})


@app.get("/dashboard")
def dashboard(request: Request):
    stats = daily_report()
    return templates.TemplateResponse("dashboard.html", {"request": request, "stats": stats})


@app.exception_handler(StarletteHTTPException)
async def custom_404_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
    return HTMLResponse(str(exc.detail), status_code=exc.status_code)


# ----------------------------------------------------
# API KEY
# ----------------------------------------------------
@app.post("/api/key/create")
def create_key(owner: str = Form(...), limit: int = Form(5000)):
    return create_api_key_service(owner, limit)


# ----------------------------------------------------
# QR GENERATION
# ----------------------------------------------------
@app.post("/api/generate-qr")
def api_generate_qr(
    data: str = Form(...),
    expires_in: int = Form(None),
    password: str = Form(None),
    logo: str = Form(None),
    file: UploadFile = File(None),
    request: Request = None,
):
    return generate_qr(data, expires_in, password, logo, file, request)


@app.get("/r/{qr_id}")
def redirect_qr(request: Request, qr_id: str, access_key: str = None):
    return redirect_qr_service(request, qr_id, access_key)


# ----------------------------------------------------
# ANALYTICS
# ----------------------------------------------------
@app.get("/api/qr/{qr_id}/stats")
def qr_stats(qr_id: str):
    return get_qr_stats(qr_id)


@app.get("/api/qr/export")
def export():
    return export_stats()


# ----------------------------------------------------
# LIST / SEARCH
# ----------------------------------------------------
@app.get("/api/qr/list")
def list_all():
    return list_qr()


@app.get("/api/qr/search")
def search(query: str):
    return search_qr(query)


# ----------------------------------------------------
# TAGS
# ----------------------------------------------------
@app.post("/api/qr/{qr_id}/tag")
def tag_qr(qr_id: str, tag: str = Form(...)):
    return add_qr_tag(qr_id, tag)


@app.get("/api/qr/{qr_id}/tags")
def get_tags(qr_id: str):
    return get_qr_tags(qr_id)


# ----------------------------------------------------
# RESTORE
# ----------------------------------------------------
@app.post("/api/qr/{qr_id}/restore")
def restore(qr_id: str):
    return restore_qr_service(qr_id)


# ----------------------------------------------------
# EDIT & DELETE
# ----------------------------------------------------
@app.post("/api/qr/{qr_id}/edit")
def edit_qr(qr_id: str, new_url: str = Form(...)):
    return edit_qr_service(qr_id, new_url)


@app.delete("/api/qr/{qr_id}/delete")
def delete_qr(qr_id: str):
    return delete_qr_service(qr_id)


# ----------------------------------------------------
# BARCODE
# ----------------------------------------------------
@app.post("/api/generate-barcode")
def api_generate_barcode(data: str = Form(...), request: Request = None):
    return generate_barcode(data, request)


# ----------------------------------------------------
# WIFI QR
# ----------------------------------------------------
@app.post("/api/generate-wifi-qr")
def api_generate_wifi_qr(
    ssid: str = Form(...),
    password: str = Form(...),
    security: str = Form("WPA"),
    logo: str = Form(None),
    file: UploadFile = File(None),
    request: Request = None,
):
    return generate_wifi_qr(ssid, password, security, logo, file, request)


# ----------------------------------------------------
# CONTACT QR
# ----------------------------------------------------
@app.post("/api/generate-contact-qr")
def contact_qr(name: str = Form(...), phone: str = Form(...), email: str = Form(...)):
    return create_contact_qr(name, phone, email)