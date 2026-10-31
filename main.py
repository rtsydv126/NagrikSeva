"""Public Complaint Management System - all routes live in this one file.
Run with:  python main.py   (or)   uvicorn main:app --reload
"""
import os, re, uuid
from datetime import datetime
from typing import Optional

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from database import Base, engine, SessionLocal, get_db, BASE_DIR, UPLOAD_DIR
from models import User, Complaint, ComplaintHistory, Notification
from auth import (hash_password, verify_password, create_session, SESSIONS,
                  user_from_request, current_user, admin_user)

# ---------- Allowed values ----------
CATEGORIES = ["Water Supply", "Electricity", "Roads", "Garbage", "Street Lights",
              "Public Transport", "Sanitation", "Other"]
DEPARTMENTS = ["Water Department", "Electricity Department", "Roads & Public Works",
               "Sanitation Department", "Transport Department", "Municipal Corporation"]
STATUSES = ["Submitted", "Under Review", "Assigned", "In Progress", "Resolved", "Rejected", "Closed"]
PRIORITIES = ["Low", "Medium", "High"]
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_FILE_MB = 5

# ---------- Start-up: create tables + default admin ----------
Base.metadata.create_all(engine)
with SessionLocal() as _db:
    if not _db.query(User).filter(User.username == "admin").first():
        _db.add(User(name="Administrator", email="admin@example.com", mobile="0000000000",
                     username="admin", password=hash_password("Admin@123"), role="admin"))
        _db.commit()

app = FastAPI(title="Public Complaint Management System")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def fmt(d):
    return d.strftime("%d-%m-%Y %H:%M") if d else ""


def notify(db, user_id, message):
    db.add(Notification(user_id=user_id, message=message))


# ---------- HTML pages (just serve the files in templates/) ----------
def page(name, need=None):
    """need=None: public page, 'user': citizens only, 'admin': admin only."""
    def handler(request: Request, db: Session = Depends(get_db)):
        user = user_from_request(request, db)
        if need and not user:
            return RedirectResponse("/login")
        if need == "admin" and user.role != "admin":
            return RedirectResponse("/dashboard")
        if need == "user" and user.role == "admin":
            return RedirectResponse("/admin")
        return FileResponse(os.path.join(BASE_DIR, "templates", name + ".html"))
    return handler


for _path, _name, _need in [("/", "index", None), ("/login", "login", None),
                            ("/register", "register", None), ("/track", "track", None),
                            ("/dashboard", "dashboard", "user"), ("/complaint", "complaint", "user"),
                            ("/admin", "admin", "admin")]:
    app.get(_path, include_in_schema=False)(page(_name, _need))


# ---------- Register / Login / Logout ----------
class RegisterIn(BaseModel):
    name: str
    email: str
    mobile: str
    username: str
    password: str
    confirm_password: str


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/api/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    name, email = data.name.strip(), data.email.strip().lower()
    mobile, username = data.mobile.strip(), data.username.strip().lower()
    if len(name) < 3:
        raise HTTPException(400, "Full name must be at least 3 characters")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(400, "Enter a valid email address")
    if not re.match(r"^\d{10}$", mobile):
        raise HTTPException(400, "Mobile number must be exactly 10 digits")
    if not re.match(r"^[a-z0-9_]{4,20}$", username):
        raise HTTPException(400, "Username: 4-20 letters, numbers or underscore")
    if len(data.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if data.password != data.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, "Username already taken")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already registered")
    db.add(User(name=name, email=email, mobile=mobile, username=username,
                password=hash_password(data.password), role="user"))
    db.commit()
    return {"message": "Registration successful. Please login."}


@app.post("/api/login")
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username.strip().lower()).first()
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(401, "Invalid username or password")
    token = create_session(user.id)
    response.set_cookie("session", token, httponly=True, samesite="lax")
    return {"role": user.role, "redirect": "/admin" if user.role == "admin" else "/dashboard"}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    SESSIONS.pop(request.cookies.get("session"), None)
    response.delete_cookie("session")
    return {"message": "Logged out"}


