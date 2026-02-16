from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Optional
import datetime
import sqlite3
import uvicorn
import secrets
import os

app = FastAPI(title="Gaurd API")

# Stripe Config (Add your real secret key here)
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_51...")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_...")

# Simple SQLite setup
def get_db():
    # Use absolute path if on Render to avoid issues
    db_path = os.path.join(os.getcwd(), "gaurd.db")
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    return db

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    # In a real app, verify the signature with stripe library
    # For now, we'll parse the JSON
    import json
    try:
        data = json.loads(payload)
        if data["type"] == "checkout.session.completed":
            session = data["data"]["object"]
            email = session.get("customer_details", {}).get("email")
            if email:
                db = get_db()
                # Mark as paid or create user if doesn't exist
                db.execute("UPDATE users SET is_paid = 1 WHERE email = ?", (email,))
                db.commit()
                print(f"Payment success for {email}")
        return {"status": "success"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error"}

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            is_paid BOOLEAN DEFAULT FALSE,
            token TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            block_porn BOOLEAN,
            block_reddit BOOLEAN,
            custom_blocklist TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id INTEGER,
            day_of_week INTEGER,
            start_time TEXT,
            end_time TEXT,
            FOREIGN KEY(profile_id) REFERENCES profiles(id)
        )
    """)
    db.commit()

init_db()

# Models
class UserCreate(BaseModel):
    email: str
    password: str

class ProfileCreate(BaseModel):
    name: str
    block_porn: bool = True
    block_reddit: bool = True
    custom_blocklist: Optional[str] = ""

class ScheduleCreate(BaseModel):
    day_of_week: int
    start_time: str
    end_time: str

import secrets

@app.post("/login")
def login(user: UserCreate):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE email = ? AND password = ?", (user.email, user.password)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate a "Key" for the browser to remember
    token = secrets.token_hex(32)
    db.execute("UPDATE users SET token = ? WHERE id = ?", (token, row["id"]))
    db.commit()
    
    return {
        "token": token,
        "is_paid": bool(row["is_paid"]),
        "email": row["email"]
    }

@app.get("/check-auth")
def check_auth(token: str):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE token = ?", (token,)).fetchone()
    if not row:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "is_paid": bool(row["is_paid"]),
        "email": row["email"]
    }

@app.get("/profiles/{user_id}")
def get_profiles(user_id: int):
    db = get_db()
    profiles = db.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchall()
    return [dict(p) for p in profiles]

@app.post("/profiles/{user_id}")
def create_profile(user_id: int, profile: ProfileCreate):
    db = get_db()
    cursor = db.execute(
        "INSERT INTO profiles (user_id, name, block_porn, block_reddit, custom_blocklist) VALUES (?, ?, ?, ?, ?)",
        (user_id, profile.name, profile.block_porn, profile.block_reddit, profile.custom_blocklist)
    )
    db.commit()
    return {"id": cursor.lastrowid}

@app.get("/policy/{profile_id}")
def get_policy(profile_id: int):
    # This is what the desktop app will call to see what it should be blocking right now
    db = get_db()
    profile = db.execute("SELECT * FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    
    schedules = db.execute("SELECT * FROM schedules WHERE profile_id = ?", (profile_id,)).fetchall()
    
    return {
        "profile": dict(profile),
        "schedules": [dict(s) for s in schedules],
        "server_time": datetime.datetime.now().isoformat()
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
