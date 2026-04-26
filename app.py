from flask import Flask, render_template, redirect, url_for, request, session
from flask_limiter import Limiter
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter.util import get_remote_address
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Date, or_
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import pandas as pd

app = Flask(__name__)

database_url = os.environ.get("DATABASE_URL")

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///YearBook.db"

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "HaQa@xK2G@X3")
app.config["WTF_CSRF_TIME_LIMIT"] = 3600
Bootstrap5(app)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,  # switch to True in HTTPS deployment
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[]
)

csrf = CSRFProtect(app)

SQUADS = [str(i) for i in range(1, 24)]
DEPT = ["Accounting", "Biological Science", "Biochemistry", "Chemistry", "English", "History & International Studies",
        "Law", "Management Science", "Mathematics", "Political Science", "Physics", "Sociology"]


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template("csrf_error.html", reason=e.description), 400


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)
db.init_app(app)


class Officers(db.Model):
    __tablename__ = "officers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(250), nullable=False)
    ap_number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    rank: Mapped[str] = mapped_column(String(50), nullable=False, default="ASP")

    is_activated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(), nullable=False)
    last_login: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lockout_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ActivationCodes(db.Model):
    __tablename__ = "activation_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    officer_id: Mapped[int] = mapped_column(ForeignKey("officers.id"), nullable=False, unique=True)

    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(), nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class Profiles(db.Model):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    officer_id: Mapped[int] = mapped_column(ForeignKey("officers.id"), nullable=False, unique=True)

    display_name: Mapped[str] = mapped_column(String(250), nullable=False)
    state_of_origin: Mapped[str] = mapped_column(String(100), nullable=False)
    hometown: Mapped[str] = mapped_column(String(150), nullable=False)
    squad: Mapped[int] = mapped_column(Integer, nullable=False)
    qualification: Mapped[str] = mapped_column(String(250), nullable=False)
    department: Mapped[str] = mapped_column(String(250), nullable=False)

    also_known_as: Mapped[str] = mapped_column(String(250), nullable=True)
    current_posting: Mapped[str] = mapped_column(String(250), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(250), nullable=True)
    about_me: Mapped[str] = mapped_column(String(1000), nullable=True)
    profile_image: Mapped[str] = mapped_column(String(500), nullable=True)

    facebook_link: Mapped[str] = mapped_column(String(250), nullable=True)
    instagram_link: Mapped[str] = mapped_column(String(250), nullable=True)
    x_link: Mapped[str] = mapped_column(String(250), nullable=True)

    consent_given: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(),
                                                 onupdate=lambda: datetime.now(),
                                                 nullable=False)


class PasswordResetRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    officer_id = db.Column(db.Integer, db.ForeignKey('officers.id'), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now())

    officer = db.relationship("Officers", backref="password_reset_requests")


# First helper function-loads Rc7 officers into DB table Officers
def preload_officers():
    df = pd.read_excel("RC7.xlsx")
    existing_ap_numbers = {
        officer.ap_number
        for officer in Officers.query.with_entities(Officers.ap_number).all()
    }

    officers_to_add = []

    for _, row in df.iterrows():
        ap_number = str(row["AP/NO"]).strip()
        full_name = str(row["NAME"]).strip().upper()

        if not ap_number or not full_name:
            continue

        if ap_number in existing_ap_numbers:
            continue

        officer = Officers(
            ap_number=ap_number,
            full_name=full_name,
            is_activated=False,
            is_paid=False,
            is_admin=False,
            rank="ASP"
        )

        officers_to_add.append(officer)
        existing_ap_numbers.add(ap_number)

    db.session.add_all(officers_to_add)
    db.session.commit()

    print(f"{len(officers_to_add)} officers loaded successfully.")


# Second helper function-ensures the officer is logged in.
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("officer_id") is None:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/')
def welcome():
    return render_template('welcome.html')


def normalize_name(name: str) -> [str]:
    return sorted(part for part in name.strip().upper().split() if part)


