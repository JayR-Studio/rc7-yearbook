from app import app, db, Officers

with app.app_context():
    officer = Officers.query.filter_by(ap_number="382294").first()

    if officer:
        officer.is_admin = True
        db.session.commit()
        print(f"name: {officer.full_name}, ap_number:{officer.ap_number}, is_admin:{officer.is_admin}. You are now admin.")
