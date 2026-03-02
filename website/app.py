from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from pathlib import Path
import sqlite3
import os
import base64
import numpy as np
from datetime import datetime, timezone

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

    if webcam_data:
        # Strip the data:image/...;base64, prefix
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


if __name__ == "__main__":
    app.run(debug=True)




















