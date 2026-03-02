"""
ID VERIFICATION PIPELINE
------------------------
Logic enforced:
- Student must bring the SAME ID type they uploaded earlier (PAN / Aadhaar / etc.)
- We DO NOT try to infer ID type from OCR
- We ONLY extract & match the expected ID type from DB
- Strong-ID → exact match only (after normalization)

Dependencies:
pip install pytesseract pillow opencv-python sqlalchemy rapidfuzz
"""

import re
import cv2
import pytesseract
import numpy as np
from sqlalchemy import create_engine, text
from rapidfuzz import fuzz



# =========================
# 1. ID FORMAT DEFINITIONS
# =========================
class IndianIDFormats:
    PATTERNS = {
        "aadhaar": re.compile(r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b"),
        "aadhar": re.compile(r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b"),
        "pan": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
        "passport": re.compile(r"\b[A-Z][0-9]{7}\b"),
        "voter": re.compile(r"\b[A-Z]{3}[0-9]{7}\b"),
        "name_pattern": re.compile(r"\b[A-Z][a-z]+\s[A-Z][a-z]*\b"),
        "hallticket": re.compile(r"\b[0-9]{10}\b")
    }

    @staticmethod
    def normalize(value: str, id_type: str) -> str:
        value = value.upper().replace(" ", "")
        return value


# =========================
# 2. OCR ENGINE
# =========================
class OCREngine:
    def __init__(self, tesseract_path=None):
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

    def extract_text(self, image_path: str) -> str:
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError("Invalid image path")

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]

        return pytesseract.image_to_string(gray, config="--psm 6")


# =========================
# 3. DATABASE ACCESS
# =========================
class UserDatabase:
    def __init__(self, db_url: str):
        self.engine = create_engine(db_url)

    def get_user_id_record(self, user_id: int):
        """
        DB MUST STORE:
        - id_type  (e.g. 'pan', 'aadhaar')
        - id_value (canonical value uploaded earlier)
        """
        q = text("""
            SELECT id_type, id_value
            FROM users
            WHERE user_id = :uid
        """)

        with self.engine.connect() as conn:
            row = conn.execute(q, {"uid": user_id}).fetchone()

        if row is None:
            raise ValueError("User not found")

        return dict(row._mapping)


# =========================
# 4. ID EXTRACTION (STRICT)
# =========================
class IDExtractor:
    def extract_expected_id(self, ocr_text: str, expected_id_type: str):
        pattern = IndianIDFormats.PATTERNS.get(expected_id_type) #error thrown here check

        if pattern is None:
            raise ValueError(f"Unsupported ID type: {expected_id_type}")

        matches = pattern.findall(ocr_text.upper())
        if not matches:
            return None

        # If multiple found, take the longest / cleanest
        return max(matches, key=len)
    
    def extract_name(self, ocr_text: str):
        pattern = IndianIDFormats.PATTERNS.get("name_pattern")
        # Search the raw text directly to preserve case
        matches = pattern.findall(ocr_text)
        
        return matches[0] if matches else None # Returns the first two Upper-lower words found


# =========================
# 5. VERIFICATION ENGINE
# =========================
class IDVerifier:
    def __init__(self, db: UserDatabase, ocr: OCREngine):
        self.db = db
        self.ocr = ocr
        self.extractor = IDExtractor()

    def verify(self, image_path: str, user_id: int) -> dict:
        # Step 1: Load DB truth
        db_record = self.db.get_user_id_record(user_id)
        expected_type = db_record["id_type"].lower() #error
        expected_value = IndianIDFormats.normalize(
            db_record["id_value"], expected_type
        )

        # Step 2: OCR
        ocr_text = self.ocr.extract_text(image_path)

        # Step 3: Extract ONLY expected ID type
        extracted_id = self.extractor.extract_expected_id(
            ocr_text, expected_type
        )
        #name 
        ocr_name = self.extractor.extract_name(ocr_text)

        if extracted_id is None:
            return {
                "status": "FAIL",
                "reason": "Expected ID not found in image",
                "expected_id_type": expected_type
            }

        extracted_id = IndianIDFormats.normalize(
            extracted_id, expected_type
        )

        # Step 4: Exact match (STRONG ID)
        match = extracted_id == expected_value


        return {
            "status": "PASS" if match else "FAIL",
            "expected_id_type": expected_type,
            "db_value": expected_value,
            "ocr_value": extracted_id,
            "ocr_name": ocr_name,
            "match": match
        }


# =========================
# 6. EXAMPLE USAGE
# =========================
if __name__ == "__main__":
    """
    Example DB row:
    user_id | id_type | id_value
    --------+---------+----------
    101     | pan     | ABCDE1234F
    """

    db = UserDatabase("sqlite:///users.db")
    ocr = OCREngine()
    verifier = IDVerifier(db, ocr)

    result = verifier.verify(
        image_path="trial.png",
        user_id=103
    )

    print(result)
