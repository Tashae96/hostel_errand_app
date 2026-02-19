import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime
from markupsafe import Markup  # for nl2br flash messages

# --- Flask app ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'hostel_secret_key'

# --- nl2br filter for flash messages ---
@app.template_filter('nl2br')
def nl2br_filter(s):
    return Markup(s.replace('\n', '<br>'))

# --- Absolute path for database ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
if not os.path.exists(INSTANCE_DIR):
    os.makedirs(INSTANCE_DIR)

DB_PATH = os.path.join(INSTANCE_DIR, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Database and Login ---
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Many-to-many table for joined errands ---
participants = db.Table('participants',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('errand_id', db.Integer, db.ForeignKey('errand.id'), primary_key=True)
)

# --- Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    errands = db.relationship('Errand', backref='user', lazy=True)
    joined_errands = db.relationship('Errand', secondary=participants, backref='joined_users')

class Errand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    priority = db.Column(db.Integer, default=3)

# --- Login manager ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Helper functions ---
def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M")

def is_overlap(start1, end1, start2, end2):
    start1, end1 = parse_time(start1), parse_time(end1)
    start2, end2 = parse_time(start2), parse_time(end2)
    return start1 < end2 and start2 < end1

def find_overlaps(new_errand, existing_errands):
    overlaps = []
    for e in existing_errands:
        if is_overlap(new_errand.start_time, new_errand.end_time, e.start_time, e.end_time):
            overlaps.append(e)
    return overlaps

# --- Routes ---
@app.route('/')
@login_required
def dashboard():
    errands = Errand.query.filter_by(user_id=current_user.id).all()
    all_errands = Errand.query.all()
    for e in errands:
        e.overlaps = find_overlaps(e, [ex for ex in all_errands if ex.id != e.id])
    return render_template('dashboard.html', errands=errands)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(request.args.get('next') or url_for('dashboard'))
        else:
            flash('Invalid credentials', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username exists', 'warning')
            return redirect(url_for('register'))
        new_user = User(username=request.form['username'], password=request.form['password'])
        db.session.add(new_user)
        db.session.commit()
        flash('Registered! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/add_errand', methods=['GET','POST'])
@login_required
def add_errand():
    if request.method=='POST':
        name = request.form['name']
        location = request.form['location']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        priority = int(request.form['priority'])

        new_errand = Errand(user_id=current_user.id, name=name, location=location,
                            start_time=start_time, end_time=end_time, priority=priority)
        overlaps = find_overlaps(new_errand, Errand.query.all())
        if overlaps:
            msg = "⚠ Warning! This errand overlaps with:\n"
            for e in overlaps:
                msg += f"- {e.user.username}'s {e.name} ({e.start_time}-{e.end_time}) at {e.location}\n"
            flash(msg, 'warning')

        db.session.add(new_errand)
        db.session.commit()
        flash('Errand added successfully!', 'success')
        return redirect(url_for('dashboard'))

    errand = None
    return render_template('add_errand.html', errand=errand)

@app.route('/edit_errand/<int:errand_id>', methods=['GET','POST'])
@login_required
def edit_errand(errand_id):
    errand = Errand.query.get_or_404(errand_id)
    if errand.user_id != current_user.id:
        flash("You cannot edit someone else's errand.", "danger")
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        errand.name = request.form['name']
        errand.location = request.form['location']
        errand.start_time = request.form['start_time']
        errand.end_time = request.form['end_time']
        errand.priority = int(request.form['priority'])
        db.session.commit()
        flash("Errand updated successfully!", "success")
        return redirect(url_for('dashboard'))

    return render_template('add_errand.html', errand=errand)

@app.route('/delete_errand/<int:errand_id>')
@login_required
def delete_errand(errand_id):
    errand = Errand.query.get_or_404(errand_id)
    if errand.user_id != current_user.id:
        flash("You cannot delete someone else's errand.", "danger")
        return redirect(url_for('dashboard'))
    db.session.delete(errand)
    db.session.commit()
    flash("Errand deleted successfully.", "success")
    return redirect(url_for('dashboard'))

@app.route('/join_errand/<int:errand_id>')
@login_required
def join_errand(errand_id):
    errand = Errand.query.get_or_404(errand_id)
    if current_user not in errand.joined_users:
        errand.joined_users.append(current_user)
        db.session.commit()
        flash(f"You joined {errand.user.username}'s errand: {errand.name}", 'success')
    else:
        flash("You are already part of this errand.", 'info')
    return redirect(url_for('dashboard'))

# --- Run app ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
