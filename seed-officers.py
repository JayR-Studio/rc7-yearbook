from app import app, preload_officers, Officers


with app.app_context():
    print("DATABASE:", app.config["SQLALCHEMY_DATABASE_URI"])
    if Officers.query.first() is None:
        preload_officers()

    else:
        print("Officers already exists in the database")