@app.get("/api/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    unread = db.query(Notification).filter_by(user_id=user.id, is_read=0).count()
    return {"id": user.id, "name": user.name, "username": user.username,
            "role": user.role, "unread": unread}


# ---------- Citizen: complaints ----------
def complaint_row(c, user_name=None):
    row = {"id": c.id, "complaint_number": c.complaint_number, "title": c.title,
           "category": c.category, "department": c.department, "priority": c.priority,
           "status": c.status, "date": fmt(c.created_at)}
    if user_name is not None:
        row["user"] = user_name
    return row


@app.post("/api/complaints")
async def submit_complaint(title: str = Form(...), description: str = Form(...),
                           category: str = Form(...), department: str = Form(""),
                           location: str = Form(...), priority: str = Form("Medium"),
                           file: Optional[UploadFile] = File(None),
                           user: User = Depends(current_user), db: Session = Depends(get_db)):
    title, description, location = title.strip(), description.strip(), location.strip()
    if len(title) < 5 or len(description) < 10 or len(location) < 3:
        raise HTTPException(400, "Please fill title (5+), description (10+) and location properly")
    if category not in CATEGORIES or priority not in PRIORITIES:
        raise HTTPException(400, "Invalid category or priority")
    if department and department not in DEPARTMENTS:
        raise HTTPException(400, "Invalid department")

    # Check the file BEFORE saving anything
    data, ext = None, ""
    if file is not None and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            raise HTTPException(400, "Only JPG, JPEG, PNG or PDF files are allowed")
        data = await file.read()
        if len(data) > MAX_FILE_MB * 1024 * 1024:
            raise HTTPException(400, f"File is too large (max {MAX_FILE_MB} MB)")

    c = Complaint(user_id=user.id, title=title, description=description, category=category,
                  department=department, location=location, priority=priority, status="Submitted")
    db.add(c)
    db.flush()                                   # gives us c.id
    c.complaint_number = f"CMP-{datetime.now().year}-{c.id:05d}"
    if data is not None:
        filename = f"complaint_{c.id:03d}_{uuid.uuid4().hex[:8]}{ext}"
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
            f.write(data)
        c.file_path = filename
    db.add(ComplaintHistory(complaint_id=c.id, status="Submitted",
                            remark="Complaint registered", updated_by=user.name))
    notify(db, user.id, f"Your complaint {c.complaint_number} has been submitted successfully.")
    db.commit()
    return {"message": "Complaint submitted successfully.", "complaint_number": c.complaint_number}


@app.get("/api/complaints")
def my_complaints(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Complaint).filter_by(user_id=user.id).order_by(Complaint.id.desc()).all()
    return [complaint_row(c) for c in rows]


@app.get("/api/stats")
def my_stats(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Complaint.status).filter_by(user_id=user.id).all()
    s = [r[0] for r in rows]
    return {"total": len(s),
            "pending": sum(x in ("Submitted", "Under Review", "Assigned") for x in s),
            "in_progress": s.count("In Progress"),
            "resolved": sum(x in ("Resolved", "Closed") for x in s)}


@app.get("/api/track/{number}")
def track(number: str, request: Request, db: Session = Depends(get_db)):
    """Anyone can track by complaint number; owner/admin also get extra details."""
    c = db.query(Complaint).filter_by(complaint_number=number.strip().upper()).first()
    if not c:
        raise HTTPException(404, "Complaint not found. Check the complaint number.")
    history = db.query(ComplaintHistory).filter_by(complaint_id=c.id).order_by(ComplaintHistory.id).all()
    out = {"complaint_number": c.complaint_number, "title": c.title, "category": c.category,
           "department": c.department or "Not assigned yet", "location": c.location,
           "priority": c.priority, "status": c.status, "submitted": fmt(c.created_at),
           "updated": fmt(c.updated_at), "admin_remark": c.admin_remark or "-",
           "history": [{"date": fmt(h.created_at), "status": h.status, "remark": h.remark} for h in history]}
    viewer = user_from_request(request, db)
    if viewer and (viewer.role == "admin" or viewer.id == c.user_id):
        owner = db.query(User).get(c.user_id)
        out.update(id=c.id, description=c.description, user=owner.name, mobile=owner.mobile,
                   file_url=f"/api/complaints/{c.id}/file" if c.file_path else "",
                   current_department=c.department)
    return out


@app.get("/api/complaints/{cid}/file")
def get_file(cid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.query(Complaint).get(cid)
    if not c or not c.file_path or (user.role != "admin" and c.user_id != user.id):
        raise HTTPException(404, "File not found")
    return FileResponse(os.path.join(UPLOAD_DIR, os.path.basename(c.file_path)))


# ---------- Notifications ----------
@app.get("/api/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Notification).filter_by(user_id=user.id).order_by(Notification.id.desc()).all()
    return [{"message": n.message, "is_read": n.is_read, "date": fmt(n.created_at)} for n in rows]


@app.post("/api/notifications/read")
def mark_read(user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter_by(user_id=user.id, is_read=0).update({"is_read": 1})
    db.commit()
    return {"message": "ok"}


# ---------- Admin ----------
@app.get("/api/admin/complaints")
def admin_complaints(q: str = "", status: str = "", category: str = "", department: str = "",
                     priority: str = "", admin: User = Depends(admin_user),
                     db: Session = Depends(get_db)):
    query = db.query(Complaint, User.name).join(User, User.id == Complaint.user_id)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Complaint.complaint_number.like(like),
                                 Complaint.title.like(like), User.name.like(like)))
    if status:
        query = query.filter(Complaint.status == status)
    if category:
        query = query.filter(Complaint.category == category)
    if department:
        query = query.filter(Complaint.department == department)
    if priority:
        query = query.filter(Complaint.priority == priority)
    return [complaint_row(c, name) for c, name in query.order_by(Complaint.id.desc()).all()]


class UpdateIn(BaseModel):
    status: str
    department: str = ""
    remark: str = ""


@app.put("/api/admin/complaints/{cid}")
def admin_update(cid: int, data: UpdateIn, admin: User = Depends(admin_user),
                 db: Session = Depends(get_db)):
    c = db.query(Complaint).get(cid)
    if not c:
        raise HTTPException(404, "Complaint not found")
    if data.status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    if data.department and data.department not in DEPARTMENTS:
        raise HTTPException(400, "Invalid department")
    remark, num = data.remark.strip(), c.complaint_number
    dept_changed = bool(data.department) and data.department != c.department
    status_changed = data.status != c.status
    if not (dept_changed or status_changed or remark):
        raise HTTPException(400, "Nothing to update")

    if dept_changed:
        c.department = data.department
        notify(db, c.user_id, f"Your complaint {num} has been assigned to the {data.department}.")
    if status_changed:
        c.status = data.status
        if data.status == "Resolved":
            notify(db, c.user_id, f"Your complaint {num} has been resolved.")
        else:
            notify(db, c.user_id, f"Your complaint {num} status has been changed to {data.status}.")
    if remark:
        c.admin_remark = remark
        if not (dept_changed or status_changed):
            notify(db, c.user_id, f"Admin added a remark on your complaint {num}.")
    c.updated_at = datetime.now()

    default = f"Assigned to {c.department}" if dept_changed else f"Status changed to {c.status}"
    db.add(ComplaintHistory(complaint_id=c.id, status=c.status, remark=remark or default,
                            updated_by=admin.name))
    db.commit()
    return {"message": "Complaint updated successfully"}


@app.get("/api/admin/stats")
def admin_stats(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    s = [r[0] for r in db.query(Complaint.status).all()]
    return {"total": len(s),
            "pending": sum(x in ("Submitted", "Under Review", "Assigned") for x in s),
            "in_progress": s.count("In Progress"),
            "resolved": s.count("Resolved"),
            "rejected": s.count("Rejected"),
            "users": db.query(User).filter(User.role == "user").count()}


@app.get("/api/admin/users")
def admin_users(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.query(User).filter(User.role == "user").order_by(User.id).all()
    counts = dict(db.query(Complaint.user_id, func.count(Complaint.id)).group_by(Complaint.user_id).all())
    return [{"name": u.name, "email": u.email, "mobile": u.mobile, "username": u.username,
             "complaints": counts.get(u.id, 0), "joined": fmt(u.created_at)} for u in rows]


@app.get("/api/admin/reports")
def admin_reports(admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    stats = admin_stats(admin, db)
    cats = dict(db.query(Complaint.category, func.count(Complaint.id)).group_by(Complaint.category).all())
    deps = dict(db.query(Complaint.department, func.count(Complaint.id)).group_by(Complaint.department).all())
    if "" in deps:
        deps["Not assigned"] = deps.pop("")
    return {"stats": stats, "by_category": cats, "by_department": deps}


if __name__ == "__main__":
    print("Open http://127.0.0.1:8000 in your browser")
    uvicorn.run(app, host="127.0.0.1", port=8000)
