import os
import sqlite3
from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import qrcode
from io import BytesIO

app = FastAPI()
templates = Jinja2Templates(directory="templates")

UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)
os.makedirs("templates", exist_ok=True)

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS pieces(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        piece_code TEXT,
        site TEXT,
        room TEXT,
        status TEXT
    )""")
    conn.commit()
    conn.close()

init_db()

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.post("/upload")
async def upload_pdf(request: Request, site: str = Form(...), room: str = Form(...), file: UploadFile = None):
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())

    reader = PdfReader(file_path)
    writer = PdfWriter()
    base_url = str(request.base_url)

    for i in range(len(reader.pages)):
        piece_code = f"LI-{site}-{room}-P{str(i+1).zfill(3)}"

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("INSERT INTO pieces (piece_code, site, room, status) VALUES (?, ?, ?, ?)",
                  (piece_code, site, room, "CUTTING"))
        conn.commit()
        conn.close()

        qr = qrcode.make(f"{base_url}scan/{piece_code}")
        qr_buffer = BytesIO()
        qr.save(qr_buffer)
        qr_buffer.seek(0)

        packet = BytesIO()
        can = canvas.Canvas(packet)
        can.drawInlineImage(qr_buffer, 450, 50, 100, 100)
        can.save()
        packet.seek(0)

        overlay = PdfReader(packet)
        page = reader.pages[i]
        page.merge_page(overlay.pages[0])
        writer.add_page(page)

    output_path = os.path.join(GENERATED_FOLDER, f"{site}_{room}_QR.pdf")
    with open(output_path, "wb") as f:
        writer.write(f)

    return FileResponse(output_path, media_type='application/pdf', filename="QR_Stickers.pdf")

@app.get("/scan/{piece_code}", response_class=HTMLResponse)
def scan_page(request: Request, piece_code: str):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT status FROM pieces WHERE piece_code=?", (piece_code,))
    result = c.fetchone()
    conn.close()

    status = result[0] if result else "Not Found"

    return HTMLResponse(f"""
    <h2>{piece_code}</h2>
    <h3>Status: {status}</h3>
    <form action="/update-status" method="post">
        <input type="hidden" name="piece_code" value="{piece_code}">
        <button name="status" value="QC_DONE">QC Done</button>
        <button name="status" value="DISPATCHED">Dispatched</button>
        <button name="status" value="INSTALLED">Installed</button>
        <button name="status" value="MISSING">Missing</button>
    </form>
    """)

@app.post("/update-status")
def update_status(piece_code: str = Form(...), status: str = Form(...)):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE pieces SET status=? WHERE piece_code=?", (status, piece_code))
    conn.commit()
    conn.close()
    return {"status": "Updated"}
