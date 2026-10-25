import os
import csv
import io
import re
import secrets
from datetime import datetime, date, time, timedelta
from functools import wraps
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file, send_from_directory, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import and_, or_, inspect, text

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-this-secret')
db_url = os.environ.get('DATABASE_URL', 'sqlite:///campus_space.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif db_url.startswith('postgresql://'):
    db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('COOKIE_SECURE', '0') == '1'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='requester', lazy=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(30), unique=True, nullable=False)
    building = db.Column(db.String(80), nullable=False, default='Main Building')
    floor = db.Column(db.Integer, nullable=False, default=1)
    kind = db.Column(db.String(20), nullable=False, default='classroom')
    capacity = db.Column(db.Integer, nullable=False, default=30)
    equipment = db.Column(db.String(500), nullable=False, default='')
    notes = db.Column(db.String(500), default='')

class RoomSection(db.Model):
    """A separately bookable zone inside a larger classroom or lab."""
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=8)
    purpose = db.Column(db.String(180), nullable=False, default='Discussion and group work')
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    room = db.relationship('Room', backref=db.backref('sections', lazy=True, cascade='all, delete-orphan'))

class TimetableEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    title = db.Column(db.String(140), nullable=False)
    batch = db.Column(db.String(80), default='')
    faculty = db.Column(db.String(120), default='')
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    cancelled = db.Column(db.Boolean, default=False, nullable=False)
    exception_note = db.Column(db.String(300), default='')
    room = db.relationship('Room', backref='timetable_entries')

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)
    section_id = db.Column(db.Integer, db.ForeignKey('room_section.id'), nullable=True, index=True)
    attendee_count = db.Column(db.Integer, nullable=False, default=1)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    purpose = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False) # pending/approved/rejected/cancelled/completed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_note = db.Column(db.String(500), default='')
    room = db.relationship('Room', backref='bookings')
    section = db.relationship('RoomSection', backref=db.backref('bookings', lazy=True))

class LibrarySession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    checkin_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    checkout_at = db.Column(db.DateTime)
    session_token = db.Column(db.String(80), unique=True, nullable=False)
    user = db.relationship('User', backref='library_sessions')

class Notice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref='notices')


class CollaborationRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    purpose = db.Column(db.String(80), nullable=False)
    topic = db.Column(db.String(180), nullable=False)
    skills_offered = db.Column(db.String(300), default='')
    skills_needed = db.Column(db.String(300), default='')
    preferred_at = db.Column(db.DateTime, nullable=True)
    duration_hours = db.Column(db.Integer, default=1, nullable=False)
    location = db.Column(db.String(120), default='')
    group_size = db.Column(db.Integer, default=2, nullable=False)
    visibility = db.Column(db.String(20), default='campus', nullable=False)
    status = db.Column(db.String(20), default='open', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    owner = db.relationship('User', backref='collaboration_requests')


class CollaborationInvite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('collaboration_request.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    request = db.relationship('CollaborationRequest', backref='invites')
    sender = db.relationship('User', foreign_keys=[sender_id])
    recipient = db.relationship('User', foreign_keys=[recipient_id])


class CollaborationGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    objective = db.Column(db.String(300), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    preferred_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    members = db.relationship('CollaborationGroupMember', backref='group', cascade='all, delete-orphan')


class CollaborationGroupMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('collaboration_group.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User')
    __table_args__ = (db.UniqueConstraint('group_id', 'user_id', name='uq_collab_group_member'),)


class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    complaint_code = db.Column(db.String(24), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(2000), nullable=False)
    location = db.Column(db.String(160), default='')
    priority = db.Column(db.String(20), default='normal', nullable=False)
    status = db.Column(db.String(24), default='Submitted', nullable=False)
    assigned_department = db.Column(db.String(100), default='Campus Administration')
    resolution_notes = db.Column(db.String(1200), default='')
    attachment_name = db.Column(db.String(255), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    reporter = db.relationship('User', backref='complaints')


class Compliment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient = db.Column(db.String(160), default='')
    category = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(1200), nullable=False)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    author = db.relationship('User', backref='compliments')


@login_manager.user_loader
def load_user(user_id): return db.session.get(User, int(user_id))

def allowed_domains():
    """Organization email domains. Set ORG_EMAIL_DOMAINS="college.edu,cs.college.edu" (use * to disable the restriction).
    If unset, the domain of ADMIN_EMAIL is used."""
    raw=os.environ.get('ORG_EMAIL_DOMAINS','').strip() or os.environ.get('ADMIN_EMAIL','admin@campus.local').rsplit('@',1)[-1]
    return [d.strip().lower().lstrip('@') for d in raw.split(',') if d.strip()]

def is_org_email(email):
    """True only for addresses on the organization's domain (or a subdomain of it)."""
    domains=allowed_domains()
    if '*' in domains: return True
    email=(email or '').strip().lower()
    if email.count('@')!=1 or email.startswith('@') or email.endswith('@'): return False
    domain=email.rsplit('@',1)[1]
    return any(domain==d or domain.endswith('.'+d) for d in domains)

def faculty_auto_approve():
    return os.environ.get('FACULTY_AUTO_APPROVE','false').strip().lower() in ('1','true','yes')

def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != 'admin' and not is_org_email(current_user.email):
                logout_user(); flash('Access is limited to members of this organization.', 'danger'); return redirect(url_for('login'))
            if current_user.role not in roles: abort(403)
            if current_user.status != 'approved' and current_user.role != 'admin':
                logout_user(); flash('Your account is awaiting administrator approval.', 'warning'); return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return wrapped
    return deco

def overlaps(a_start, a_end, b_start, b_end): return a_start < b_end and b_start < a_end

def room_conflicts(room, starts_at, ends_at, exclude_booking_id=None, section_id=None):
    """Check whole-room timetable occupancy and section-aware confirmed bookings.

    Timetable entries reserve the room as a whole. A room-wide booking conflicts with
    every section; a section booking conflicts only with the same section and any
    room-wide booking for the same time.
    """
    issues=[]
    entries=TimetableEntry.query.filter_by(room_id=room.id, cancelled=False).all()
    for entry in entries:
        if overlaps(starts_at, ends_at, entry.starts_at, entry.ends_at):
            issues.append(f'Timetable conflict: {entry.title} ({entry.starts_at:%d %b %H:%M}–{entry.ends_at:%H:%M})')
    q=Booking.query.filter(Booking.room_id==room.id, Booking.status=='approved', Booking.starts_at < ends_at, Booking.ends_at > starts_at)
    if section_id is not None:
        q=q.filter(or_(Booking.section_id.is_(None), Booking.section_id==section_id))
    if exclude_booking_id:
        q=q.filter(Booking.id != exclude_booking_id)
    for booking in q.all():
        place = f' ({booking.section.name})' if booking.section else ' (whole room)'
        issues.append(f'Approved booking #{booking.id}{place} already occupies this slot')
    return issues

def schedule_conflicts(starts_at, ends_at, batch='', faculty=''):
    issues=[]
    q=TimetableEntry.query.filter(TimetableEntry.cancelled.is_(False), TimetableEntry.starts_at < ends_at, TimetableEntry.ends_at > starts_at)
    for entry in q.all():
        if batch and entry.batch and entry.batch.strip().lower()==batch.strip().lower():
            issues.append(f'Batch conflict: {batch} overlaps {entry.title}')
        if faculty and entry.faculty and entry.faculty.strip().lower()==faculty.strip().lower():
            issues.append(f'Faculty conflict: {faculty} overlaps {entry.title}')
    return issues


def notify(user_id, message): db.session.add(Notice(user_id=user_id, message=message))

def seed_data():
    db.create_all()
    # Safe additive migration for existing SQLite/PostgreSQL databases.
    try:
        columns = {c['name'] for c in inspect(db.engine).get_columns('timetable_entry')}
        if 'faculty' not in columns:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE timetable_entry ADD COLUMN faculty VARCHAR(120) DEFAULT ''"))
    except Exception:
        app.logger.exception('Could not apply additive timetable migration')
        raise
    # Safe additive migrations for section-level bookings on existing databases.
    try:
        booking_columns = {c['name'] for c in inspect(db.engine).get_columns('booking')}
        if 'section_id' not in booking_columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE booking ADD COLUMN section_id INTEGER REFERENCES room_section(id)'))
        if 'attendee_count' not in booking_columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE booking ADD COLUMN attendee_count INTEGER NOT NULL DEFAULT 1'))
    except Exception:
        app.logger.exception('Could not apply additive section-booking migration')
        raise
    admin_email=os.environ.get('ADMIN_EMAIL','admin@campus.local').lower()
    admin_password=os.environ.get('ADMIN_PASSWORD','Admin@12345')
    admin=User.query.filter_by(email=admin_email).first()
    if not admin:
        admin=User(name='Campus Administrator', email=admin_email, role='admin', status='approved'); admin.set_password(admin_password); db.session.add(admin)
    if Room.query.count()==0:
        rooms=[
          Room(code='A201',building='Academic Block A',floor=2,kind='classroom',capacity=40,equipment='Projector, Smart board, AC',notes='Lecture room'),
          Room(code='A203',building='Academic Block A',floor=2,kind='classroom',capacity=60,equipment='Projector, AC',notes='Large classroom'),
          Room(code='A204',building='Academic Block A',floor=2,kind='classroom',capacity=35,equipment='Projector',notes='Seminar room'),
          Room(code='LAB-2',building='Science and Computing Block',floor=1,kind='lab',capacity=30,equipment='Computer systems, Projector, Lab equipment',notes='Computing laboratory'),
          Room(code='LAB-3',building='Science and Computing Block',floor=1,kind='lab',capacity=24,equipment='Computer systems, Smart board',notes='Development lab'),
          Room(code='LIBRARY',building='Central Library',floor=1,kind='library',capacity=120,equipment='Wi-Fi, Reading desks',notes='QR check-in/out prototype')]
        db.session.add_all(rooms)
    db.session.commit()
    # Demo defaults: split classrooms and labs into independently bookable zones.
    # Admins should adjust these to match the actual physical layout before real use.
    zone_names = ['Discussion Zone A', 'Discussion Zone B']
    for room in Room.query.filter(Room.kind.in_(['classroom', 'lab'])).all():
        if not RoomSection.query.filter_by(room_id=room.id).first():
            # Seed two small zones only; admins can add further sections based on the real floor plan.
            zone_capacity = max(1, min(8, room.capacity // 3))
            for zone_name in zone_names:
                db.session.add(RoomSection(room_id=room.id, name=zone_name, capacity=zone_capacity,
                    purpose='Small-group discussion, project meetings and collaborative work'))
    db.session.commit()
    if TimetableEntry.query.count()==0:
        today=date.today(); now=datetime.now(); start=datetime.combine(today, time(9,0)); end=datetime.combine(today,time(10,0))
        for code,title,st,en in [('A203','Database Systems',start,end),('LAB-2','Java Programming',start,end),('A201','Project Discussion',datetime.combine(today,time(14,0)),datetime.combine(today,time(16,0)))]:
            room=Room.query.filter_by(code=code).first(); db.session.add(TimetableEntry(room_id=room.id,title=title,batch='Demo batch',starts_at=st,ends_at=en))
        db.session.commit()

def room_status(room):
    now=datetime.now()
    active_timetable=any(not e.cancelled and e.starts_at <= now < e.ends_at for e in room.timetable_entries)
    active_bookings=[b for b in room.bookings if b.status=='approved' and b.starts_at <= now < b.ends_at]
    if active_timetable or any(b.section_id is None for b in active_bookings):
        return 'Occupied'
    if active_bookings:
        return 'Partially booked'
    upcoming=[e.starts_at for e in room.timetable_entries if not e.cancelled and e.starts_at > now] + [b.starts_at for b in room.bookings if b.status=='approved' and b.starts_at > now]
    if upcoming and min(upcoming).date()==now.date(): return 'Available later'
    if upcoming: return 'Booked'
    return 'Available'

@app.context_processor
def inject_globals():
    return {'org_domains': [d for d in allowed_domains() if d!='*'], 'seat_free_color': ('green' if os.environ.get('SEAT_FREE_COLOR','red').strip().lower()=='green' else 'red'), 'now': datetime.now, 'room_status': room_status, 'unread_notices': Notice.query.filter_by(user_id=current_user.id, read=False).count() if current_user.is_authenticated else 0}

@app.route('/')
def index():
    rooms=Room.query.order_by(Room.building,Room.code).all()
    return render_template('index.html', rooms=rooms)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password',''); role=request.form.get('role','student')
        if role not in ('student','faculty'): flash('Choose student or faculty.', 'danger')
        elif not name or not email or len(password)<8: flash('Enter all fields. Password must be at least 8 characters.', 'danger')
        elif not is_org_email(email):
            flash('Only members of this organization can register. Use your official organization email ('+', '.join('@'+d for d in allowed_domains())+').', 'danger')
        elif User.query.filter_by(email=email).first(): flash('An account with that email already exists.', 'danger')
        else:
            auto=(role=='faculty' and faculty_auto_approve())
            user=User(name=name,email=email,role=role,status='approved' if auto else 'pending'); user.set_password(password); db.session.add(user); db.session.commit()
            if auto: flash('Faculty account created. You can now sign in.', 'success')
            else:
                for admin in User.query.filter_by(role='admin').all(): notify(admin.id, f'{role.title()} account approval required: {name} ({email})')
                flash(f'Registration submitted. An administrator must approve your {role} account before you can sign in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        user=User.query.filter_by(email=request.form.get('email','').strip().lower()).first()
        selected_role=request.form.get('role','')
        if not user or not user.check_password(request.form.get('password','')):
            flash('Invalid email or password.', 'danger')
        elif selected_role and user.role != selected_role:
            flash(f'This account is registered as {user.role}. Choose the matching login section.', 'danger')
        elif user.role!='admin' and not is_org_email(user.email): flash('Access is limited to members of this organization.', 'danger')
        elif user.status=='pending': flash('Your account is waiting for admin approval.', 'warning')
        elif user.status=='rejected': flash('Your account request was rejected. Contact the administrator.', 'danger')
        else:
            login_user(user); return redirect(url_for('admin_dashboard' if user.role=='admin' else 'dashboard'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); flash('You have been signed out.', 'info'); return redirect(url_for('index'))

@app.route('/dashboard')
@role_required('student','faculty')
def dashboard():
    bookings=Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).limit(8).all()
    notices=Notice.query.filter_by(user_id=current_user.id).order_by(Notice.created_at.desc()).limit(8).all()
    rooms=Room.query.order_by(Room.building,Room.code).all()
    section_rooms=[r for r in rooms if r.kind.lower() in ('classroom','lab')]
    return render_template('dashboard.html', bookings=bookings, notices=notices, rooms=rooms, section_rooms=section_rooms)

@app.route('/rooms')
@role_required('student','faculty','admin')
def rooms():
    all_rooms=Room.query.order_by(Room.building,Room.floor,Room.code).all()
    return render_template('rooms.html', rooms=all_rooms)

@app.route('/recommend', methods=['GET','POST'])
@role_required('student','faculty','admin')
def recommend():
    recommendations=[]; explanation=''
    if request.method=='POST':
        try:
            capacity=max(1,int(request.form.get('capacity','1'))); duration=max(1,int(request.form.get('duration','1')))
            day=datetime.strptime(request.form.get('date'),'%Y-%m-%d').date(); start_time=datetime.strptime(request.form.get('start_time'),'%H:%M').time()
            starts=datetime.combine(day,start_time); ends=starts+timedelta(hours=duration)
            kind=request.form.get('kind','any'); required=set(x.strip().lower() for x in request.form.getlist('equipment') if x.strip())
            for room in Room.query.all():
                if kind!='any' and room.kind!=kind: continue
                available=set(x.strip().lower() for x in room.equipment.split(','))
                if not required.issubset(available): continue
                if room.kind.lower() in ('classroom','lab'):
                    suitable_sections=[sec for sec in room.sections if sec.is_active and sec.capacity>=capacity]
                    if not suitable_sections: continue
                    section_options=[]
                    for sec in suitable_sections:
                        conflicts=room_conflicts(room,starts,ends,section_id=sec.id)
                        section_options.append({'section':sec,'conflicts':conflicts,'capacity':sec.capacity,
                            'score':(0 if conflicts else 100)-max(sec.capacity-capacity,0)*0.1})
                    section_options.sort(key=lambda x:(bool(x['conflicts']),-x['score'],x['capacity']))
                    best=section_options[0]
                    recommendations.append({'room':room,'section':best['section'],'capacity':best['capacity'],
                        'conflicts':best['conflicts'],'score':best['score']})
                else:
                    if room.capacity<capacity: continue
                    conflicts=room_conflicts(room,starts,ends)
                    recommendations.append({'room':room,'section':None,'capacity':room.capacity,'conflicts':conflicts,
                        'score':(0 if conflicts else 100)+min(room.capacity-capacity,50)*-0.1})
            recommendations.sort(key=lambda x:(bool(x['conflicts']), -x['score'], x['capacity']))
            if not recommendations: explanation='No rooms match capacity, type and equipment. Try relaxing one filter.'
            else: explanation=f'Checked {len(recommendations)} matching rooms against timetable exceptions and approved bookings.'
        except (ValueError,TypeError): flash('Enter a valid date, start time, capacity and duration.', 'danger')
    return render_template('recommend.html', recommendations=recommendations, explanation=explanation)

def create_booking(room, section_booking, data):
    """Validate and create a booking for current_user.
    Returns (booking, None) on success or (None, error_message). Shared by the booking form and the tap-to-book API."""
    try:
        starts=datetime.strptime(data.get('starts_at') or '','%Y-%m-%dT%H:%M')
        ends=datetime.strptime(data.get('ends_at') or '','%Y-%m-%dT%H:%M')
    except ValueError:
        return None, 'Check the date/time, section, attendee count and purpose.'
    purpose=(data.get('purpose') or '').strip()[:500]
    try: attendee_count=int(data.get('attendee_count') or 1)
    except (TypeError,ValueError): return None, 'Enter a valid attendee count.'
    section=None
    if section_booking:
        try: section_id=int(data.get('section_id') or 0)
        except (TypeError,ValueError): return None, 'Choose a discussion section.'
        section=db.session.get(RoomSection, section_id)
        if section is None or section.room_id != room.id or not section.is_active:
            return None, 'Choose an active section within this room.'
        if attendee_count < 1 or attendee_count > section.capacity:
            return None, f'{section.name} can accommodate 1–{section.capacity} people.'
    elif attendee_count < 1 or attendee_count > room.capacity:
        return None, f'This facility can accommodate 1–{room.capacity} people.'
    if ends<=starts or starts<datetime.now()-timedelta(minutes=1) or not purpose:
        return None, 'Choose a future time range and enter a purpose.'
    conflicts=room_conflicts(room,starts,ends,section_id=section.id if section else None)
    if conflicts:
        return None, 'This slot is unavailable: '+'; '.join(conflicts)
    manual_types={x.strip().lower() for x in os.environ.get('MANUAL_APPROVAL_ROOM_TYPES','lab,seminar').split(',') if x.strip()}
    status='pending' if room.kind.lower() in manual_types else 'approved'
    booking=Booking(user_id=current_user.id,room_id=room.id,section_id=section.id if section else None,
        attendee_count=attendee_count,starts_at=starts,ends_at=ends,purpose=purpose,status=status)
    db.session.add(booking); db.session.flush()
    target=f'{room.code} · {section.name}' if section else room.code
    if status=='pending':
        for admin in User.query.filter_by(role='admin').all():
            notify(admin.id,f'Booking request #{booking.id}: {target}, {starts:%d %b %H:%M} needs review.')
        notify(current_user.id, f'Booking #{booking.id} for {target} is pending manual review.')
    else:
        notify(current_user.id, f'Booking #{booking.id} for {target} was automatically approved.')
    db.session.commit()
    return booking, None

def _home_url():
    return url_for('admin_dashboard' if current_user.role=='admin' else 'dashboard')

@app.route('/book/<int:room_id>', methods=['GET','POST'])
@role_required('student','faculty','admin')
def book_room(room_id):
    room=db.get_or_404(Room,room_id)
    sections=RoomSection.query.filter_by(room_id=room.id,is_active=True).order_by(RoomSection.name).all()
    section_booking=room.kind.lower() in ('classroom','lab')
    if request.method=='POST':
        booking, error = create_booking(room, section_booking, request.form)
        if error:
            flash(error, 'danger')
        else:
            flash('Booking automatically approved.' if booking.status=='approved' else 'This facility requires administrator approval; your request is pending.', 'success')
            return redirect(_home_url())
    return render_template('book.html', room=room, sections=sections, section_booking=section_booking)

@app.route('/api/rooms/<int:room_id>/book', methods=['POST'])
@role_required('student','faculty','admin')
def book_section_api(room_id):
    """Tap-to-book: books a section directly from the seat map."""
    room=db.get_or_404(Room,room_id)
    data=request.get_json(silent=True) or {}
    booking, error = create_booking(room, room.kind.lower() in ('classroom','lab'), data)
    if error:
        return jsonify({'ok':False,'error':error}), 409 if 'unavailable' in error else 400
    target=f'{room.code} · {booking.section.name}' if booking.section else room.code
    msg=(f'Booked! {target} is confirmed for {booking.starts_at:%d %b %H:%M}–{booking.ends_at:%H:%M}.' if booking.status=='approved'
         else f'Request sent for {target}. It needs administrator approval.')
    return jsonify({'ok':True,'status':booking.status,'message':msg,'redirect':_home_url()})

def _parse_local(value):
    try: return datetime.strptime(value or '', '%Y-%m-%dT%H:%M')
    except ValueError: return None

def section_availability(room, starts, ends):
    """Per-section state for a time window: free / booked / pending / blocked (whole room in use)."""
    blocked=None
    for e in TimetableEntry.query.filter_by(room_id=room.id, cancelled=False).all():
        if overlaps(starts, ends, e.starts_at, e.ends_at):
            blocked=f'Class in session: {e.title} ({e.starts_at:%H:%M}–{e.ends_at:%H:%M})'; break
    live=Booking.query.filter(Booking.room_id==room.id, Booking.status.in_(('approved','pending')), Booking.starts_at < ends, Booking.ends_at > starts).all()
    if not blocked:
        for b in live:
            if b.status=='approved' and b.section_id is None:
                blocked=f'Whole room booked ({b.starts_at:%H:%M}–{b.ends_at:%H:%M})'; break
    result=[]
    for sec in RoomSection.query.filter_by(room_id=room.id, is_active=True).order_by(RoomSection.name).all():
        state, detail = 'free', 'Available for this time'
        if blocked:
            state, detail = 'blocked', blocked
        else:
            mine=[b for b in live if b.section_id==sec.id]
            appr=[b for b in mine if b.status=='approved']
            pend=[b for b in mine if b.status=='pending']
            if appr:
                b=min(appr, key=lambda x:x.starts_at); state, detail = 'booked', f'Booked {b.starts_at:%d %b %H:%M}–{b.ends_at:%H:%M}'
            elif pend:
                b=min(pend, key=lambda x:x.starts_at); state, detail = 'pending', f'Request awaiting approval ({b.starts_at:%H:%M}–{b.ends_at:%H:%M})'
        result.append({'id':sec.id,'name':sec.name,'capacity':sec.capacity,'purpose':sec.purpose,'state':state,'detail':detail})
    return blocked, result

@app.route('/api/rooms/<int:room_id>/sections')
@role_required('student','faculty','admin')
def section_status(room_id):
    room=db.get_or_404(Room,room_id)
    starts=_parse_local(request.args.get('start')); ends=_parse_local(request.args.get('end'))
    if not starts or not ends or ends<=starts:
        starts=datetime.now().replace(second=0,microsecond=0); ends=starts+timedelta(hours=1)
    blocked, sections = section_availability(room, starts, ends)
    free=[x for x in sections if x['state']=='free']
    return jsonify({'room':{'id':room.id,'code':room.code,'capacity':room.capacity},
        'window':{'start':starts.strftime('%Y-%m-%dT%H:%M'),'end':ends.strftime('%Y-%m-%dT%H:%M'),'label':f'{starts:%d %b %H:%M} – {ends:%H:%M}' if starts.date()==ends.date() else f'{starts:%d %b %H:%M} – {ends:%d %b %H:%M}'},
        'blocked_reason':blocked,
        'summary':{'total':len(sections),'free':len(free),'seats_free':sum(x['capacity'] for x in free)},
        'sections':sections})

@app.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@role_required('student','faculty','admin')
def cancel_booking(booking_id):
    booking=db.get_or_404(Booking,booking_id)
    if current_user.role!='admin' and booking.user_id!=current_user.id: abort(403)
    if booking.status in ('pending','approved'):
        booking.status='cancelled'; notify(booking.user_id, f'Booking #{booking.id} was cancelled.'); db.session.commit(); flash('Booking cancelled.', 'success')
    return redirect(url_for('admin_dashboard' if current_user.role=='admin' else 'dashboard'))

@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    pending_users=User.query.filter(User.role.in_(['student','faculty']),User.status=='pending').order_by(User.created_at).all()
    pending_bookings=Booking.query.filter_by(status='pending').order_by(Booking.created_at).all()
    all_bookings=Booking.query.order_by(Booking.created_at.desc()).limit(12).all()
    rooms=Room.query.all(); total=Room.query.count(); now=datetime.now()
    occupied=sum(1 for r in rooms if any(not e.cancelled and e.starts_at<=now<e.ends_at for e in r.timetable_entries) or any(b.status=='approved' and b.starts_at<=now<b.ends_at for b in r.bookings))
    active_library=LibrarySession.query.filter_by(checkout_at=None).count()
    section_rooms=[r for r in sorted(rooms,key=lambda r:r.code) if r.kind.lower() in ('classroom','lab')]
    return render_template('admin.html',section_rooms=section_rooms,pending_users=pending_users,pending_bookings=pending_bookings,all_bookings=all_bookings,rooms=rooms,total=total,occupied=occupied,active_library=active_library)

@app.route('/admin/user/<int:user_id>/<decision>', methods=['POST'])
@role_required('admin')
def decide_user(user_id,decision):
    user=db.get_or_404(User,user_id)
    if user.role not in ('student','faculty') or user.status!='pending' or decision not in ('approve','reject'): abort(400)
    if decision=='approve' and not is_org_email(user.email):
        flash('This email is not on the organization domain, so it cannot be approved.', 'danger'); return redirect(url_for('admin_dashboard'))
    user.status='approved' if decision=='approve' else 'rejected'; notify(user.id, f'Your {user.role} account has been approved.' if decision=='approve' else f'Your {user.role} account request was rejected.'); db.session.commit(); flash(f'{user.role.title()} account {decision}d.', 'success'); return redirect(url_for('admin_dashboard'))

@app.route('/admin/booking/<int:booking_id>/<decision>', methods=['POST'])
@role_required('admin')
def decide_booking(booking_id,decision):
    booking=db.get_or_404(Booking,booking_id)
    if booking.status!='pending' or decision not in ('approve','reject'): abort(400)
    conflicts=room_conflicts(booking.room,booking.starts_at,booking.ends_at,exclude_booking_id=booking.id,section_id=booking.section_id)
    if decision=='approve' and conflicts:
        flash('Approval blocked because a conflict appeared: '+'; '.join(conflicts), 'danger'); return redirect(url_for('admin_dashboard'))
    booking.status='approved' if decision=='approve' else 'rejected'; booking.admin_note=request.form.get('note','').strip(); target=f'{booking.room.code} · {booking.section.name}' if booking.section else booking.room.code; notify(booking.user_id, f'Booking #{booking.id} {booking.status} for {target}.')
    db.session.commit(); flash(f'Booking {booking.status}.', 'success'); return redirect(url_for('admin_dashboard'))

@app.route('/admin/rooms', methods=['GET','POST'])
@role_required('admin')
def manage_rooms():
    if request.method=='POST':
        code=request.form.get('code','').strip().upper(); equipment=request.form.get('equipment','').strip()
        try: capacity=int(request.form.get('capacity','0')); floor=int(request.form.get('floor','1'))
        except ValueError: capacity=0; floor=0
        if not code or capacity<1 or Room.query.filter_by(code=code).first(): flash('Room code must be unique and capacity must be positive.', 'danger')
        else:
            kind=request.form.get('kind','classroom').strip().lower()
            room=Room(code=code,building=request.form.get('building','Main Building').strip() or 'Main Building',floor=floor,kind=kind,capacity=capacity,equipment=equipment)
            db.session.add(room); db.session.flush()
            if kind in ('classroom','lab'):
                section_capacity=max(1,min(8,capacity//3))
                db.session.add_all([
                    RoomSection(room_id=room.id,name='Discussion Zone A',capacity=section_capacity,purpose='Small-group discussion and project work'),
                    RoomSection(room_id=room.id,name='Discussion Zone B',capacity=section_capacity,purpose='Small-group discussion and project work')
                ])
            db.session.commit(); flash('Room added with bookable discussion sections.' if kind in ('classroom','lab') else 'Room added.', 'success'); return redirect(url_for('manage_rooms'))
    return render_template('manage_rooms.html', rooms=Room.query.order_by(Room.code).all())

@app.route('/admin/rooms/<int:room_id>/sections', methods=['POST'])
@role_required('admin')
def manage_room_sections(room_id):
    room=db.get_or_404(Room,room_id)
    if room.kind.lower() not in ('classroom','lab'):
        flash('Separate discussion sections are available for classrooms and labs.', 'warning')
        return redirect(url_for('manage_rooms'))
    name=request.form.get('name','').strip()
    purpose=request.form.get('purpose','Discussion and group work').strip() or 'Discussion and group work'
    try: capacity=int(request.form.get('capacity','0'))
    except (TypeError,ValueError): capacity=0
    current_total=sum(s.capacity for s in RoomSection.query.filter_by(room_id=room.id,is_active=True).all())
    if not name or capacity < 1:
        flash('Enter a section name and a positive capacity.', 'danger')
    elif RoomSection.query.filter_by(room_id=room.id,name=name).first():
        flash('That section name already exists for this room.', 'danger')
    elif current_total + capacity > room.capacity:
        flash(f'Section capacities total {current_total + capacity}, exceeding room capacity ({room.capacity}). Reduce the section size or edit the room layout first.', 'danger')
    else:
        db.session.add(RoomSection(room_id=room.id,name=name,capacity=capacity,purpose=purpose))
        db.session.commit()
        flash(f'{name} added to {room.code}.', 'success')
    return redirect(url_for('manage_rooms'))


@app.route('/admin/timetable', methods=['GET','POST'])
@role_required('admin','faculty')
def manage_timetable():
    if request.method=='POST':
        if current_user.role != 'admin':
            abort(403)
        try:
            room=db.get_or_404(Room,int(request.form.get('room_id'))); starts=datetime.strptime(request.form.get('starts_at'),'%Y-%m-%dT%H:%M'); ends=datetime.strptime(request.form.get('ends_at'),'%Y-%m-%dT%H:%M')
            if ends<=starts: raise ValueError()
            entry=TimetableEntry(room_id=room.id,title=request.form.get('title','').strip(),batch=request.form.get('batch','').strip(),faculty=request.form.get('faculty','').strip(),starts_at=starts,ends_at=ends,exception_note=request.form.get('exception_note','').strip())
            if not entry.title: raise ValueError()
            db.session.add(entry); db.session.commit(); flash('Timetable entry added.', 'success'); return redirect(url_for('manage_timetable'))
        except (ValueError,TypeError): flash('Please check timetable details.', 'danger')
    entries=TimetableEntry.query.order_by(TimetableEntry.starts_at.desc()).limit(100).all()
    return render_template('timetable.html', rooms=Room.query.all(), entries=entries)

@app.route('/timetable/<int:entry_id>/cancel', methods=['POST'])
@role_required('admin','faculty')
def cancel_timetable(entry_id):
    entry=db.get_or_404(TimetableEntry,entry_id)
    if entry.cancelled:
        flash('This class is already cancelled.', 'info')
        return redirect(url_for('manage_timetable'))
    note=request.form.get('note','').strip() or ('Emergency cancellation by faculty' if current_user.role=='faculty' else 'Cancelled by administrator')
    entry.cancelled=True
    entry.exception_note=note
    # Notify approved campus users so room availability changes are visible immediately.
    recipients=User.query.filter(User.status=='approved', User.role.in_(['student','faculty'])).all()
    for recipient in recipients:
        notify(recipient.id, f'Class cancelled: {entry.title} in {entry.room.code} at {entry.starts_at:%d %b %H:%M}. Room availability has been updated. Reason: {note}')
    db.session.commit()
    flash('Class cancellation recorded. Room availability is updated and campus users were notified.', 'success')
    return redirect(url_for('manage_timetable'))

@app.route('/analytics')
@role_required('admin')
def analytics():
    rooms=Room.query.all(); stats=[]
    for room in rooms:
        bookings=Booking.query.filter_by(room_id=room.id,status='approved').count()
        classes=TimetableEntry.query.filter_by(room_id=room.id,cancelled=False).count()
        stats.append({'room':room,'bookings':bookings,'classes':classes,'usage':bookings+classes})
    total_slots=sum(s['usage'] for s in stats); empty_pct=round(100*sum(1 for s in stats if s['usage']==0)/len(stats),1) if stats else 0
    max_usage=max((s['usage'] for s in stats), default=1) or 1
    complaint_total=Complaint.query.count()
    unresolved_complaints=Complaint.query.filter(Complaint.status!='Resolved').count()
    compliment_total=Compliment.query.count()
    group_total=CollaborationGroup.query.count()
    return render_template('analytics.html', stats=stats,total_slots=total_slots,empty_pct=empty_pct,max_usage=max_usage,
        complaint_total=complaint_total,unresolved_complaints=unresolved_complaints,compliment_total=compliment_total,group_total=group_total)

@app.route('/notifications')
@role_required('student','faculty','admin')
def notifications():
    items=Notice.query.filter_by(user_id=current_user.id).order_by(Notice.created_at.desc()).all()
    for n in items: n.read=True
    db.session.commit(); return render_template('notifications.html', items=items)

@app.route('/library')
@role_required('student','faculty','admin')
def library():
    active=LibrarySession.query.filter_by(user_id=current_user.id,checkout_at=None).first()
    history=LibrarySession.query.filter_by(user_id=current_user.id).order_by(LibrarySession.checkin_at.desc()).limit(10).all()
    library_room=Room.query.filter_by(kind='library').first()
    capacity=library_room.capacity if library_room else 0
    occupied=LibrarySession.query.filter_by(checkout_at=None).count()
    return render_template('library.html',active=active,history=history,capacity=capacity,occupied=occupied,qr_url=url_for('library_scan',token=os.environ.get('LIBRARY_QR_TOKEN','campus-library-demo-token'),_external=True))

@app.route('/library/qr.png')
@role_required('student','faculty','admin')
@login_required
def library_qr():
    import io
    import qrcode
    target=url_for('library_scan',token=os.environ.get('LIBRARY_QR_TOKEN','campus-library-demo-token'),_external=True)
    image=qrcode.make(target)
    output=io.BytesIO()
    image.save(output,format='PNG')
    output.seek(0)
    return send_file(output,mimetype='image/png',max_age=0)

@app.route('/library/scan')
def library_scan():
    token=request.args.get('token','')
    if token != os.environ.get('LIBRARY_QR_TOKEN','campus-library-demo-token'):
        abort(403)
    if not current_user.is_authenticated:
        flash('QR verified. Sign in to record your library check-in.', 'info')
        return redirect(url_for('login', next=url_for('library')))
    if current_user.status!='approved' and current_user.role!='admin':
        flash('Your account must be approved before library access.', 'warning')
        return redirect(url_for('login'))
    flash('Library QR verified. Confirm check-in on the Library page.', 'success')
    return redirect(url_for('library'))

@app.route('/library/checkin', methods=['POST'])
@role_required('student','faculty','admin')
def library_checkin():
    if LibrarySession.query.filter_by(user_id=current_user.id,checkout_at=None).first():
        flash('You already have an active library session.', 'warning')
    else:
        library_room=Room.query.filter_by(kind='library').first()
        capacity=library_room.capacity if library_room else 0
        occupied=LibrarySession.query.filter_by(checkout_at=None).count()
        if capacity and occupied >= capacity:
            flash('The library is currently at its configured capacity. Please try again after a checkout.', 'warning')
        else:
            import secrets
            db.session.add(LibrarySession(user_id=current_user.id,session_token=secrets.token_urlsafe(24)))
            db.session.commit()
            flash('Library check-in recorded. Remember to check out so another student can use the seat.', 'success')
    return redirect(url_for('library'))

@app.route('/library/checkout/<int:session_id>', methods=['POST'])
@role_required('student','faculty','admin')
def library_checkout(session_id):
    item=db.get_or_404(LibrarySession,session_id)
    if item.user_id!=current_user.id and current_user.role!='admin': abort(403)
    if not item.checkout_at: item.checkout_at=datetime.utcnow(); db.session.commit(); flash('Library check-out recorded.', 'success')
    return redirect(url_for('library'))



def _tokens(value):
    return {w for w in re.findall(r'[a-z0-9+#.-]+', (value or '').lower()) if len(w) > 1}


def collaboration_match(a, b):
    """Explainable heuristic matching; this is rule-based, not a trained AI model."""
    reasons = []
    a_offer, a_need = _tokens(a.skills_offered), _tokens(a.skills_needed)
    b_offer, b_need = _tokens(b.skills_offered), _tokens(b.skills_needed)
    if a_offer & b_need or b_offer & a_need:
        reasons.append('complementary skills')
    topic_a, topic_b = _tokens(a.topic), _tokens(b.topic)
    if topic_a & topic_b:
        reasons.append('overlapping topics')
    purpose_pairs = {
        frozenset(('group discussion', 'academic project')),
        frozenset(('group study', 'peer learning')),
        frozenset(('technical event', 'event management')),
        frozenset(('hackathon', 'academic project')),
        frozenset(('presentation', 'group discussion')),
        frozenset(('research', 'skill sharing')),
    }
    if a.purpose.lower() == b.purpose.lower():
        reasons.append('shared purpose')
    elif frozenset((a.purpose.lower(), b.purpose.lower())) in purpose_pairs:
        reasons.append('compatible goals across different purposes')
    if a.preferred_at and b.preferred_at and abs((a.preferred_at-b.preferred_at).total_seconds()) <= 3*3600:
        reasons.append('similar preferred time')
    score = len(reasons)
    return score, ', '.join(dict.fromkeys(reasons)) if reasons else 'No strong compatibility signals yet'


@app.route('/collaboration', methods=['GET', 'POST'])
@role_required('student', 'faculty', 'admin')
def collaboration():
    if request.method == 'POST':
        purpose=request.form.get('purpose','').strip()
        topic=request.form.get('topic','').strip()
        offered=request.form.get('skills_offered','').strip()
        needed=request.form.get('skills_needed','').strip()
        location=request.form.get('location','').strip()
        visibility=request.form.get('visibility','campus')
        try:
            duration=int(request.form.get('duration_hours','1'))
            group_size=int(request.form.get('group_size','2'))
            preferred_raw=request.form.get('preferred_at','').strip()
            preferred=datetime.strptime(preferred_raw,'%Y-%m-%dT%H:%M') if preferred_raw else None
        except (ValueError, TypeError):
            flash('Check the preferred time, duration and group size.', 'danger')
            return redirect(url_for('collaboration'))
        if not purpose or not topic or len(topic)>180 or duration<1 or duration>8 or group_size<2 or group_size>50 or visibility not in ('campus','private'):
            flash('Enter a purpose and topic. Duration must be 1–8 hours and group size 2–50.', 'danger')
        else:
            item=CollaborationRequest(user_id=current_user.id,purpose=purpose[:80],topic=topic,
                skills_offered=offered[:300],skills_needed=needed[:300],preferred_at=preferred,
                duration_hours=duration,location=location[:120],group_size=group_size,visibility=visibility)
            db.session.add(item); db.session.commit()
            flash('Collaboration request published. Compatible requests will show matching reasons.', 'success')
        return redirect(url_for('collaboration'))
    own=CollaborationRequest.query.filter_by(user_id=current_user.id,status='open').order_by(CollaborationRequest.created_at.desc()).all()
    requests_list=CollaborationRequest.query.filter(CollaborationRequest.status=='open',CollaborationRequest.user_id!=current_user.id).order_by(CollaborationRequest.created_at.desc()).limit(100).all()
    ranked=[]
    for item in requests_list:
        if item.visibility=='private':
            continue
        best=(0,'Create your own request to unlock personalized matching')
        for mine in own:
            score,why=collaboration_match(mine,item)
            if score>best[0]: best=(score,why)
        ranked.append({'item':item,'score':best[0],'reason':best[1]})
    ranked.sort(key=lambda x:(-x['score'], x['item'].created_at))
    incoming=CollaborationInvite.query.filter_by(recipient_id=current_user.id,status='pending').order_by(CollaborationInvite.created_at.desc()).all()
    groups=CollaborationGroup.query.join(CollaborationGroupMember).filter(CollaborationGroupMember.user_id==current_user.id).order_by(CollaborationGroup.created_at.desc()).all()
    sent_ids={x.request_id for x in CollaborationInvite.query.filter_by(sender_id=current_user.id).all()}
    return render_template('collaboration.html', own=own, ranked=ranked, incoming=incoming, groups=groups, sent_ids=sent_ids, rooms=Room.query.filter(Room.kind!='library').order_by(Room.code).all())


@app.route('/collaboration/invite/<int:request_id>', methods=['POST'])
@role_required('student','faculty','admin')
def collaboration_invite(request_id):
    target=db.get_or_404(CollaborationRequest,request_id)
    if target.user_id==current_user.id or target.status!='open' or target.visibility=='private':
        abort(400)
    existing=CollaborationInvite.query.filter_by(request_id=target.id,sender_id=current_user.id,recipient_id=target.user_id).first()
    if existing:
        flash('You have already sent an invitation for this request.', 'info')
    else:
        invite=CollaborationInvite(request_id=target.id,sender_id=current_user.id,recipient_id=target.user_id)
        db.session.add(invite)
        notify(target.user_id,f'{current_user.name} invited you to collaborate on: {target.topic}.')
        db.session.commit()
        flash('Collaboration invitation sent. A group is created only after the recipient accepts.', 'success')
    return redirect(url_for('collaboration'))


@app.route('/collaboration/invite/decision/<int:invite_id>/<decision>', methods=['POST'])
@role_required('student','faculty','admin')
def collaboration_invite_decision(invite_id,decision):
    invite=db.get_or_404(CollaborationInvite,invite_id)
    if invite.recipient_id!=current_user.id or invite.status!='pending' or decision not in ('accept','decline'):
        abort(403)
    invite.status='accepted' if decision=='accept' else 'declined'
    if decision=='accept':
        req=invite.request
        group=CollaborationGroup(name=f'{req.topic[:95]} collaboration',objective=f'{req.purpose}: {req.topic}',created_by=req.user_id,preferred_at=req.preferred_at)
        db.session.add(group); db.session.flush()
        for uid in {req.user_id, invite.sender_id, invite.recipient_id}:
            db.session.add(CollaborationGroupMember(group_id=group.id,user_id=uid))
        notify(invite.sender_id,f'{current_user.name} accepted your collaboration invitation. Group #{group.id} is ready.')
        notify(req.user_id,f'{current_user.name} accepted a collaboration invitation for {req.topic}.')
        flash('Invitation accepted and collaboration group created.', 'success')
    else:
        notify(invite.sender_id,f'{current_user.name} declined your collaboration invitation.')
        flash('Invitation declined.', 'info')
    db.session.commit()
    return redirect(url_for('collaboration'))



@app.route('/collaboration/group/<int:group_id>/book', methods=['POST'])
@role_required('student', 'faculty', 'admin')
def collaboration_group_book(group_id):
    group=db.get_or_404(CollaborationGroup,group_id)
    member=CollaborationGroupMember.query.filter_by(group_id=group.id,user_id=current_user.id).first()
    if not member:
        abort(403)
    try:
        room=db.get_or_404(Room,int(request.form.get('room_id','0')))
        starts=datetime.strptime(request.form.get('starts_at',''),'%Y-%m-%dT%H:%M')
        ends=datetime.strptime(request.form.get('ends_at',''),'%Y-%m-%dT%H:%M')
        section=None
        if room.kind.lower() in ('classroom','lab'):
            section_id=int(request.form.get('section_id','0'))
            section=db.session.get(RoomSection,section_id)
            if section is None or section.room_id != room.id or not section.is_active:
                raise ValueError()
            if len(group.members)>section.capacity:
                flash(f'{section.name} fits {section.capacity} people, but your group has {len(group.members)} members.', 'danger')
                return redirect(url_for('collaboration'))
        if ends<=starts or starts<datetime.now()-timedelta(minutes=1):
            raise ValueError()
    except (ValueError,TypeError):
        flash('Choose a valid room, discussion section (for a classroom/lab), and future time range.', 'danger')
        return redirect(url_for('collaboration'))
    conflicts=room_conflicts(room,starts,ends,section_id=section.id if section else None)
    if conflicts:
        flash('Shared room is unavailable: '+'; '.join(conflicts), 'danger')
        return redirect(url_for('collaboration'))
    manual_types={x.strip().lower() for x in os.environ.get('MANUAL_APPROVAL_ROOM_TYPES','lab,seminar').split(',') if x.strip()}
    status='pending' if room.kind.lower() in manual_types else 'approved'
    booking=Booking(user_id=current_user.id,room_id=room.id,section_id=section.id if section else None,
        attendee_count=len(group.members),starts_at=starts,ends_at=ends,
        purpose=f'Collaboration group #{group.id}: {group.objective}'[:500],status=status)
    db.session.add(booking); db.session.flush()
    for gm in group.members:
        target=f'{room.code} · {section.name}' if section else room.code
        notify(gm.user_id,f'Shared room booking #{booking.id} for group "{group.name}" is {status}. {target}, {starts:%d %b %H:%M}.')
    if status=='pending':
        for admin in User.query.filter_by(role='admin').all():
            notify(admin.id,f'Shared room booking #{booking.id} for collaboration group {group.id} needs review.')
    db.session.commit()
    flash('Shared room booking '+('submitted for admin review.' if status=='pending' else 'automatically approved.'), 'success')
    return redirect(url_for('collaboration'))


@app.route('/feedback', methods=['GET', 'POST'])
@role_required('student','faculty','admin')
def feedback():
    if request.method=='POST':
        kind=request.form.get('kind','complaint')
        if kind=='compliment':
            category=request.form.get('compliment_category','').strip()
            description=request.form.get('compliment_description','').strip()
            recipient=request.form.get('recipient','').strip()
            public=request.form.get('is_public')=='yes'
            if not category or not description or len(description)>1200:
                flash('Enter a compliment category and description (up to 1200 characters).','danger')
            else:
                item=Compliment(user_id=current_user.id,recipient=recipient[:160],category=category[:60],description=description,is_public=public)
                db.session.add(item)
                if public:
                    for admin in User.query.filter_by(role='admin').all():
                        notify(admin.id,f'Public compliment submitted: {category}.')
                db.session.commit()
                flash('Thank you for sharing your appreciation.', 'success')
                return redirect(url_for('feedback'))
        else:
            title=request.form.get('title','').strip()
            category=request.form.get('category','').strip()
            description=request.form.get('description','').strip()
            location=request.form.get('location','').strip()
            priority=request.form.get('priority','normal')
            attachment=request.files.get('attachment')
            attachment_name=''
            if attachment and attachment.filename:
                safe_name=secure_filename(attachment.filename)
                ext=os.path.splitext(safe_name)[1].lower()
                if ext not in ('.png','.jpg','.jpeg','.webp'):
                    flash('Complaint attachments must be PNG, JPG, JPEG or WEBP images.', 'danger')
                    return redirect(url_for('feedback'))
                upload_dir=os.path.join(app.instance_path,'complaint_uploads')
                os.makedirs(upload_dir,exist_ok=True)
                attachment_name=f'{secrets.token_hex(16)}{ext}'
                attachment.save(os.path.join(upload_dir,attachment_name))
            if not title or not category or not description or len(title)>160 or len(description)>2000 or priority not in ('low','normal','high','urgent'):
                flash('Enter a title, category and description. Check the allowed lengths and priority.', 'danger')
            else:
                dept_map={'Classroom / Lab':'Facilities','IT / Wi-Fi':'IT Support','Timetable / Booking':'Academic Administration','Library':'Library Services','Cleanliness / Maintenance':'Facilities','Other':'Campus Administration'}
                code=f'CS-{datetime.now():%y%m%d}-{secrets.token_hex(3).upper()}'
                item=Complaint(complaint_code=code,user_id=current_user.id,title=title,category=category[:60],
                    description=description,location=location[:160],priority=priority,assigned_department=dept_map.get(category,'Campus Administration'),attachment_name=attachment_name)
                db.session.add(item); db.session.flush()
                for admin in User.query.filter_by(role='admin').all():
                    notify(admin.id,f'Complaint {code} submitted: {title} — routed to {item.assigned_department}.')
                db.session.commit()
                flash(f'Complaint submitted. Your tracking ID is {code}.', 'success')
                return redirect(url_for('feedback'))
    query=Complaint.query
    if current_user.role!='admin':
        query=query.filter_by(user_id=current_user.id)
    complaints=query.order_by(Complaint.created_at.desc()).limit(100).all()
    # Private compliments are visible only to their author; public compliments can be seen by campus users.
    compliments_query=Compliment.query.filter(or_(Compliment.user_id==current_user.id, Compliment.is_public.is_(True)))
    compliments=compliments_query.order_by(Compliment.created_at.desc()).limit(100).all()
    return render_template('feedback.html',complaints=complaints,compliments=compliments)



@app.route('/feedback/complaint/<int:complaint_id>/attachment')
@role_required('student','faculty','admin')
def complaint_attachment(complaint_id):
    item=db.get_or_404(Complaint,complaint_id)
    if current_user.role!='admin' and item.user_id!=current_user.id:
        abort(403)
    if not item.attachment_name:
        abort(404)
    return send_from_directory(os.path.join(app.instance_path,'complaint_uploads'),item.attachment_name,as_attachment=False)


@app.route('/feedback/complaint/<int:complaint_id>/update', methods=['POST'])
@role_required('admin')
def update_complaint(complaint_id):
    item=db.get_or_404(Complaint,complaint_id)
    status=request.form.get('status','')
    allowed={'Submitted','Assigned','In Progress','Resolved','Reopened'}
    if status not in allowed:
        abort(400)
    item.status=status
    item.resolution_notes=request.form.get('resolution_notes','').strip()[:1200]
    if status=='Reopened' and not item.resolution_notes:
        item.resolution_notes='Reopened for further investigation.'
    notify(item.user_id,f'Complaint {item.complaint_code} status updated to {status}.')
    db.session.commit()
    flash(f'Complaint {item.complaint_code} updated.', 'success')
    return redirect(url_for('feedback'))


@app.route('/admin/timetable/import', methods=['GET','POST'])
@role_required('admin')
def timetable_import():
    result=None
    if request.method=='POST':
        upload=request.files.get('timetable_file')
        if not upload or not upload.filename:
            flash('Choose a CSV or text-based PDF timetable file.', 'danger')
        elif not (upload.filename.lower().endswith('.csv') or upload.filename.lower().endswith('.pdf')):
            flash('Only CSV and PDF files are accepted.', 'danger')
        else:
            try:
                raw=upload.read()
                if upload.filename.lower().endswith('.pdf'):
                    try:
                        from pypdf import PdfReader
                    except ImportError:
                        raise ValueError('PDF support requires pypdf. Install requirements.txt, then retry.')
                    reader=PdfReader(io.BytesIO(raw))
                    extracted='\n'.join(page.extract_text() or '' for page in reader.pages)
                    if not extracted.strip():
                        raise ValueError('This PDF has no extractable text. Scanned PDFs need OCR; upload a CSV or text-based PDF.')
                    pdf_lines=extracted.splitlines()
                    header_index=next((i for i,line in enumerate(pdf_lines) if line.strip().lower().startswith('room_code,')),None)
                    if header_index is not None:
                        extracted='\n'.join(pdf_lines[header_index:])
                    stream=io.StringIO(extracted)
                else:
                    stream=io.StringIO(raw.decode('utf-8-sig'))
                reader=csv.DictReader(stream)
                required={'room_code','title','starts_at','ends_at'}
                if not reader.fieldnames or not required.issubset({h.strip().lower() for h in reader.fieldnames}):
                    raise ValueError('Required columns: room_code,title,starts_at,ends_at. Optional: batch,faculty. Date format: YYYY-MM-DD HH:MM.')
                # Normalize column names, validate the whole upload before writing anything.
                rows=[]
                for line_no,row in enumerate(reader, start=2):
                    row={str(k).strip().lower(): (v or '').strip() for k,v in row.items() if k is not None}
                    if not any(row.values()): continue
                    room=Room.query.filter_by(code=row.get('room_code','').upper()).first()
                    if not room: raise ValueError(f'Row {line_no}: unknown room code {row.get("room_code","")}.')
                    starts=datetime.strptime(row.get('starts_at',''),'%Y-%m-%d %H:%M')
                    ends=datetime.strptime(row.get('ends_at',''),'%Y-%m-%d %H:%M')
                    if not row.get('title','').strip(): raise ValueError(f'Row {line_no}: title is required.')
                    if ends<=starts: raise ValueError(f'Row {line_no}: end must be after start.')
                    if room_conflicts(room,starts,ends): raise ValueError(f'Row {line_no}: room {room.code} conflicts with an existing timetable entry or approved booking.')
                    nonroom=schedule_conflicts(starts,ends,row.get('batch',''),row.get('faculty',''))
                    if nonroom: raise ValueError(f'Row {line_no}: '+ '; '.join(nonroom))
                    rows.append(TimetableEntry(room_id=room.id,title=row.get('title','')[:140],batch=row.get('batch','')[:80],faculty=row.get('faculty','')[:120],starts_at=starts,ends_at=ends))
                # Detect collisions among rows in this upload before commit.
                for i,a in enumerate(rows):
                    for b in rows[i+1:]:
                        if a.room_id==b.room_id and overlaps(a.starts_at,a.ends_at,b.starts_at,b.ends_at):
                            raise ValueError(f'Upload contains overlapping entries for room {a.room.code}.')
                        if a.batch and a.batch==b.batch and overlaps(a.starts_at,a.ends_at,b.starts_at,b.ends_at):
                            raise ValueError(f'Upload contains overlapping sessions for batch {a.batch}.')
                        if a.faculty and a.faculty.lower()==(b.faculty or '').lower() and overlaps(a.starts_at,a.ends_at,b.starts_at,b.ends_at):
                            raise ValueError(f'Upload contains overlapping sessions for faculty {a.faculty}.')
                if not rows: raise ValueError('No timetable rows were found.')
                db.session.add_all(rows); db.session.commit()
                flash(f'Imported {len(rows)} timetable entries after validation.', 'success')
                return redirect(url_for('manage_timetable'))
            except (ValueError,UnicodeDecodeError,csv.Error) as exc:
                db.session.rollback()
                flash(str(exc) or 'Unable to parse timetable file.', 'danger')
            except Exception:
                db.session.rollback()
                app.logger.exception('Timetable import failed')
                flash('Import failed. Check the file format and application logs.', 'danger')
    return render_template('timetable_import.html')



@app.route('/admin/timetable/export')
@role_required('admin')
def timetable_export():
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(['room_code','title','batch','faculty','starts_at','ends_at','cancelled','exception_note'])
    entries=TimetableEntry.query.order_by(TimetableEntry.starts_at.asc()).all()
    for entry in entries:
        writer.writerow([entry.room.code,entry.title,entry.batch or '',entry.faculty or '',
            entry.starts_at.strftime('%Y-%m-%d %H:%M'),entry.ends_at.strftime('%Y-%m-%d %H:%M'),
            'yes' if entry.cancelled else 'no',entry.exception_note or ''])
    data=io.BytesIO(output.getvalue().encode('utf-8-sig'))
    return send_file(data,mimetype='text/csv',as_attachment=True,download_name='campusspace_timetable.csv')


@app.route('/admin/timetable/generate', methods=['GET','POST'])
@role_required('admin')
def timetable_generate():
    result=None
    if request.method=='POST':
        upload=request.files.get('courses_file')
        if not upload or not upload.filename or not upload.filename.lower().endswith('.csv'):
            flash('Upload a course-constraints CSV file.', 'danger')
            return redirect(url_for('timetable_generate'))
        try:
            stream=io.StringIO(upload.read().decode('utf-8-sig'))
            reader=csv.DictReader(stream)
            required={'subject','batch','faculty','weekly_sessions','duration_minutes','students','room_type'}
            if not reader.fieldnames or not required.issubset({h.strip().lower() for h in reader.fieldnames}):
                raise ValueError('Required columns: subject,batch,faculty,weekly_sessions,duration_minutes,students,room_type.')
            courses=[]
            for line_no,row in enumerate(reader,start=2):
                row={str(k).strip().lower():(v or '').strip() for k,v in row.items() if k is not None}
                if not any(row.values()): continue
                try:
                    sessions=int(row['weekly_sessions']); duration=int(row['duration_minutes']); students=int(row['students'])
                except ValueError: raise ValueError(f'Row {line_no}: session count, duration and students must be integers.')
                if not row['subject'] or not row['batch'] or not row['faculty'] or sessions<1 or sessions>5 or duration not in (30,60,90,120) or students<1:
                    raise ValueError(f'Row {line_no}: invalid course details; duration must be 30, 60, 90 or 120 minutes.')
                courses.append({**row,'weekly_sessions_n':sessions,'duration_n':duration,'students_n':students})
            if not courses: raise ValueError('No course requirements found.')
            rooms=Room.query.filter(Room.kind!='library').order_by(Room.capacity).all()
            if not rooms: raise ValueError('No classrooms or labs are configured.')
            today=date.today()
            monday=today+timedelta(days=(7-today.weekday())%7 or 7)
            # Greedy constraint-based scheduling over weekdays and 30-minute start slots.
            planned=[]; failures=[]
            occupied_room=[]; occupied_batch=[]; occupied_faculty=[]
            for course in sorted(courses,key=lambda c:(-c['duration_n']*c['weekly_sessions_n'], -c['students_n'])):
                placed=0
                for session_no in range(course['weekly_sessions_n']):
                    found=None
                    for day_offset in range(5):
                        day=monday+timedelta(days=day_offset)
                        for minute in range(9*60,17*60-course['duration_n']+1,30):
                            st=datetime.combine(day,time(minute//60,minute%60)); en=st+timedelta(minutes=course['duration_n'])
                            for room in rooms:
                                if course['room_type'].lower() not in ('any','classroom/lab','classroom or lab') and room.kind.lower()!=course['room_type'].lower(): continue
                                if room.capacity<course['students_n']: continue
                                if room_conflicts(room,st,en): continue
                                if schedule_conflicts(st,en,course['batch'],course['faculty']): continue
                                if any(x['room'].id==room.id and overlaps(st,en,x['starts_at'],x['ends_at']) for x in planned): continue
                                if any(x['batch'].lower()==course['batch'].lower() and overlaps(st,en,x['starts_at'],x['ends_at']) for x in planned): continue
                                if any(x['faculty'].lower()==course['faculty'].lower() and overlaps(st,en,x['starts_at'],x['ends_at']) for x in planned): continue
                                # Avoid placing two weekly sessions of the same course on the same day.
                                if any(x['subject'].lower()==course['subject'].lower() and x['batch'].lower()==course['batch'].lower() and x['starts_at'].date()==day for x in planned): continue
                                found={'room':room,'title':course['subject'],'batch':course['batch'],'faculty':course['faculty'],'starts_at':st,'ends_at':en}
                                break
                            if found: break
                        if found: break
                    if not found: break
                    planned.append(found); placed+=1
                if placed<course['weekly_sessions_n']:
                    failures.append(f"{course['subject']} ({course['batch']}): placed {placed}/{course['weekly_sessions_n']} sessions")
            if failures:
                summary='; '.join(failures[:5])
                raise ValueError('Could not place every requested session. Nothing was saved. Try adding rooms, reducing constraints or adjusting course requirements. '+summary)
            for item in planned:
                db.session.add(TimetableEntry(room_id=item['room'].id,title=item['title'],batch=item['batch'],faculty=item['faculty'],starts_at=item['starts_at'],ends_at=item['ends_at']))
            db.session.commit()
            flash(f'Generated and saved {len(planned)} sessions for the week starting {monday:%d %b %Y}. Room, batch, faculty and existing timetable conflicts were checked.', 'success')
            return redirect(url_for('manage_timetable'))
        except (ValueError,UnicodeDecodeError,csv.Error) as exc:
            db.session.rollback()
            flash(str(exc), 'danger')
        except Exception:
            db.session.rollback()
            app.logger.exception('Timetable generation failed')
            flash('Generation failed. Check the input and application logs.', 'danger')
    return render_template('timetable_generate.html')


@app.errorhandler(413)
def too_large(e):
    return render_template('error.html', code=413, message='Uploaded file is too large. Maximum size is 8 MB.'), 413


@app.errorhandler(403)
def forbidden(e): return render_template('error.html',code=403,message='You do not have permission to access this page.'),403
@app.errorhandler(404)
def not_found(e): return render_template('error.html',code=404,message='The requested page was not found.'),404

with app.app_context(): seed_data()

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.environ.get('PORT',5000)),debug=os.environ.get('FLASK_DEBUG')=='1')
