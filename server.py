from flask import Flask, render_template, redirect, url_for, request, session, current_app
from PIL import Image
from flask_limiter import Limiter
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter.util import get_remote_address
from flask_bootstrap import Bootstrap5
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Date, or_
from datetime import datetime, UTC, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from werkzeug.utils import secure_filename
import os
import pandas as pd
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, URL

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "HaQa@xK2G@X3")
app.config["WTF_CSRF_TIME_LIMIT"] = 3600
Bootstrap5(app)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///YearBook.db")
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "webp"}

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


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template("csrf_error.html", reason=e.description), 400


# Helper Function
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in app.config["ALLOWED_EXTENSIONS"]


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

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    last_login: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lockout_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class ActivationCodes(db.Model):
    __tablename__ = "activation_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    officer_id: Mapped[int] = mapped_column(ForeignKey("officers.id"), nullable=False, unique=True)

    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
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

    current_posting: Mapped[str] = mapped_column(String(250), nullable=True)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=True)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=True)
    email: Mapped[str] = mapped_column(String(250), nullable=True)
    about_me: Mapped[str] = mapped_column(String(1000), nullable=True)
    profile_image: Mapped[str] = mapped_column(String(500), nullable=True)

    facebook_link: Mapped[str] = mapped_column(String(250), nullable=True)
    instagram_link: Mapped[str] = mapped_column(String(250), nullable=True)
    x_link: Mapped[str] = mapped_column(String(250), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC),
                                                 onupdate=lambda: datetime.now(UTC),
                                                 nullable=False)


def preload_officers():
    df = pd.read_excel("RC7.xlsx")

    for index, row in df.iterrows():
        ap_number = str(row["AP/NO"]).strip()
        full_name = str(row["NAME"]).strip()

        existing_officer = Officers.query.filter_by(ap_number=ap_number).first()

        if existing_officer is None:
            officer = Officers(
                full_name=full_name,
                ap_number=ap_number
            )
            db.session.add(officer)

    db.session.commit()
    print("Officers imported successfully.")


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


@app.route('/login', methods=["POST", "GET"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip().upper()
        ap_number = request.form.get("ap_number", "").strip()

        officer = Officers.query.filter_by(ap_number=ap_number).first()

        if officer is None:
            return render_template('login.html',
                                   error_message="Invalid AP Number")

        if officer.full_name != full_name.strip().upper():
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

    if sort == "state":
        query = query.order_by(Profiles.state_of_origin.asc())
    elif sort == "squad":
        query = query.order_by(Profiles.squad.asc())
    elif sort == "department":
        query = query.order_by(Profiles.squad.asc())
    else:
        query = query.order_by(Profiles.display_name.asc())

    pagination = query.paginate(page=page, per_page=24, error_out=False)

    return render_template(
        "home.html",
        current_officer=current_officer,
        current_profile=current_profile,
        officers=pagination.items,
        pagination=pagination,
        search=search,
        sort=sort
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
        state = request.form.get("state", "").strip()
        hometown = request.form.get("hometown", "").strip()
        squad = request.form.get("squad", "").strip()
        date_input = request.form.get("date_of_birth")
        profile_image = request.files.get("profile_image")
        department = request.form.get("department").strip()
        qualification = request.form.get("qualification").strip()

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

        image_path = None

        if profile_image and profile_image.filename:
            if not allowed_file(profile_image.filename):
                return render_template(
                    "create_profile.html",
                    error_message="Invalid image format. Use PNG, JPG, JPEG, or WEBP."
                )

            original_filename = secure_filename(profile_image.filename)
            base_name = os.path.splitext(original_filename)[0]
            filename = f"{base_name}.jpg"

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            profile_image.save(save_path)

            img = Image.open(save_path)
            img = img.convert("RGB")
            img.thumbnail((900, 900))
            img.save(save_path, format="JPEG", quality=95, optimize=True)

            image_path = os.path.join("uploads", filename).replace("\\", "/")

        profile = Profiles(
            officer_id=officer.id,
            display_name=display_name,
            state_of_origin=state,
            hometown=hometown,
            squad=squad,
            date_of_birth=date_of_birth,
            profile_image=image_path,
            qualification=qualification,
            department=department,
        )

        db.session.add(profile)
        db.session.commit()

        return redirect(url_for("home"))

    return render_template("create_profile.html")


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
        profile.display_name = request.form.get("display_name", "").strip()
        profile.state_of_origin = request.form.get("state", "").strip()
        profile.hometown = request.form.get("hometown", "").strip()
        profile.squad = request.form.get("squad", "").strip()
        profile.current_posting = request.form.get("current_posting", "").strip()
        profile.phone_number = request.form.get("phone_number", "").strip()
        profile.email = request.form.get("email", "").strip()
        profile.about_me = request.form.get("about_me", "").strip()

        date_input = request.form.get("date_of_birth", "").strip()
        if date_input:
            try:
                profile.date_of_birth = datetime.strptime(date_input, "%Y-%m-%d").date()
            except ValueError:
                return render_template(
                    "edit_profile.html",
                    officer=officer,
                    profile=profile,
                    error_message="Invalid date format. Please use YYYY-MM-DD."
                )
        else:
            profile.date_of_birth = None

        new_image = request.files.get("profile_image")

        if new_image and new_image.filename != "":
            if not allowed_file(new_image.filename):
                return render_template(
                    "edit_profile.html",
                    officer=officer,
                    profile=profile,
                    error_message="Invalid image format. Use PNG, JPG, JPEG, or WEBP."
                )

            original_filename = secure_filename(new_image.filename)
            base_name = os.path.splitext(original_filename)[0]
            filename = f"{base_name}.jpg"

            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            new_image.save(save_path)

            img = Image.open(save_path)
            img = img.convert("RGB")
            img.thumbnail((900, 900))
            img.save(save_path, format="JPEG", quality=95, optimize=True)

            profile.profile_image = os.path.join("uploads", filename).replace("\\", "/")

        if not profile.display_name:
            return render_template(
                "edit_profile.html",
                officer=officer,
                profile=profile,
                error_message="Display name is required."
            )

        db.session.commit()
        return redirect(url_for("view_profile", officer_id=officer.id, updated="1"))

    return render_template("edit_profile.html", officer=officer, profile=profile)


@app.route('/logout')
def logout():
    session.pop("officer_id", None)
    return redirect(url_for('login'))


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

    if officer.lockout_until and officer.lockout_until > datetime.now(UTC):
        remaining = officer.lockout_until - datetime.now(UTC)
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
                officer.lockout_until = datetime.now(UTC) + timedelta(minutes=15)
                officer.failed_login_attempts = 0

            db.session.commit()

            return render_template(
                "password_login.html",
                officer=officer,
                error_message="Incorrect password."
            )

        officer.failed_login_attempts = 0
        officer.lockout_until = None
        officer.last_login = datetime.now(UTC)
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


@app.errorhandler(429)
def ratelimit_handler(e):
    if request.endpoint == "login":
        return render_template("login.html", error_message="Too many attempts. Please wait a minute and try again."), 429

    if request.endpoint == "password_login":
        officer_id = request.view_args.get("officer_id") if request.view_args else None
        officer = Officers.query.get(officer_id) if officer_id else None
        return render_template(
            "password_login.html",
            officer=officer,
            error_message="Too many attempts. Please wait a minute and try again."
        ), 429

    return "Too many requests", 429


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        # preload_officers()
    app.run(debug=False)
