import os
import sqlite3
from fastapi import FastAPI, Request, UploadFile, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import qrcode
from io import BytesIO
import uvicorn

app = FastAPI()

UPLOAD_FOLDER = "uploads"
GENERATED_FOLDER = "generated"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(GENERATED_FOLDER, exist_ok=True)

# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS pieces(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            piece_code TEXT,
            site TEXT,
            room TEXT,
            status TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------- HOME REDIRECT ----------------

@app.get("/")
def home():
    return RedirectResponse("/admin")

# ---------------- ADMIN PAGE ----------------

@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return """
    <h2>Levi Interiors - Admin Panel</h2>
    <form action="/upload" method="post" enctype="multipart/form-data">
        <input name="site" placeholder="Site Code (S01)" required><br><br>
        <input name="room" placeholder="Room (KITCHEN)" required><br><br>
        <input type="file" name="file" required><br><br>
        <button type="submit">Generate QR PDF</button>
    </form>
    """

# ---------------- PDF UPLOAD + QR INJECTION ----------------

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

        # Save to DB
        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO pieces (piece_code, site, room, status) VALUES (?, ?, ?, ?)",
            (piece_code, site, room, "CUTTING")
        )
        conn.commit()
        conn.close()

        # Generate QR
        qr = qrcode.make(f"{base_url}scan/{piece_code}")
        qr_buffer = BytesIO()
        qr.save(qr_buffer)
        qr_buffer.seek(0)

        # Create overlay
        packet = BytesIO()
        can = canvas.Canvas(packet)
        can.drawInlineImage(qr_buffer, 450, 50, 100, 100)
        can.save()
        packet.seek(0)

        overlay_pdf = PdfReader(packet)
        page = reader.pages[i]
        page.merge_page(overlay_pdf.pages[0])
        writer.add_page(page)

    output_path = os.path.join(GENERATED_FOLDER, f"{site}_{room}_QR.pdf")

    with open(output_path, "wb") as f:
        writer.write(f)

    return FileResponse(output_path, media_type="application/pdf", filename="QR_Stickers.pdf")

# ---------------- SCAN PAGE ----------------

@app.get("/scan/{piece_code}", response_class=HTMLResponse)
def scan_page(piece_code: str):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT status FROM pieces WHERE piece_code=?", (piece_code,))
    result = c.fetchone()
    conn.close()

    status = result[0] if result else "Not Found"

    return f"""
    <h2>Piece: {piece_code}</h2>
    <h3>Status: {status}</h3>

    <form action="/update-status" method="post">
        <input type="hidden" name="piece_code" value="{piece_code}">
        <button name="status" value="QC_DONE">QC Done</button>
        <button name="status" value="DISPATCHED">Dispatched</button>
        <button name="status" value="INSTALLED">Installed</button>
        <button name="status" value="MISSING">Missing</button>
    </form>
    """

# ---------------- UPDATE STATUS ----------------

@app.post("/update-status")
def update_status(piece_code: str = Form(...), status: str = Form(...)):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE pieces SET status=? WHERE piece_code=?", (status, piece_code))
    conn.commit()
    conn.close()

    return HTMLResponse(f"""
    <h3>Status Updated Successfully</h3>
    <a href="/scan/{piece_code}">Go Back</a>
    """)

# ---------------- RENDER PORT FIX ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
