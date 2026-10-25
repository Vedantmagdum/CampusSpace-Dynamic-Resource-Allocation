# CampusSpace — DevNova | SIH 2026

Flask-based campus resource prototype with PostgreSQL support.

## Roles and main flows

- **Student:** register (pending until admin approval), sign in, view room status, search by capacity/equipment/time, book a discussion section inside a classroom/lab (instead of reserving the whole room), use collaboration matching/invitations, submit complaints and compliments, view notices, and check in/out of the library.
- **Faculty:** register and sign in, view the timetable, and record emergency class cancellations. A cancelled timetable entry no longer blocks the room; approved students/faculty receive in-app notices.
- **Admin:** approve/reject student accounts and restricted-facility requests, add rooms, maintain/import timetables, generate weekly schedules from course constraints, manage complaints, and view utilization analytics.
- **Library:** QR code is generated from the current website URL. Scanning it opens a verified page; the signed-in user confirms check-in. Active sessions are used as an estimate of occupied seats and check-out frees capacity.

## Run locally on Windows PowerShell

1. Install Python 3.11 or 3.12.
2. Extract this ZIP and open PowerShell in the `CampusSpace` folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Optional: copy `.env.example` to `.env` and set variables. Flask does not load `.env` automatically; either set them in PowerShell or install/use a dotenv loader. SQLite is used by default if `DATABASE_URL` is not set.
6. Start:

   ```powershell
   python app.py
   ```

7. Visit http://127.0.0.1:5000

Default local demo administrator: `admin@campus.local` / `Admin@12345`. This is for local demo only. Set `ADMIN_EMAIL`, `ADMIN_PASSWORD`, and `SECRET_KEY` before public deployment. Do not publish real credentials.

## Use PostgreSQL locally

1. Install PostgreSQL from https://www.postgresql.org/download/windows/ and optionally install pgAdmin.
2. In pgAdmin, connect to your local PostgreSQL server.
3. Create a database named `campus_space` (Databases → Create → Database).
4. Set the `DATABASE_URL` environment variable in the same PowerShell terminal (replace password with your actual password):

   ```powershell
   $env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/campus_space"
   $env:SECRET_KEY = "put-a-long-random-secret-here"
   $env:ADMIN_EMAIL = "admin@your-college.edu"
   $env:ADMIN_PASSWORD = "a-strong-unique-admin-password"
   $env:LIBRARY_QR_TOKEN = "a-long-random-token"
   python app.py
   ```

5. The app creates its tables and demo rooms/timetable when it starts. Keep credentials private. If your database password contains reserved URL characters, URL-encode them.

## Deploy to Render

1. Push the `CampusSpace` folder contents to a GitHub repository.
2. In Render, create a managed PostgreSQL database. Copy its **Internal Database URL** when the web service and database are in the same Render region.
3. Create a Render **Web Service** from the GitHub repository.
4. Build command: `pip install -r requirements.txt`
5. Start command: `gunicorn app:app`
6. In the service's Environment settings add:
   - `DATABASE_URL` = Render PostgreSQL Internal Database URL
   - `SECRET_KEY` = long random secret
   - `ADMIN_EMAIL` = admin email
   - `ADMIN_PASSWORD` = strong unique password
   - `LIBRARY_QR_TOKEN` = long random token
7. Deploy. Open the deployed website, test all roles, then print the QR code from the Library page. If you change the deployed domain, regenerate/reprint the QR code.

## Pre-deployment test checklist

- [ ] Register student; confirm login is blocked while pending.
- [ ] Admin approves student; student can then sign in.
- [ ] Student books a specific classroom/lab discussion section; the selected section appears on the dashboard and admin review screen.
- [ ] Two groups can book different sections of the same room for overlapping times, while a conflicting same-section or whole-room booking is blocked.
- [ ] Admin can add sections while keeping combined active section capacity within the room capacity.
- [ ] Admin approval appears in student notifications/dashboard.
- [ ] Overlapping timetable or approved booking blocks a request.
- [ ] Faculty cancels a scheduled lecture; room status changes and notices appear.
- [ ] Library QR opens the deployed URL; check-in increases estimated occupancy; check-out reduces it.
- [ ] Restart/redeploy and verify data persists in PostgreSQL.

