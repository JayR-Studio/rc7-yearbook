from app import app, preload_officers, Officers


with app.app_context():
    if Officers.query.first() is None:
        preload_officers()

    else:
        print("Officers already exists in the database")
