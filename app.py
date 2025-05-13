import os
from flask import Flask, render_template, redirect, url_for, flash, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, HiddenField
from wtforms.validators import DataRequired, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from config import Config
from flask_migrate import Migrate

# Initialize app and load configuration
app = Flask(__name__)
app.config.from_object(Config)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
migrate = Migrate(app, db)


# Helper for image uploads
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']



# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    house_type = db.Column(db.String(50), nullable=False)  # House Type from dropdown
    price = db.Column(db.String(50), nullable=False)  # Price field (as string e.g., "Ksh 6,500/month")
    content = db.Column(db.String, nullable=False)  # Description field
    location = db.Column(db.String(50), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    image_filename = db.Column(db.String(150), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# Flask-Login user loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Forms
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField('Repeat Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Username already exists. Please choose a different one.')


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class PostForm(FlaskForm):
    title = StringField('House Title', validators=[DataRequired()])
    house_type = SelectField('House Type',
                             choices=[('Bedsitter', 'Bedsitter'), ('1 Bedroom', '1 Bedroom'),
                                      ('2 Bedroom', '2 Bedroom')],
                             validators=[DataRequired()])
    price = StringField('Price', validators=[DataRequired()])
    content = TextAreaField('Description', validators=[DataRequired()])
    location = StringField('Location', validators=[DataRequired()])
    latitude = HiddenField('Latitude')
    longitude = HiddenField('Longitude')
    submit = SubmitField('Submit Post')




# Routes
@app.route("/")
def index():
    return render_template("index.html")


@app.route('/view')
def view():
    posts = Post.query
    house_type = request.args.get('type')
    location = request.args.get('location')

    if house_type:
        posts = posts.filter_by(house_type=house_type)
    if location:
        posts = posts.filter(Post.location.ilike(f"%{location}%"))

    posts = posts.all()
    return render_template('view.html', posts=posts)



@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('post'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful! Please log in.')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('post'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user)
        flash('Logged in successfully.')
        return redirect(url_for('post'))
    return render_template('login.html', form=form)


@app.route('/user/<username>')
def user_posts(username):
    user = User.query.filter_by(username=username).first_or_404()
    posts = Post.query.filter_by(user_id=user.id).all()
    return render_template('user_posts.html', user=user, posts=posts)


@app.route('/post/<int:post_id>')
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    return render_template('post_detail.html', post=post)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('index'))


@app.route('/post', methods=['GET', 'POST'])
@login_required
def post():
    form = PostForm()
    if form.validate_on_submit():
        filename = None
        print(f"Lat: {form.latitude.data}, Lng: {form.longitude.data}")
        # Check if an image file is part of the submission
        if 'image' in request.files:
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        new_post = Post(
            title=form.title.data,
            house_type=form.house_type.data,
            price=form.price.data,
            content=form.content.data,
            location = form.location.data,
            latitude=form.latitude.data,  # ✅ Save lat/lng here
            longitude=form.longitude.data,
            image_filename=filename,
            author=current_user
        )
        db.session.add(new_post)
        db.session.commit()
        flash('Post submitted successfully!')
        return redirect(url_for('update'))
    return render_template('post.html', form=form)


@app.route('/update', methods=['GET', 'POST'])
@login_required
def update():
    posts = Post.query.filter_by(user_id=current_user.id).all()
    if request.method == 'POST':
        if request.form.get('delete'):
            post_id = int(request.form.get('post_id'))
            post_to_delete = Post.query.filter_by(id=post_id, user_id=current_user.id).first()
            if post_to_delete:
                db.session.delete(post_to_delete)
                db.session.commit()
                flash('Post deleted successfully.')
            return redirect(url_for('update'))
        elif request.form.get('edit'):
            post_id = int(request.form.get('post_id'))
            post_to_edit = Post.query.filter_by(id=post_id, user_id=current_user.id).first()
            if post_to_edit:
                post_to_edit.title = request.form.get('title')
                post_to_edit.house_type = request.form.get('house_type')
                post_to_edit.price = request.form.get('price')
                post_to_edit.content = request.form.get('content')
                post_to_edit.location = request.form.get('location')
                db.session.commit()
                flash('Post updated successfully.')
            return redirect(url_for('update'))
    return render_template('update.html', posts=posts)


@app.cli.command('initdb')
def initdb_command():
    """Initialize the database and create upload folder."""
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    print('Initialized the database.')


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