## Added workflows

- **Section-based booking:** classrooms and labs expose separately bookable discussion zones. A booking reserves only the selected zone; different zones may be booked concurrently. Whole-room timetable entries and whole-room bookings still block all sections. Admins can add zones from Manage rooms, and active section capacities may not exceed the room capacity. Demo zones are seeded automatically and must be adjusted to the actual physical floor plan.
- **Automatic booking decisions:** valid classroom-section bookings are approved immediately after server-side conflict checks. Room types listed in `MANUAL_APPROVAL_ROOM_TYPES` (default: `lab,seminar`) require admin review.
- **Timetable import:** admins can upload CSV or text-extractable PDF files using `room_code,title,starts_at,ends_at` plus optional `batch,faculty`. Scanned PDFs need OCR, which is not bundled.
- **Timetable generation:** admins can upload a course-constraints CSV (`subject,batch,faculty,weekly_sessions,duration_minutes,students,room_type`). The greedy scheduler fills weekdays 09:00–17:00 for the next Monday–Friday and saves only if all sessions can be placed. It checks configured room capacity/type, room conflicts, batch conflicts, and faculty conflicts.
- **Collaboration:** campus-visible requests are ranked with explainable rule-based signals (purpose, overlapping topic tokens, complementary skill tokens, and nearby preferred times). Invitations require acceptance before a group is created.
- **Feedback:** complaints receive a tracking code and category-based department routing; admins can update status and resolution notes. Image attachments are private to the reporter and admins. Compliments support private/public visibility.
- **Sample CSVs:** download `sample_timetable.csv`, `sample_timetable.pdf`, and `sample_course_constraints.csv` from the relevant admin pages.

## Prototype limitations

- Library occupancy is based on check-in sessions, not real sensors; users must check out. Automatic expiry and reminder scheduling are not implemented.
- Analytics are basic record-count estimates, not full time-weighted utilization reports.
- The campus map is a room directory/floor overview, not a surveyed architectural map.
- Faculty cancellation currently applies to timetable entries visible to faculty; production deployment should restrict cancellations to classes assigned to that faculty member and add audit/approval policy.
- Production hardening still requires CSRF protection, rate limiting, stronger admin bootstrap/secret management, and a concurrency-safe database constraint for overlapping bookings. SQLite does not guarantee protection against simultaneous booking races in this prototype.
- Timetable generation is a greedy heuristic, not a globally optimal solver or trained AI model. PDF import requires text extraction to retain a CSV-like row structure; scanned-PDF OCR is not included.
- Collaboration recommendations are transparent keyword/rule heuristics, not trained AI. Automatic push/email delivery and background reminders are not implemented; notifications are in-app.

## Organization-only access

Only members of your organization can register or sign in.

- Set your organization's email domain(s) before starting the app:
  - Windows PowerShell: `$env:ORG_EMAIL_DOMAINS = "yourcollege.edu"` (comma-separate several domains; subdomains such as `cs.yourcollege.edu` are included).
  - If you do not set it, the domain of `ADMIN_EMAIL` is used.
  - `ORG_EMAIL_DOMAINS=*` turns the restriction off (open demo only).
- Emails from any other domain are rejected at registration, blocked at login, and cannot be approved by an admin.
- Every new student and faculty account must be approved by an admin. To let faculty in immediately, set `FACULTY_AUTO_APPROVE=true`.
- Guests only see the landing page. Rooms, booking, library and all APIs need a signed-in, approved member.
- The admin account is created from `ADMIN_EMAIL` / `ADMIN_PASSWORD` and is not blocked by the domain rule.
