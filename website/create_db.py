from sqlalchemy import create_engine, text

# This creates a file called users.db in the current folder
engine = create_engine("sqlite:///users.db")

with engine.begin() as conn:
    # Create table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            id_type TEXT NOT NULL,
            id_value TEXT NOT NULL,
            primary_face_path TEXT
        )
                   
    """))

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS user_faces (
            face_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            image_path TEXT NOT NULL,
            embedding BLOB,           -- optional, pre‑computed vector
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        ) """))
    
    conn.execute(text("""ALTER TABLE users ADD COLUMN name TEXT;
"""))
    conn.execute(text("""ALTER TABLE users ADD COLUMN gmail TEXT;
"""))
    
    # Insert a default test user and a batch of Aadhaar users (INSERT OR IGNORE to be idempotent)
    conn.execute(text("""
        INSERT OR IGNORE INTO users (user_id, id_type, id_value) VALUES
        (103, 'aadhaar', '342506531151')
    """))

    # seed 20 additional aadhaar users (IDs 200-219)
    aadhaars = [
        (200, 'aadhaar', '735882193971'),
        (201, 'aadhaar', '342506531151'),
        (202, 'aadhaar', '234500000003'),
        (203, 'aadhaar', '342506531151'),
        (204, 'aadhaar', '735882193971'),
        (205, 'aadhaar', '342506531151'),
        (206, 'aadhaar', '735882193971'),
        (207, 'aadhaar', '735882193971'),
        (208, 'aadhaar', '9147385602'),
        (209, 'aadhaar', '982663598852'),
        (210, 'aadhaar', '405030827062'),
        (211, 'aadhaar', '123456789012'),
        (212, 'aadhaar', '234500000013'),
        (213, 'aadhaar', '566769986356'),
        (214, 'aadhaar', '987654321098'),
        (215, 'aadhaar', '234500000016'),
        (216, 'aadhaar', '234500000017'),
        (217, 'aadhaar', '234500000018'),
        (218, 'aadhaar', '234500000019'),
        (219, 'aadhaar', '234500000020')
    ]

    for u in aadhaars:
        conn.execute(text("INSERT OR IGNORE INTO users (user_id, id_type, id_value) VALUES (:id, :t, :v)"), {"id": u[0], "t": u[1], "v": u[2]})

print("Database created: users.db")