@app.route('/login', methods=["POST", "GET"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip().upper()
        ap_number = request.form.get("ap_number", "").strip()

        officer = db.session.query(
            Officers.id,
            Officers.full_name,
            Officers.is_activated
        ).filter_by(ap_number=ap_number).first()

        if officer is None:
            return render_template('login.html',
                                   error_message="Invalid AP Number")

        name_entered = normalize_name(full_name)
        name_in_database = normalize_name(officer.full_name)

        if name_in_database != name_entered:
            return render_template('login.html',
                                   error_message="Name does not match our records")

        if officer.is_activated:
            return redirect(url_for("password_login", officer_id=officer.id))
        else:
            return redirect(url_for("create_password", officer_id=officer.id))

    return render_template('login.html')


@app.route('/home')
@login_required
def home():
    officer_id = session.get("officer_id")
    current_officer = db.get_or_404(Officers, officer_id)

    current_profile = Profiles.query.filter_by(officer_id=current_officer.id).first()
    if current_profile is None:
        return redirect(url_for("create_profile"))

    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "name").strip()
    page = request.args.get("page", 1, type=int)

    query = db.session.query(Profiles, Officers).join(
        Officers, Profiles.officer_id == Officers.id
    )

    if search:
        query = query.filter(
            or_(
                Profiles.display_name.ilike(f"%{search}%"),
                Profiles.state_of_origin.ilike(f"%{search}%"),
                Profiles.hometown.ilike(f"%{search}%"),
                Profiles.squad.ilike(f"%{search}%"),
                Officers.full_name.ilike(f"%{search}%"),
                Profiles.department.ilike(f"%{search}%"),
                Profiles.qualification.ilike(f"%{search}%"),
            )
        )

    current_count = Profiles.query.count()
    total_count = Officers.query.count()

    # if sort == "state":
    #     query = query.order_by(Profiles.state_of_origin.asc())
    # elif sort == "squad":
    #     query = query.order_by(Profiles.squad.asc())
    # elif sort == "department":
    #     query = query.order_by(Profiles.squad.asc())
    # else:
    #     query = query.order_by(Profiles.display_name.asc())

    pagination = query.paginate(page=page, per_page=24, error_out=False)
    current_user_profile = Profiles.query.filter_by(
        officer_id=session.get("officer_id")
    ).first()

    return render_template(
        "home.html",
        current_officer=current_officer,
        current_profile=current_profile,
        officers=pagination.items,
        pagination=pagination,
        search=search,
        current_count=current_count,
        total_count=total_count,
        current_user_profile=current_user_profile,
    )


@app.route('/create_profile', methods=["GET", "POST"])
@login_required
def create_profile():
    officer_id = session.get("officer_id")
    officer = db.get_or_404(Officers, officer_id)

    existing_profile = Profiles.query.filter_by(officer_id=officer.id).first()

    if existing_profile:
        return redirect(url_for("home"))

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        also_known_as = request.form.get("also_known_as", "").strip()
        state = request.form.get("state", "").strip()
        hometown = request.form.get("hometown", "").strip()
        date_input = request.form.get("date_of_birth")
        profile_image_url = request.form.get("profile_image_url")
        department = request.form.get("department", "").strip()
        qualification = request.form.get("qualification", "").strip()
        squad = request.form.get("squad", "").strip()
        consent_given = request.form.get("consent_given") == "yes"

        if not consent_given:
            return render_template(
                "create_profile.html",
                squads=SQUADS,
                error_message="Please consent so you can create your profile."
            )

        if date_input:
            try:
                date_of_birth = datetime.strptime(date_input, "%Y-%m-%d").date()
            except ValueError:
                return render_template(
                    "create_profile.html",
                    error_message="Invalid date format. Please use YYYY-MM-DD."
                )
        else:
            date_of_birth = None

        if not display_name:
            return render_template(
                "create_profile.html",
                error_message="Display name is required."
            )

        profile = Profiles(
            officer_id=officer.id,
            display_name=display_name,
            state_of_origin=state,
            hometown=hometown,
            squad=squad,
            date_of_birth=date_of_birth,
            profile_image=profile_image_url,
            qualification=qualification,
            department=department,
            consent_given=consent_given,
            also_known_as=also_known_as,
        )

        db.session.add(profile)
        db.session.commit()

        return redirect(url_for("home"))

    return render_template("create_profile.html", squads=SQUADS, departments=DEPT)


@app.route('/profile/<int:officer_id>')
@login_required
def view_profile(officer_id):
    officer = db.get_or_404(Officers, officer_id)
    profile = Profiles.query.filter_by(officer_id=officer.id).first_or_404()

    is_owner = session.get("officer_id") == officer.id
    updated = request.args.get("updated") == "1"

    return render_template(
        "profile.html",
        officer=officer,
        profile=profile,
        is_owner=is_owner,
        updated=updated,
    )


@app.route('/edit-profile', methods=["GET", "POST"])
@login_required
def edit_profile():
    officer_id = session.get("officer_id")
    officer = db.get_or_404(Officers, officer_id)
    profile = Profiles.query.filter_by(officer_id=officer.id).first_or_404()

    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        also_known_as = request.form.get("also_known_as", "").strip()
        state_of_origin = request.form.get("state", "").strip()
        hometown = request.form.get("hometown", "").strip()
        current_posting = request.form.get("current_posting", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        email = request.form.get("email", "").strip()
        about_me = request.form.get("about_me", "").strip()
        squad = request.form.get("squad", "").strip()
        department = request.form.get("department", "").strip()
        profile_image_url = request.form.get("profile_image_url")

        if not display_name:
            return render_template(
                "edit_profile.html",
                officer=officer,
                profile=profile,
                squads=SQUADS,
                departments=DEPT,
                error_message="Display name is required."
            )

        if squad not in SQUADS:
            return render_template(
                "edit_profile.html",
                officer=officer,
                profile=profile,
                squads=SQUADS,
                departments=DEPT,
                error_message="Please select a valid squad."
            )

        if department not in DEPT:
            return render_template(
                "edit_profile.html",
                officer=officer,
                profile=profile,
                squads=SQUADS,
                departments=DEPT,
                error_message="Please select a valid department."
            )

        date_input = request.form.get("date_of_birth", "").strip()
        if date_input:
            try:
                date_of_birth = datetime.strptime(date_input, "%Y-%m-%d").date()
            except ValueError:
                return render_template(
                    "edit_profile.html",
                    officer=officer,
                    profile=profile,
                    squads=SQUADS,
                    departments=DEPT,
                    error_message="Invalid date format. Please use YYYY-MM-DD."
                )
        else:
            date_of_birth = None

        profile.display_name = display_name
        profile.also_known_as = also_known_as
        profile.state_of_origin = state_of_origin
        profile.hometown = hometown
        profile.current_posting = current_posting
        profile.phone_number = phone_number
        profile.email = email
        profile.about_me = about_me
        profile.squad = squad
        profile.department = department
        profile.date_of_birth = date_of_birth
        if profile_image_url:
            profile.profile_image = profile_image_url

        db.session.commit()
        return redirect(url_for("view_profile", officer_id=officer.id))

    return render_template(
        "edit_profile.html",
        officer=officer,
        profile=profile,
        squads=SQUADS,
        departments=DEPT
    )


@app.route("/admin/reset-requests")
@login_required
def view_reset_requests():
    officer_id = session.get("officer_id")
    officer = db.get_or_404(Officers, officer_id)

    # Simple admin check (you can refine later)
    if not officer.is_admin:
        return "Access denied", 403

    requests = PasswordResetRequest.query.filter_by(is_used=False).all()

    return render_template(
        "admin_reset_requests.html",
        requests=requests
    )


@app.route('/logout')
def logout():
    session.pop("officer_id", None)
    return redirect(url_for('login'))


@app.route("/consent")
def consent():
    return render_template("consent.html")


@app.route('/about')
@login_required
def about():
    return render_template("about.html")


@app.route('/contact')
@login_required
def contact():
    return render_template("contact.html")


@app.route('/password-login/<int:officer_id>', methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def password_login(officer_id):
    officer = db.get_or_404(Officers, officer_id)

    if officer.lockout_until and officer.lockout_until > datetime.now():
        remaining = officer.lockout_until - datetime.now()
        minutes_left = max(1, int(remaining.total_seconds() // 60))
        return render_template(
            "password_login.html",
            officer=officer,
            error_message=f"Too many failed attempts. Try again in about {minutes_left} minute(s)."
        )

    if request.method == "POST":
        password = request.form.get("password", "").strip()

        if not password:
            return render_template(
                "password_login.html",
                officer=officer,
                error_message="Password is required."
            )

        if not check_password_hash(officer.password_hash, password):
            officer.failed_login_attempts += 1

            if officer.failed_login_attempts >= 5:
                officer.lockout_until = datetime.now() + timedelta(minutes=15)
                officer.failed_login_attempts = 0

            db.session.commit()

            return render_template(
                "password_login.html",
                officer=officer,
                error_message="Incorrect password."
            )

        officer.failed_login_attempts = 0
        officer.lockout_until = None
        officer.last_login = datetime.now()
        db.session.commit()

        session["officer_id"] = officer.id
        return redirect(url_for("home"))

    return render_template("password_login.html", officer=officer)


@app.route('/create_password/<int:officer_id>', methods=["GET", "POST"])
def create_password(officer_id):
    officer = db.get_or_404(Officers, officer_id)

    if request.method == "POST":
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not password or not confirm_password:
            return render_template(
                "create_password.html",
                officer=officer,
                error_message="Both password fields are required."
            )

        if password != confirm_password:
            return render_template(
                "create_password.html",
                officer=officer,
                error_message="Passwords do not match."
            )

        officer.password_hash = generate_password_hash(password)
        officer.is_activated = True
        db.session.commit()

        return redirect(url_for("password_login", officer_id=officer.id))

    return render_template("create_password.html", officer=officer)


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    officer_id = session.get("officer_id")
    officer = db.get_or_404(Officers, officer_id)

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(officer.password_hash, current_password):
            return render_template(
                "change_password.html",
                error_message="Current password is incorrect."
            )

        if new_password != confirm_password:
            return render_template(
                "change_password.html",
                error_message="New passwords do not match."
            )

        officer.password_hash = generate_password_hash(new_password)
        db.session.commit()

        return redirect(url_for('home'))

    return render_template("change_password.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        ap_number = request.form.get("ap_number", "").strip()

        officer = Officers.query.filter_by(
            full_name=full_name,
            ap_number=ap_number
        ).first()

        if not officer:
            return render_template(
                "forgot_password.html",
                error_message="Invalid details. Please check your name and AP number."
            )

        existing_request = PasswordResetRequest.query.filter_by(
            officer_id=officer.id,
            is_used=False
        ).first()

        if existing_request:
            return render_template(
                "forgot_password.html",
                success_message="You already have a pending reset request. Please contact admin."
            )

        reset_request = PasswordResetRequest(officer_id=officer.id)
        db.session.add(reset_request)
        db.session.commit()

        return render_template(
            "forgot_password.html",
            success_message="Password reset request submitted successfully. Please contact admin."
        )

    return render_template("forgot_password.html")


@app.route("/admin/reset-password/<int:officer_id>", methods=["POST"])
@login_required
def admin_reset_password(officer_id):
    admin_id = session.get("officer_id")
    admin = db.get_or_404(Officers, admin_id)

    if not admin.is_admin:
        return "Access denied", 403

    officer = db.get_or_404(Officers, officer_id)
    new_password = request.form.get("new_password")

    officer.password_hash = generate_password_hash(new_password)

    # Mark request as handled
    PasswordResetRequest.query.filter_by(
        officer_id=officer.id,
        is_used=False
    ).update({"is_used": True})

    db.session.commit()

    return redirect(url_for("view_reset_requests"))


@app.errorhandler(429)
def ratelimit_handler(e):
    if request.endpoint == "login":
        return render_template("login.html",
                               error_message="Too many attempts. Please wait a minute and try again."), 429

    if request.endpoint == "password_login":
        officer_id = request.view_args.get("officer_id") if request.view_args else None
        officer = Officers.query.get(officer_id) if officer_id else None
        return render_template(
            "password_login.html",
            officer=officer,
            error_message="Too many attempts. Please wait a minute and try again."
        ), 429

    return "Too many requests", 429


@app.route("/robots.txt")
def robots_txt():
    return app.send_static_file("robots.txt")


if __name__ == "__main__":
    app.run(debug=True)
