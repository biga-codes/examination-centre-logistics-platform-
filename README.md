# Automated examination centre operations platform - end semester project 

## 📋 Project Overview

Automated examination centre operations platform with real-time candidate verification, aadhar/pan/hall-ticket OCR processing, live facial biometric capture, and comprehensive audit trails. Combines computer vision preprocessing, deep learning face matching, fuzzy similarity algorithms, and centralized dashboards for efficient, fraud/impersonation proof setup, This project eliminates the time-consuming manual verification processes and reduces impersonation fraud through biometric validation.

## Website Implementation:
#Home Page
<img width="1903" height="919" alt="Screenshot 2026-03-02 224342" src="https://github.com/user-attachments/assets/24594e33-bcfb-4985-b437-d3ff3f2f0ed1" />
# Candidate Face Verification/Live web camera capture/ OCR and ID verification kiosk + Computer vision pipeline
<img width="1789" height="893" alt="Screenshot 2026-03-02 224300" src="https://github.com/user-attachments/assets/9f26aadd-626e-4f40-88fd-d9c5317055fb" />
#Candidate Detail Registration and Upload to backend Database with various ID choices for upload
<img width="1851" height="873" alt="Screenshot 2026-03-02 224229" src="https://github.com/user-attachments/assets/7f154f53-38e3-4bdf-89e2-f09800b5a241" />
#Webcamera Image Capture
<img width="1670" height="981" alt="image" src="https://github.com/user-attachments/assets/a83228ea-bb3b-4199-9ee9-69d3ba0559b7" />



## 🎯 Purpose

Traditional examination centre entry procedures involve extensive manual checks of identity documents and hall tickets, leading to:

- Long queues and significant delays
- Human errors in verification
- Difficulty handling large volumes of candidates
- Increased risk of malpractice due to inadequate scrutiny

## ✨ Key Features

- **🔍 Automated OCR Text Extraction**: Extracts candidate information from hall tickets, Aadhaar cards, and other ID documents using Tesseract OCR
- **👤 Facial Recognition**: Compares live candidate photos with reference images stored in the database
- **📊 Real-time Verification Dashboard**: Web-based interface for managing candidate records and verification status
- **🗄️ Centralized Database**: SQLite-based storage for candidate records, verification attempts, and audit logs
- **🔐 Secure & Audit-Friendly**: All verification attempts are logged with timestamps for traceability
- **⚡ Fast Processing**: Reduces verification time from minutes to seconds per candidate
- **🎯 Fuzzy Matching**: Handles OCR errors using similarity metrics (RapidFuzz/Levenshtein) for robust text matching

 
## 🏗️ System Architecture

The system follows a multi-stage verification pipeline:

<img width="1334" height="701" alt="image" src="https://github.com/user-attachments/assets/3a9c1608-8e93-4469-b91f-6331549ed2a0" />


1. **Image Capture**: ID documents and live photos captured via camera/webcam
2. **Preprocessing**: Image enhancement, denoising, and preparation using OpenCV
3. **Text Extraction**: OCR engine extracts text from preprocessed ID images
4. **Data Normalization**: Fuzzy text correction handles spelling errors and formatting
5. **Facial Recognition**: Features extracted from live photo and compared with stored data
6. **Database Verification**: Cross-references extracted data with SQLite records
7. **Decision & Logging**: Returns ACCEPTED/REJECTED status with audit trail

## 🛠️ Technology Stack

- **Backend**: Python, Flask
- **Database**: SQLite with SQLAlchemy ORM
- **Computer Vision**: OpenCV (cv2)
- **OCR**: Tesseract (pytesseract)
- **Image Processing**: Pillow (PIL)
- **Text Matching**: RapidFuzz (fuzzy string matching)

---

# Testing & Setup Guide

This guide covers how to set up, configure, and run the mod1 application.

## Prerequisites

### System Requirements
- Python 3.8 or higher
- PowerShell Terminal on VS Code
- SQLite3

### Required Libraries

Install all dependencies using pip:

```bash
pip install flask sqlalchemy pytesseract pillow opencv-python rapidfuzz
```

Or use the requirements file:

```bash
pip install -r requirements.txt
```

### PowerShell Execution Policy (Windows Only)

If you encounter execution policy restrictions on Windows, run:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/biga-codes/mod1.git
cd mod1
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Database Initialization

Initialize the local SQLite databases from the **root directory** before the first run:

```bash
python website/create_db.py
python website/create_verify_db.py
```

This creates:
- `*.db` - Local SQLite instances storing verification records and user data

## Running the Application

### Starting the Flask Server

**Important:** You must navigate into the `website` directory so that template and static paths resolve correctly:

```bash
# Navigate into the website folder
cd website

# Launch the Flask server
python app.py
```

### Server Details

- Access the UI at: **http://127.0.0.1:5000/**
- The application runs on port 5000 by default

## Project Structure

| File/Folder | Description |
|-------------|-------------|
| `website/app.py` | Main Flask entry point and API route definitions |
| `website/templates/` | Jinja2 templates for the Home, Candidate, and Report views |
| `website/static/` | Contains the futuristic CSS `style.css` and local assets |
| `uploads/ocr/` | Storage for sensitive candidate documents |
| `*.db` | Local SQLite instances storing verification records and user data |

## Running Tests

### Manual Testing

1. Navigate to the website directory:
   ```bash
   cd website
   ```

2. Start the application:
   ```bash
   python app.py
   ```

3. Open your browser and navigate to:
   ```
   http://127.0.0.1:5000/
   ```

4. Test the following features:
   - Home page loads correctly
   - Candidate verification functionality
   - Document upload and OCR processing
   - Report generation

### API Testing

You can test the API endpoints using tools like:
- cURL
- Postman
- HTTPie

Example:
```bash
curl http://127.0.0.1:5000/api/endpoint
```

## Troubleshooting

### Common Issues

**1. Module Not Found Error**
```
ModuleNotFoundError: No module named 'flask'
```
**Solution:** Install dependencies:
```bash
pip install flask sqlalchemy pytesseract pillow opencv-python rapidfuzz
```

**2. Template Not Found Error**
```
TemplateNotFoundError: template.html
```
**Solution:** Make sure you're running `python app.py` from the `website/` directory:
```bash
cd website
python app.py
```

**3. Database Error**
```
sqlite3.OperationalError: no such table
```
**Solution:** Initialize databases from the root directory:
```bash
cd ..  # Go back to root
python website/create_db.py
python website/create_verify_db.py
```

**4. Port Already in Use**
```
OSError: [Errno 48] Address already in use
```
**Solution:** Kill the process using port 5000 or change the port in `app.py`

## Security & Data Privacy

⚠️ **Security Notes:**
- Ensure proper access controls are in place for production deployments
- Never commit sensitive documents or database files to version control

## Development Workflow

1. **Make changes** to the code
2. **Navigate to website directory**: `cd website`
3. **Run the application**: `python app.py`
4. **Test your changes** in the browser
5. **Stop the server**: Press `Ctrl+C`

## Additional Resources

- Flask Documentation: https://flask.palletsprojects.com/
- SQLAlchemy Documentation: https://docs.sqlalchemy.org/
- Tesseract OCR: https://github.com/tesseract-ocr/tesseract

## Support

For issues or questions, please open an issue on the GitHub repository:
https://github.com/biga-codes/mod1/issues

