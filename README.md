
# 🏫 CampusSpace — DevNova

### Smart Campus Resource Allocation & Management System

CampusSpace is a Flask-based campus resource management prototype developed for **Hello World 2026**, organized by **ACSES × Semicolon** at KIT's College of Engineering, Kolhapur.

The project helps students discover and book available classrooms, laboratory discussion zones, and campus facilities while enabling faculty and administrators to manage timetables, room allocation, and campus operations.

---

## 👥 Team DevNova

| Team Member | Role |
|---|---|
| **Vedant Magdum** | Team Leader, Backend Development & Presentation |
| **Ajit Jamdade** | Database Management & Research |
| **Pradnya** | Frontend Development |
| **Supriya** | Presentation & Backend Development Support |

---

## 🏆 Hackathon Details

- **Event:** Hello World 2026
- **Organized by:** ACSES × Semicolon
- **Track:** Beginner Track
- **Problem Statement:** 2 — Dynamic Resource Allocation for College Facilities
- **Achievement:** Shortlisted among 20 teams from approximately 70 registered teams
- **Development Sprint:** 4-hour offline hackathon

---

## 🎯 Problem Statement

Classrooms and laboratories often remain unused when scheduled classes are not taking place, while students struggle to find available spaces for group discussions, collaborative projects, and study sessions.

CampusSpace addresses this problem by providing a centralized platform for checking room availability and managing campus resources.

---

## ✨ Key Features

### 🎓 Student Module

- Student registration and admin approval.
- Secure login and account access.
- View room availability and search by capacity, equipment, and time.
- Book specific discussion sections inside classrooms and laboratories.
- Collaboration matching and group invitations.
- Submit complaints and compliments.
- View notices and notifications.
- Library check-in and check-out using QR codes.

### 👨‍🏫 Faculty Module

- Faculty registration and login.
- View timetable information.
- Record emergency class cancellations.
- Notify relevant users about timetable changes.

### 🛡️ Admin Module

- Approve or reject student accounts.
- Manage restricted-facility booking requests.
- Add and manage rooms and discussion sections.
- Import timetables using CSV or text-extractable PDF files.
- Generate weekly schedules using course constraints.
- Manage complaints and resolution status.
- View basic resource utilization analytics.

### 🪑 Smart Room Allocation

- Section-based booking for classrooms and laboratories.
- Conflict checking for room, timetable, and booking schedules.
- Automatic approval for eligible classroom-section bookings.
- Manual review for configured restricted room types.
- Multiple discussion sections can be booked independently when there are no conflicts.

### 📚 Library Management

- QR code linked to the current website URL.
- Verified library check-in and check-out.
- Estimated seat occupancy based on active sessions.

### 🤝 Collaboration & Feedback

- Rule-based collaboration recommendations.
- Group invitations requiring acceptance.
- Complaint tracking with category-based routing.
- Private complaint attachments and configurable compliment visibility.

---

## 🛠️ Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application logic |
| Flask | Backend and web framework |
| HTML5 | Web page structure |
| CSS3 | Styling and responsive layouts |
| JavaScript | Client-side interactions |
| PostgreSQL | Database option |
| SQLite | Default local fallback when `DATABASE_URL` is not configured |
| Git & GitHub | Version control |

---

## 📁 Project Structure

```text
CampusSpace/
├── app.py
├── requirements.txt
├── Procfile
├── .env.example
├── .gitignore
├── README.md
├── routes/
├── templates/
├── static/
└── ...
```

*Note: The structure above is illustrative. Actual files may differ.*

---

## ⚙️ Installation & Setup

### Prerequisites

- Python 3.11 or 3.12
- Git
- PostgreSQL for PostgreSQL configuration
- Visual Studio Code (recommended)

### 1. Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd CampusSpace
```

Replace `YOUR_GITHUB_REPOSITORY_URL` with your actual GitHub repository URL.

### 2. Create a Virtual Environment

```powershell
py -m venv .venv
```

Activate it in Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure the Application

Optionally, copy `.env.example` to `.env` and configure the environment variables.

Flask does not automatically load `.env` without a dotenv loader. You can configure variables directly in PowerShell.

### 5. Run the Application

```powershell
python app.py
```

Open your browser and visit:

**http://127.0.0.1:5000**

---

## 🐘 PostgreSQL Configuration

1. Install PostgreSQL from the [official PostgreSQL website](https://www.postgresql.org/download/windows/).
2. Create a database named `campus_space`.
3. Configure the database connection and secret variables in PowerShell.

```powershell
$env:DATABASE_URL = "postgresql://postgres:YOUR_PASSWORD@localhost:5432/campus_space"
$env:SECRET_KEY = "your-long-random-secret"
$env:ADMIN_EMAIL = "admin@your-college.edu"
$env:ADMIN_PASSWORD = "your-strong-admin-password"
$env:LIBRARY_QR_TOKEN = "your-random-library-token"

python app.py
```

Replace the example values with your own credentials. Never commit real passwords, tokens, or `.env` files to GitHub.

---

## 🧪 Testing Checklist

- [ ] Student registration and admin approval.
- [ ] Login restrictions for unapproved users.
- [ ] Room and discussion-section booking.
- [ ] Booking conflict validation.
- [ ] Admin room and timetable management.
- [ ] Faculty emergency class cancellation.
- [ ] Notifications after relevant changes.
- [ ] Library QR check-in and check-out.
- [ ] Database persistence after restart.

---

## ⚠️ Current Limitations

- Library occupancy is estimated from active check-in sessions, not physical sensors.
- Analytics are basic record-count estimates.
- The campus map is a room directory or floor overview, not a surveyed architectural map.
- Timetable generation uses a greedy scheduling heuristic, not a globally optimal solver.
- Collaboration recommendations use transparent rules and keyword matching, not a trained AI model.
- Scanned PDF timetable import requires OCR, which is not included.
- Production deployment needs additional security hardening and concurrency-safe booking validation.

---

## 🚀 Future Improvements

- Improve the campus map with verified floor plans.
- Add automated notification delivery and reminders.
- Enhance analytics with time-based utilization reports.
- Strengthen security, access control, and booking concurrency protection.
- Improve scheduling algorithms and resource recommendations.

---

## 🙌 Acknowledgements

We thank **ACSES × Semicolon**, the organizers, mentors, and judges of Hello World 2026 for providing an opportunity to build and present our solution.

Developed by **Team DevNova** with the goal of making campus resource allocation more accessible and efficient.

---

**Project:** CampusSpace  
**Team:** DevNova  
**Team Leader:** Vedant Magdum

