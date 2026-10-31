# Public Complaint Management System
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
git push -u origin main
## Installation
1. Install Python 3.9 or newer.
2. Open this folder in VS Code.
3. Open a terminal (Terminal > New Terminal).
4. Create a virtual environment: `python -m venv venv`
5. Activate it: Windows `venv\Scripts\activate` | Mac/Linux `source venv/bin/activate`
6. Install requirements: `pip install -r requirements.txt`
7. Run: `uvicorn main:app --reload`  (or simply `python main.py`)
8. Open **http://127.0.0.1:8000** in your browser.

The folders, SQLite database, tables and default admin are created automatically on first start.

## Admin login (academic demo only!)
- Username: `admin`
- Password: `Admin@123`

> This default password is only for the college demo. Never use it in a real system.

## How to use
**Citizen:** Register > Login > *Submit Complaint* (optionally attach JPG/PNG/PDF, max 5 MB) >
you get a number like `CMP-2026-00001` > use *Track Complaint* or *My Complaints* to follow progress >
read updates under *Notifications*.

**Admin:** Login > see statistics and all complaints > search/filter > click *View / Update* >
assign a department, change status, add a remark (or use Resolve / Reject / Close buttons) >
each change is saved in the complaint history and the citizen gets a notification >
*Reports* shows complaints by category and department, *Users* lists citizens.

## Where is data stored?
- Database: `database/complaints.db` (SQLite)
- Uploaded files: `storage/uploads/` (e.g. `complaint_001_ab12cd34.jpg`)
- Delete `database/complaints.db` to reset everything.

## Project flow (for explaining)
Citizen registers/logs in > submits complaint > saved in SQLite + number generated > admin reviews >
assigns department > changes status > history updated > citizen gets internal notification >
complaint resolved > citizen tracks final status.

## Files
| File | Purpose |
|------|---------|
| `main.py` | All routes (pages + API) and start-up |
| `database.py` | SQLite connection, creates folders |
| `models.py` | 4 tables: users, complaints, complaint_history, notifications |
| `auth.py` | Password hashing + cookie login/role checks |
| `templates/` | The 7 HTML pages |
| `static/` | `style.css` and `app.js` (shared helpers) |

## Security used
Hashed passwords (PBKDF2), cookie sessions, role checks (citizen/admin), input and file validation,
ORM queries (no raw SQL), HTML escaping in the browser, citizens can only open their own attachments.
Tracking by complaint number is public but shows no personal details.
Note: sessions are kept in memory, so restarting the server logs everyone out.
