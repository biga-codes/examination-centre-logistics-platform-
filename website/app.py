from pydoc import html

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from pathlib import Path
import sqlite3
import os
import base64
import numpy as np
from datetime import datetime, timezone
from flask import make_response
import io

from Testroute import preprocess_webcam_image
from Untitled_1 import OCREngine, UserDatabase, IDVerifier
from Untitled_2 import StudentVerifier, InsightFaceEngine

BASE = Path(__file__).parent
UPLOAD_DIR = BASE / "uploads"
OCR_DIR = UPLOAD_DIR / "ocr"
FACE_REF_DIR = UPLOAD_DIR / "facever"
FACE_ATTEMPT_DIR = UPLOAD_DIR / "face_attempts"
VERIFY_DB = BASE / "verify.db"
USERS_DB_URL = f"sqlite:///{BASE / 'users.db'}"

for d in (UPLOAD_DIR, OCR_DIR, FACE_REF_DIR, FACE_ATTEMPT_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = "dev-secret"

# shared InsightFace engine (loaded once at startup) 
face_engine = InsightFaceEngine()

# DB rulezz

def verify_connect():
    conn = sqlite3.connect(VERIFY_DB)
    conn.row_factory = sqlite3.Row
    return conn

def get_verification(cid):
    with verify_connect() as conn:
        cur = conn.execute("SELECT * FROM verifications WHERE candidate_id = ?", (cid,))
        row = cur.fetchone()
        return dict(row) if row else None

def upsert_verification(cid, status=None, ocr_value=None, db_value=None,
                        ocr_path=None, face_score=None,
                        face_path=None, face_attempt_path=None):
    now = datetime.now(timezone.utc).isoformat()
    with verify_connect() as conn:
        cur = conn.execute("SELECT 1 FROM verifications WHERE candidate_id = ?", (cid,))
        if cur.fetchone():
            conn.execute("""
                UPDATE verifications
                SET status=?, ocr_value=?, db_value=?, ocr_path=?,
                    face_score=?, face_path=?, face_attempt_path=?, last_update=?
                WHERE candidate_id=?
            """, (status, ocr_value, db_value, ocr_path,
                  face_score, face_path, face_attempt_path, now, cid))
        else:
            conn.execute("""
                INSERT INTO verifications
                    (candidate_id, status, ocr_value, db_value, ocr_path,
                     face_score, face_path, face_attempt_path, last_update)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (cid, status, ocr_value, db_value, ocr_path,
                  face_score, face_path, face_attempt_path, now))
        conn.commit()

def _merge_status(ocr_status, face_status):
    """Both must be PASS for overall PASS."""
    if ocr_status == "PASS" and face_status == "PASS":
        return "PASS"
    if ocr_status in (None, "PENDING") and face_status in (None, "PENDING"):
        return "PENDING"
    return "FAIL"

def get_user_record(uid):
    db = UserDatabase(USERS_DB_URL)
    try:
        return db.get_user_id_record(uid)
    except Exception:
        return None

#APIRoutes 

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard", methods=["POST"])
def dashboard():
    cid = request.form.get("candidate_id")
    try:
        cid_int = int(cid)
    except Exception:
        flash("Invalid candidate id")
        return redirect(url_for("index"))
    return redirect(url_for("candidate", cid=cid_int))

@app.route("/candidate/<int:cid>")
def candidate(cid):
    user = get_user_record(cid) or {}
    verification = get_verification(cid) or {}
    display = {
        "candidate_id": cid,
        "name": user.get("name") if isinstance(user, dict) else "",
        "id_type": user.get("id_type"),
        "id_value": user.get("id_value"),
        "status": verification.get("status"),
        "ocr_value": verification.get("ocr_value"),
        "face_path": verification.get("face_path"),
        "face_attempt_path": verification.get("face_attempt_path"),
        "face_score": verification.get("face_score"),
    }
    return render_template("candidate.html", candidate=display)

# OCR 

@app.route("/api/ocr", methods=["POST"])
def api_ocr():
    cid = int(request.form.get("candidate_id"))
    file = request.files.get("ocr_file")
    if not file:
        flash("No file uploaded for OCR")
        return redirect(url_for("candidate", cid=cid))

    filename = f"{cid}_ocr_{int(datetime.utcnow().timestamp())}.jpg"
    path = OCR_DIR / filename
    file.save(path)

    try:
        user_db = UserDatabase(USERS_DB_URL)
        ocr_engine = OCREngine()
        verifier = IDVerifier(user_db, ocr_engine)
        result = verifier.verify(str(path), cid)
        ocr_status = result.get("status")
        ocr_value  = result.get("ocr_value")
        db_value   = result.get("db_value")
    except Exception as e:
        ocr_status = "ERROR"
        ocr_value  = None
        db_value   = None
        flash(f"OCR/verifier error: {e}")

    # Preserve existing face result when recalculating combined status
    existing = get_verification(cid) or {}
    face_status = existing.get("face_status")          # separate sub-status column if you add it
    combined = _merge_status(ocr_status, existing.get("face_score") and
                             ("PASS" if existing.get("face_score", 0) >= 0.4 else "FAIL"))

    upsert_verification(
        cid,
        status=combined,
        ocr_value=ocr_value,
        db_value=db_value,
        ocr_path=str(path),
        face_score=existing.get("face_score"),
        face_path=existing.get("face_path"),
        face_attempt_path=existing.get("face_attempt_path"),
    )
    flash(f"OCR completed — status: {ocr_status}")
    return redirect(url_for("candidate", cid=cid))

    # Preserve existing face result when recalculating combined status
    existing = get_verification(cid) or {}
    face_status = existing.get("face_status")          # separate sub-status column if you add it
    combined = _merge_status(ocr_status, existing.get("face_score") and
                             ("PASS" if existing.get("face_score", 0) >= 0.4 else "FAIL"))

    upsert_verification(
        cid,
        status=combined,
        ocr_value=ocr_value,
        db_value=db_value,
        ocr_path=str(path),
        face_score=existing.get("face_score"),
        face_path=existing.get("face_path"),
        face_attempt_path=existing.get("face_attempt_path"),
    )
    flash(f"OCR completed — status: {ocr_status}")
    return redirect(url_for("candidate", cid=cid))

#  facever  

def _run_face_verification(cid: int, live_image_path: str):
    """
    Compares uploads/facever/<cid>.jpg (pre-placed reference photo) against the
    live image. No DB read required — file naming convention is the source of truth.
    Deliberately does NOT re-run OCR.
    """
    ref_path = FACE_REF_DIR / f"{cid}.jpg"
    if not ref_path.exists():
        return "FAIL", None, f"Reference photo not found at {ref_path}. Place <id>.jpg in uploads/facever/."

    try:
        ref_emb  = face_engine.extract_embedding(str(ref_path))
        live_emb = face_engine.extract_embedding(live_image_path)
        result   = face_engine.compare(ref_emb, live_emb)  # threshold=0.4 default
        face_status = "PASS" if result["match"] else "FAIL"
        return face_status, float(result["similarity"]), None
    except Exception as e:
        return "FAIL", None, str(e)



@app.route("/api/face_attempt", methods=["POST"])
def api_face_attempt():
    cid = int(request.form.get("candidate_id"))

    # determine image source: webcam (base64) or file upload 
    webcam_data = request.form.get("webcam_image")   # base64 data-URL from JS
    face_file   = request.files.get("face_file")

    timestamp = int(datetime.utcnow().timestamp())
    attempt_filename = f"{cid}_attempt_{timestamp}.jpg"
    attempt_path = FACE_ATTEMPT_DIR / attempt_filename
    ''' if webcam_data:
        header, encoded = webcam_data.split(",", 1)
        img_bytes = base64.b64decode(encoded)
        
        # PROCESS HERE before exception place
        processed_bytes = preprocess_webcam_image(img_bytes)
        attempt_path.write_bytes(processed_bytes)'''
    if webcam_data:
        # data:image/...;base64, prefix
        try:
            header, encoded = webcam_data.split(",", 1)
            img_bytes = base64.b64decode(encoded)
            attempt_path.write_bytes(img_bytes)
        except Exception as e:
            flash(f"Failed to decode webcam image: {e}")
            return redirect(url_for("candidate", cid=cid))
    elif face_file:
        face_file.save(attempt_path)
    else:
        flash("No face image provided (upload or webcam)")
        return redirect(url_for("candidate", cid=cid))

    # run face-only verification 
    face_status, similarity, error = _run_face_verification(cid, str(attempt_path))

    if error:
        flash(f"Face verification error: {error}")
    else:
        flash(f"Face verification completed — {face_status} (similarity: {similarity:.3f})")

    #statusscheckkk
    existing   = get_verification(cid) or {}
    ocr_val    = existing.get("ocr_value")
    db_val     = existing.get("db_value")
    if ocr_val is not None and db_val is not None:
        ocr_status = "PASS" if ocr_val == db_val else "FAIL"
    else:
        ocr_status = "PENDING"
    combined = _merge_status(ocr_status, face_status)

    upsert_verification(
        cid,
        status=combined,
        ocr_value=existing.get("ocr_value"),
        db_value=existing.get("db_value"),
        ocr_path=existing.get("ocr_path"),
        face_score=similarity,
        face_path=str(FACE_REF_DIR / f"{cid}.jpg"),
        face_attempt_path=str(attempt_path),
    )
    return redirect(url_for("candidate", cid=cid))

# Manual statuscheckk

@app.route("/api/set_status", methods=["POST"])
def api_set_status():
    cid = int(request.form.get("candidate_id"))
    status = request.form.get("status")
    if status not in ("PASS", "FAIL", "PENDING", "OCR_UPLOADED"):
        flash("Invalid status")
        return redirect(url_for("candidate", cid=cid))
    existing = get_verification(cid) or {}
    upsert_verification(
        cid,
        status=status,
        ocr_value=existing.get("ocr_value"),
        db_value=existing.get("db_value"),
        ocr_path=existing.get("ocr_path"),
        face_score=existing.get("face_score"),
        face_path=existing.get("face_path"),
        face_attempt_path=existing.get("face_attempt_path"),
    )
    flash(f"Status manually set to {status}")
    return redirect(url_for("candidate", cid=cid))

@app.route("/next/<int:cid>")
def next_candidate(cid):
    return redirect(url_for("candidate", cid=cid + 1))



@app.route("/report")
def report():
    users_db_path = BASE / "users.db"
    users = []
    import sqlite3 as _sqlite
    with _sqlite.connect(users_db_path) as conn:
        conn.row_factory = _sqlite.Row
        cur = conn.execute("SELECT user_id, id_type, id_value FROM users ORDER BY user_id")
        for r in cur.fetchall():
            users.append({"user_id": r["user_id"], "id_type": r["id_type"], "id_value": r["id_value"]})

    verifs = {}
    with verify_connect() as conn:
        cur = conn.execute("SELECT * FROM verifications")
        for r in cur.fetchall():
            verifs[r["candidate_id"]] = dict(r)

    rows = []
    total = passed = failed = 0
    for u in users:
        uid = u["user_id"]
        v = verifs.get(uid, {})
        status = v.get("status") or "PENDING"
        if status == "PASS":  passed += 1
        if status == "FAIL":  failed += 1
        total += 1

        lu = v.get("last_update")
        if lu:
            try:
                parsed = datetime.fromisoformat(lu)
                formatted_lu = (parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                                if parsed.tzinfo else parsed.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                formatted_lu = lu
        else:
            formatted_lu = None

        rows.append({
            "user_id":    uid,
            "id_type":    u.get("id_type"),
            "id_value":   u.get("id_value"),
            "status":     status,
            "ocr_value":  v.get("ocr_value"),
            "face_score": round(v["face_score"], 3) if v.get("face_score") is not None else None,
            "last_update": formatted_lu,
        })

    pass_pct = round(passed / total * 100, 1) if total else 0
    fail_pct = round(failed / total * 100, 1) if total else 0
    return render_template("report.html", rows=rows, pass_pct=pass_pct, fail_pct=fail_pct)
#.
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("registration.html")

    # collect fields
    name    = request.form.get("candidate_name", "").strip()
    gmail   = request.form.get("gmail", "").strip()
    id_value = request.form.get("id_value", "").strip()
    id_type  = request.form.get("id_type",  "aadhaar").strip()

    # auto-assign next candidate ID
    import sqlite3 as _sq
    with _sq.connect(BASE / "users.db") as conn:
        row = conn.execute("SELECT MAX(user_id) FROM users").fetchone()
        cid = (row[0] or 0) + 1
        conn.execute(
            "INSERT INTO users (user_id, id_type, id_value, name, gmail) VALUES (?, ?, ?, ?, ?)",
            (cid, id_type, id_value, name, gmail)
        )
        conn.commit()

    # save OCR image → uploads/ocr/<cid>.jpg
    ocr_webcam = request.form.get("ocr_webcam")
    ocr_file   = request.files.get("ocr_file")
    ocr_path   = OCR_DIR / f"{cid}.jpg"
    if ocr_webcam:
        _, enc = ocr_webcam.split(",", 1)
        ocr_path.write_bytes(base64.b64decode(enc))
    elif ocr_file:
        ocr_file.save(ocr_path)

    # save face image → uploads/facever/<cid>.jpg
    face_webcam = request.form.get("face_webcam")
    face_file   = request.files.get("face_file")
    face_path   = FACE_REF_DIR / f"{cid}.jpg"
    if face_webcam:
        _, enc = face_webcam.split(",", 1)
        face_path.write_bytes(base64.b64decode(enc))
    elif face_file:
        face_file.save(face_path)

    flash(f"Candidate registered with ID {cid}", "success")
   # return redirect(url_for("candidate", cid=cid))
    return render_template("registration.html", registered_cid=cid)

@app.route("/hallticket/<int:cid>")
def hallticket(cid):
    # Fetch candidate info
    import sqlite3 as _sq
    with _sq.connect(BASE / "users.db") as conn:
        conn.row_factory = _sq.Row
        user = conn.execute("SELECT * FROM users WHERE user_id=?", (cid,)).fetchone()
    if not user:
        flash("Candidate not found")
        return redirect(url_for("index"))

    # Load photos as base64 for embedding in HTML
    def img_b64(path):
        p = Path(path)
        if p.exists():
            data = p.read_bytes()
            return "data:image/jpeg;base64," + base64.b64encode(data).decode()
        return ""

    face_img = img_b64(FACE_REF_DIR / f"{cid}.jpg")
    ocr_img  = img_b64(OCR_DIR      / f"{cid}.jpg")

    name     = user["name"]    if "name"    in user.keys() else "—"
    aadhaar  = user["id_value"] or "—"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: 'Inter', Arial, sans-serif;
    background: #fff;
    color: #111;
    padding: 0;
  }}

  .page {{
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto;
    padding: 12mm 14mm;
  }}

  /* Header */
  .header {{
    display: flex;
    align-items: center;
    border-bottom: 3px solid #1a3c8f;
    padding-bottom: 10px;
    margin-bottom: 10px;
    gap: 16px;
  }}
  .header-logo {{
    width: 64px; height: 64px;
    background: #1a3c8f;
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-size: 22px; font-weight: 700; letter-spacing: 1px;
    flex-shrink: 0;
  }}
  .header-text h1 {{
    font-size: 18px; font-weight: 700; color: #1a3c8f; letter-spacing: 0.03em;
  }}
  .header-text p {{
    font-size: 12px; color: #555; margin-top: 2px;
  }}
  .header-badge {{
    margin-left: auto;
    background: #1a3c8f;
    color: #fff;
    padding: 6px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.05em;
    flex-shrink: 0;
  }}

  /* Hall ticket title */
  .ticket-title {{
    text-align: center;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #1a3c8f;
    border: 2px solid #1a3c8f;
    padding: 6px;
    margin-bottom: 14px;
    background: #eef2ff;
  }}

  /* Main body: info left, photos right */
  .body-row {{
    display: flex;
    gap: 16px;
    margin-bottom: 14px;
  }}
  .info-block {{
    flex: 1;
  }}
  .photos-block {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: center;
    flex-shrink: 0;
  }}
  .photo-wrap {{
    text-align: center;
  }}
  .photo-wrap img {{
    width: 90px; height: 110px;
    object-fit: cover;
    border: 2px solid #1a3c8f;
    border-radius: 4px;
    display: block;
  }}
  .photo-wrap .photo-label {{
    font-size: 9px;
    color: #555;
    margin-top: 3px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .photo-placeholder {{
    width: 90px; height: 110px;
    background: #f0f0f0;
    border: 2px dashed #aaa;
    border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; color: #aaa; text-align: center;
  }}

  /* Info table */
  table.info {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12.5px;
  }}
  table.info td {{
    padding: 6px 8px;
    border: 1px solid #d0d7e8;
    vertical-align: top;
  }}
  table.info td.lbl {{
    background: #eef2ff;
    font-weight: 600;
    color: #1a3c8f;
    width: 38%;
    white-space: nowrap;
  }}
  table.info td.val {{
    color: #111;
    font-weight: 500;
  }}

  /* Exam details box */
  .exam-box {{
    border: 2px solid #1a3c8f;
    border-radius: 6px;
    overflow: hidden;
    margin-bottom: 14px;
  }}
  .exam-box-title {{
    background: #1a3c8f;
    color: #fff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 5px 12px;
  }}
  .exam-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    font-size: 12.5px;
  }}
  .exam-cell {{
    padding: 7px 12px;
    border-right: 1px solid #d0d7e8;
    border-bottom: 1px solid #d0d7e8;
  }}
  .exam-cell:nth-child(even) {{ border-right: none; }}
  .exam-cell .ec-label {{
    font-size: 10px;
    color: #1a3c8f;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    margin-bottom: 2px;
  }}
  .exam-cell .ec-val {{
    font-weight: 600;
    color: #111;
  }}

  /* Address box */
  .addr-box {{
    border: 1px solid #d0d7e8;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 14px;
    font-size: 12px;
    color: #555;
    background: #fafafa;
  }}
  .addr-box .addr-label {{
    font-size: 10px;
    font-weight: 700;
    color: #1a3c8f;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
  }}

  /* Instructions */
  .instructions {{
    border: 1px solid #f0c040;
    background: #fffbea;
    border-radius: 6px;
    padding: 10px 14px;
    margin-bottom: 14px;
    font-size: 11px;
    color: #555;
  }}
  .instructions b {{ color: #b45309; }}
  .instructions ol {{ padding-left: 16px; margin-top: 4px; }}
  .instructions li {{ margin-bottom: 3px; }}

  /* Signature row */
  .sig-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-top: 10px;
    font-size: 11px;
    color: #555;
  }}
  .sig-box {{
    text-align: center;
  }}
  .sig-line {{
    width: 140px;
    border-top: 1px solid #333;
    margin: 28px auto 4px;
  }}

  /* Footer */
  .footer {{
    border-top: 2px solid #1a3c8f;
    margin-top: 14px;
    padding-top: 6px;
    font-size: 10px;
    color: #888;
    text-align: center;
  }}
</style>
</head>
<body>
<div class="page">

  <!-- Header -->
  <div class="header">
    <div class="header-logo">EVS</div>
    <div class="header-text">
      <h1>Exam Verification System</h1>
      <p>Conducting Body &bull; National Examination Authority</p>
    </div>
    <div class="header-badge">ADMIT CARD</div>
  </div>

  <!-- Title -->
  <div class="ticket-title">Hall Ticket &mdash; Examination Admit Card</div>

  <!-- Body: info + photos -->
  <div class="body-row">
    <div class="info-block">
      <table class="info">
        <tr>
          <td class="lbl">Candidate ID</td>
          <td class="val" style="font-family:monospace; font-size:14px; letter-spacing:0.05em;">{cid}</td>
        </tr>
        <tr>
          <td class="lbl">Candidate Name</td>
          <td class="val">{name}</td>
        </tr>
        <tr>
          <td class="lbl">Aadhaar Number</td>
          <td class="val" style="font-family:monospace;">{aadhaar}</td>
        </tr>
        <tr>
          <td class="lbl">Examination</td>
          <td class="val">Graduate Aptitude Test in Engineering (EVS-2025)</td>
        </tr>
        <tr>
          <td class="lbl">Paper / Subject</td>
          <td class="val">Computer Science &amp; Information Technology (CS)</td>
        </tr>
        <tr>
          <td class="lbl">Address</td>
          <td class="val" style="color:#aaa;">123 Main Street, City, State &mdash; 000000<br><span style="font-size:10px;">(placeholder)</span></td>
        </tr>
      </table>
    </div>

    <!-- Photos -->
    <div class="photos-block">
      <div class="photo-wrap">
        {"<img src='" + face_img + "'>" if face_img else "<div class='photo-placeholder'>No Face<br>Photo</div>"}
        <div class="photo-label">Face Photo</div>
      </div>
      <div class="photo-wrap">
        {"<img src='" + ocr_img + "'>" if ocr_img else "<div class='photo-placeholder'>No ID<br>Photo</div>"}
        <div class="photo-label">ID Document</div>
      </div>
    </div>
  </div>

  <!-- Exam details -->
  <div class="exam-box">
    <div class="exam-box-title">Examination Schedule</div>
    <div class="exam-grid">
      <div class="exam-cell">
        <div class="ec-label">Exam Name</div>
        <div class="ec-val">EVS Graduate Aptitude Test 2025</div>
      </div>
      <div class="exam-cell">
        <div class="ec-label">Exam Date</div>
        <div class="ec-val">15 February 2025</div>
      </div>
      <div class="exam-cell">
        <div class="ec-label">Reporting Time</div>
        <div class="ec-val">08:30 AM</div>
      </div>
      <div class="exam-cell">
        <div class="ec-label">Exam Time</div>
        <div class="ec-val">09:30 AM &ndash; 12:30 PM</div>
      </div>
      <div class="exam-cell" style="grid-column: 1/-1;">
        <div class="ec-label">Venue</div>
        <div class="ec-val">Examination Hall No. 4, Block B &mdash; National University Campus, Main Road, City &mdash; 000000 &nbsp;<span style="color:#aaa; font-weight:400; font-size:11px;">(placeholder)</span></div>
      </div>
    </div>
  </div>

  <!-- Address -->
  <div class="addr-box">
    <div class="addr-label">Correspondence Address</div>
    123 Main Street, Locality, City, State &mdash; PIN 000000 &nbsp;<span style="color:#bbb;">(placeholder)</span>
  </div>

  <!-- Instructions -->
  <div class="instructions">
    <b>Important Instructions:</b>
    <ol>
      <li>Candidates must bring this hall ticket along with a valid photo ID to the examination centre.</li>
      <li>Mobile phones, electronic gadgets, and calculators are strictly prohibited inside the exam hall.</li>
      <li>Candidates must report at least 30 minutes before the scheduled exam time.</li>
      <li>Entry will not be allowed after the exam commences. No exceptions will be made.</li>
      <li>This hall ticket is valid only with a government-issued photo ID proof.</li>
    </ol>
  </div>

  <!-- Signatures -->
  <div class="sig-row">
    <div class="sig-box">
      <div class="sig-line"></div>
      Candidate's Signature
    </div>
    <div style="font-size:10px; color:#aaa; text-align:center;">
      Generated by Exam Verification System<br>
      This is a computer-generated document.
    </div>
    <div class="sig-box">
      <div class="sig-line"></div>
      Invigilator's Signature
    </div>
  </div>

  <!-- Footer -->
  <div class="footer">
    Exam Verification System &bull; Candidate ID: {cid} &bull; This document is system-generated and valid without physical signature.
  </div>

</div>
</body>
</html>"""

    try:
        
        from xhtml2pdf import pisa
        import io

        def generate_pdf(html_content):
            pdf_buffer = io.BytesIO()
            pisa.CreatePDF(html_content, dest=pdf_buffer)
            return pdf_buffer.getvalue()

        pdf_bytes = generate_pdf(html)
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f"inline; filename=hallticket_{cid}.pdf"
        return resp

    except ImportError:
        # fallback: return HTML directly if xhtml2pdf not installed
        return html 

if __name__ == "__main__":
    app.run(debug=True)




















