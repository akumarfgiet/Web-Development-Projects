from flask import Flask, render_template, request, session, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import date
from flask_login import current_user
import boto3
from flask_migrate import Migrate
from dotenv import load_dotenv
from werkzeug.serving import run_simple

load_dotenv()

app = Flask(__name__)
app.secret_key = '1234AYUSH'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# File Upload - S3 Configuration
S3_BUCKET = os.getenv('S3_BUCKET')
S3_LOCATION = os.getenv('S3_LOCATION')
S3_KEY = os.getenv('S3_ACCESS_KEY')
S3_SECRET = os.getenv('S3_SECRET_KEY')

s3 = boto3.client('s3', aws_access_key_id=S3_KEY, aws_secret_access_key=S3_SECRET)

db = SQLAlchemy(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = "login"

# Models
class users(db.Model, UserMixin):
    User_ID = db.Column(db.Integer, primary_key=True)
    Name = db.Column(db.String(20), nullable=False)
    Email = db.Column(db.String(30), unique=True, nullable=False)
    Password = db.Column(db.String(1000), nullable=False)
    ProfileImage = db.Column(db.String(100), nullable=True)

    posts = db.relationship('posts', backref='user', lazy=True)
    likes = db.relationship('Likes', backref='user', lazy=True)
    comments = db.relationship('comments', backref='user', lazy=True)
    sent_requests = db.relationship('friends', foreign_keys='friends.Request_from_ID', backref='requester', lazy=True)
    received_requests = db.relationship('friends', foreign_keys='friends.Request_to_ID', backref='receiver', lazy=True)

    def get_id(self):
        return str(self.User_ID)

class posts(db.Model):
    Post_ID = db.Column(db.Integer, primary_key=True)
    User_ID = db.Column(db.Integer, db.ForeignKey('users.User_ID'), nullable=False)
    Title = db.Column(db.String(100), nullable=False)
    Image = db.Column(db.String(500), nullable=True)
    Descrip = db.Column(db.String(200), nullable=True)
    Likes = db.Column(db.Integer, nullable=True, default=0)
    Comments = db.Column(db.Integer, nullable=True, default=0)
    Date = db.Column(db.String(20), nullable=False)

    comments = db.relationship('comments', backref='post', lazy=True)
    likes = db.relationship('Likes', backref='post', lazy=True)

class comments(db.Model):
    Comment_ID = db.Column(db.Integer, primary_key=True)
    Post_ID = db.Column(db.Integer, db.ForeignKey('posts.Post_ID'), nullable=False)
    User_ID = db.Column(db.Integer, db.ForeignKey('users.User_ID'), nullable=False)
    comment = db.Column(db.String(200), nullable=False)
    commented_on = db.Column(db.String(100), nullable=True)

class Likes(db.Model):
    __tablename__ = 'Likes'
    id = db.Column(db.Integer, primary_key=True)
    Post_ID = db.Column(db.Integer, db.ForeignKey('posts.Post_ID'), nullable=False)
    User_ID = db.Column(db.Integer, db.ForeignKey('users.User_ID'), nullable=False)

class friends(db.Model):
    Friends_ID = db.Column(db.Integer, primary_key=True)
    Request_from_ID = db.Column(db.Integer, db.ForeignKey('users.User_ID'), nullable=False)
    Request_to_ID = db.Column(db.Integer, db.ForeignKey('users.User_ID'), nullable=False)
    IsAccepted = db.Column(db.String(10), nullable=False)

@login_manager.user_loader
def load_user(User_ID):
    return users.query.get(User_ID)

#routes
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/home", methods=['GET','POST'])
def home_page():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.", 'danger')
        return redirect(url_for("login"))

    posts_data = posts.query.join(users).all()
    return render_template("home.html", data=posts_data)

@app.route("/myprofile", methods=['GET', 'POST'])
def my_profile():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.", 'danger')
        return redirect(url_for("login"))
    user_data = users.query.get(current_user.User_ID)
    return render_template("profile.html", user=user_data)

@app.route("/myposts", methods=['GET','POST'])
def my_posts():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.", 'danger')
        return redirect(url_for("login"))
    posts_data = current_user.posts
    if len(posts_data) == 0:
        return render_template("zeroposts.html")
    return render_template("myposts.html", data=posts_data)

@app.route("/editprofile", methods=['GET', 'POST'])
def edit_profile():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.", 'danger')
        return redirect(url_for("login"))
    if request.method == "POST":
        fetch_file = request.files.get("file")
        file_url = current_user.ProfileImagee
        if fetch_file and fetch_file.filename != "":
            filename = secure_filename(fetch_file.filename)
            try:
                s3.upload_fileobj(fetch_file, S3_BUCKET, filename)
                file_url = f"{S3_LOCATION}{filename}"
            except Exception as e:
                flash(f"File upload failed: {str(e)}", "danger")
                return redirect(url_for("edit_profile"))
        fetch_email = request.form.get("email")
        fetch_name = request.form.get("name")
        user = users.query.get(current_user.User_ID)
        user.Email = fetch_email
        user.Name = fetch_name
        user.ProfileImage = file_url
        db.session.commit()
        flash("Profile Updated Successfully", "success")
        return redirect(url_for("my_profile"))
    return render_template("editprofile.html")
        
@app.route("/comments/<int:id>", methods=['GET', 'POST'])
def all_comments(id):
    if not current_user.is_authenticated:
        flash("Please log in to access this page.",'danger')
        return redirect(url_for("login"))          
    comments_data = comments.query.filter_by(Post_ID=id).all()
    return render_template("comments.html", data=comments_data, post_id=id, count=len(comments_data))

@app.route("/comment/<int:post_id>/<int:user_id>", methods=['GET', 'POST'])
def add_comment(post_id, user_id):
    if request.method == "POST":
        fetch_comment = request.form.get("comment")
        fetch_comment_on = request.form.get("commented_on")
        post = posts.query.get(post_id)
        user = users.query.get(user_id)
        new_comment = comments(
            Post_ID=post_id,
            User_ID=user_id,
            comment=fetch_comment,
            commented_on=fetch_comment_on,
        )
        db.session.add(new_comment)
        db.session.commit()
        if post.Comments is None:
            post.Comments = 1
        else:
            post.Comments += 1
        db.session.commit()
        flash("Comment Added Successfully", "success")
        return redirect(url_for("all_comments", id=post_id))
    return redirect(url_for("home_page"))

@app.route("/connect", methods=['GET', 'POST'])
def connect():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.", 'danger')
        return redirect(url_for("login"))
    users_data = users.query.filter(users.User_ID != current_user.User_ID).all()
    return render_template("connect.html", users=users_data)

@app.route("/connect/search", methods=['GET','POST'])
def search_friend():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.", 'danger')
        return redirect(url_for("login"))
    if request.method == "POST":
        fetch_username = request.form.get("username")
        if fetch_username.lower() == current_user.Name.lower():
            flash("You cannot send a friend request to yourself.", "warning")
            return redirect(url_for("connect"))
        users_data = users.query.filter(users.Name.ilike(f"%{fetch_username}%")).filter(users.User_ID != current_user.User_ID).all()
        if not users_data:
            flash("No users found with that name.", "warning")
            return render_template("searchfriend.html", users=users_data)
        return render_template("searchfriend.html", users=users_data)
    users_data = users.query.filter(users.User_ID != current_user.User_ID).all()
    return render_template("connect.html", users=users_data)

@app.route("/connect/<path:send_to_path>", methods=['GET','POST'])
def connect_with_friends(send_to_path):
    send_from = (send_to_path.split('/'))[0]
    send_to = (send_to_path.split('/'))[1]
    request_from = friends.query.filter_by(Request_from_ID=send_from).first()
    request_to = friends.query.filter_by(Request_to_ID=send_to).first()
    if request_from and request_to:
        flash("Request Already Sent","primary")
        return redirect(url_for("connect", id=send_from))
    else:
        query = f"INSERT INTO `friends`(Request_from_ID,Request_to_ID,IsAccepted) VALUES (%s,%s,%s);"
        with db.engine.begin() as conn:
            response = conn.exec_driver_sql(query,(send_from,send_to,"FALSE"))
            flash("Friend Request Sent!","success")
            return redirect(url_for("connect",id=send_from))
    return redirect(url_for("connect",id=send_from))

@app.route("/remove/<path:send_to_path>", methods=['GET', 'POST'])
def remove_friends(send_to_path):
    send_from = (send_to_path.split('/'))[0]
    send_to = (send_to_path.split('/'))[1]
    request_from = friends.query.filter_by(Request_from_ID=send_from, Request_to_ID=send_to).first()
    request_to = friends.query.filter_by(Request_from_ID=send_to, Request_to_ID=send_from).first()
    if request_from or request_to:
        if request_from:
            db.session.delete(request_from)
        if request_to:
            db.session.delete(request_to)
        db.session.commit()
        flash("Friend Request Cancelled", "warning")
    else:
        flash("No friend request found to cancel.", "danger")
    return redirect(url_for("connect"))

@app.route("/posts", methods=['GET', 'POST'])
def add_post():
    if not current_user.is_authenticated:
        flash("Please log in to access this page.", 'danger')
        return redirect(url_for("login"))
    if request.method == "POST":
        fetch_name = request.form.get("name")
        fetch_title = request.form.get("title")
        fetch_desc = request.form.get("desc")
        fetch_file = request.files.get("file")
        file_url = None
        if fetch_file:
            filename = secure_filename(fetch_file.filename)
            try:
                s3.upload_fileobj(fetch_file, S3_BUCKET, filename)
                file_url = f"{S3_LOCATION}{filename}"
            except Exception as e:
                flash(f"Upload failed: {str(e)}", 'danger')
                return redirect(url_for("add_post"))

        if file_url:
            today_date = str(date.today())
            new_post = posts(
                User_ID=current_user.User_ID,
                Title=fetch_title,
                Image=file_url,
                Descrip=fetch_desc,
                Date=today_date
            )
            try:
                db.session.add(new_post)
                db.session.commit()
                flash("Post Uploaded Successfully", "info")
                return redirect(url_for("home_page"))
            except Exception as e:
                flash(f"An error occurred while saving the post: {str(e)}", "danger")
                db.session.rollback()
        else:
            flash("Please provide a valid file to upload.", "warning")
            return redirect(url_for("add_post"))
    return render_template("posts.html")

@app.route("/like/<int:post_id>/<int:user_id>", methods=['POST'])
def like(post_id, user_id):
    existing_like = Likes.query.filter_by(Post_ID=post_id, User_ID=user_id).first()
    if existing_like:
        flash("You have already liked this post!", "warning")
        return redirect(url_for("home_page"))
    post = posts.query.get(post_id)
    if post.Likes is None:
        post.Likes = 1
    else:
        post.Likes += 1
    db.session.add(post)
    db.session.commit()
    new_like = Likes(Post_ID=post_id, User_ID=user_id)
    db.session.add(new_like)
    db.session.commit()
    flash("You liked this post!", "success")
    return redirect(url_for("home_page"))

@app.route("/login", methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        logout_user()
        return redirect(url_for("login"))
    if request.method=="POST":
        fetch_email = request.form.get("email")
        fetch_pass = request.form.get("password")
        user = users.query.filter_by(Email=fetch_email).first()
        if user and check_password_hash(user.Password, fetch_pass):            
            login_user(user)
            flash("Successfully Logged In!","success")
            return redirect(url_for("home_page"))
        else:
            flash("Incorrect Email or Password","warning")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/signup", methods=['GET','POST'])
def signup():
    if request.method == "POST":
        fetch_name = request.form.get("name")
        fetch_email = request.form.get("email")
        fetch_pass = request.form.get("password")
        hash_pass = generate_password_hash(fetch_pass)

        # Default profile image URL set during signup
        default_profile_image = os.getenv("Default_Image")
        
        query = f"INSERT INTO users (`Name`, `Email`, `Password`, `ProfileImage`) VALUES (%s, %s, %s, %s);"
        with db.engine.begin() as conn:
            response = conn.exec_driver_sql(query, (fetch_name, fetch_email, hash_pass, default_profile_image))
            flash("Account Created Successfully!", "success")
            return redirect(url_for("login"))
    return render_template("signup.html") 

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Successfully Logged Out.",'success')
    return redirect(url_for("login"))

if __name__ == "__main__":
    run_simple('0.0.0.0', int(os.getenv('PORT', 5000)), app)
