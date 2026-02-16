from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import datetime
import sqlite3
import uvicorn

app = FastAPI(title="Gaurd API")

# Simple SQLite setup
def get_db():
    db = sqlite3.connect("gaurd.db")
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT
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

@app.post("/signup")
def signup(user: UserCreate):
    db = get_db()
    try:
        db.execute("INSERT INTO users (email, password) VALUES (?, ?)", (user.email, user.password))
        db.commit()
        return {"message": "User created successfully"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already exists")

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
