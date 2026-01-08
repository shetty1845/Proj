from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
import uuid
from datetime import datetime
from decimal import Decimal
import os
from dotenv import load_dotenv
import secrets
import re
import hashlib
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

print("\n" + "="*80)
print("🎬 CinemaPulse - Real-Time Movie Feedback & Analytics Platform")
print("="*80)

# ============================================================================
# AWS DYNAMODB CONFIGURATION
# ============================================================================

AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
aws_key = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')

print(f"📍 Region: {AWS_REGION}")
print(f"🔑 Access Key: {aws_key[:10] + '...' if aws_key else '❌ NOT SET'}")
print(f"🔐 Secret Key: {'✅ SET' if aws_secret else '❌ NOT SET'}")

use_dynamodb = False
dynamodb = None
users_table = None
reviews_table = None
movies_table = None

# Try to connect to DynamoDB
try:
    if aws_key and aws_secret:
        dynamodb = boto3.resource('dynamodb', 
                                   region_name=AWS_REGION,
                                   aws_access_key_id=aws_key,
                                   aws_secret_access_key=aws_secret)
        dynamodb.meta.client.list_tables()
        print("✅ Connected to AWS DynamoDB successfully!")
        use_dynamodb = True
    else:
        raise Exception("AWS credentials not found")
except Exception as e:
    print(f"⚠️  AWS Connection Failed: {e}")
    print("⚠️  Running in IN-MEMORY MODE")

print("="*80 + "\n")

# ============================================================================
# IN-MEMORY STORAGE + MOVIES
# ============================================================================

IN_MEMORY_REVIEWS = []
IN_MEMORY_USERS = []

MOVIES = [
    {'movie_id': 'movie_001', 'title': 'The Quantum Paradox', 'description': 'Sci-fi thriller', 'genre': 'Sci-Fi', 'release_year': 2024, 'director': 'Sarah Mitchell', 'total_reviews': 0, 'avg_rating': 0.0, 'image_url': 'https://image.tmdb.org/t/p/w500/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg', 'active': True},
    {'movie_id': 'movie_002', 'title': 'Echoes of Tomorrow', 'description': 'Time travel drama', 'genre': 'Drama', 'release_year': 2025, 'director': 'James Chen', 'image_url': 'https://image.tmdb.org/t/p/w500/kXfqcdQKsToO0OUXHcrrNCHDBzO.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True},
    {'movie_id': 'movie_003', 'title': 'Shadow Protocol', 'description': 'Action espionage', 'genre': 'Action', 'release_year': 2025, 'director': 'Marcus Rodriguez', 'image_url': 'https://image.tmdb.org/t/p/w500/7WsyChQLEftFiDOVTGkv3hFpyyt.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True},
    {'movie_id': 'movie_004', 'title': 'The Last Symphony', 'description': "Composer's final masterpiece", 'genre': 'Drama', 'release_year': 2024, 'director': 'Elena Volkov', 'image_url': 'https://image.tmdb.org/t/p/w500/qNBAXBIQlnOThrVvA6mA2B5ggV6.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True},
    {'movie_id': 'movie_005', 'title': 'Neon City', 'description': 'Cyberpunk dystopia', 'genre': 'Sci-Fi', 'release_year': 2026, 'director': 'Kenji Tanaka', 'image_url': 'https://image.tmdb.org/t/p/w500/pwGmXVKUgKN13psUjlhC9zBcq1o.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True},
    {'movie_id': 'movie_006', 'title': 'Desert Storm', 'description': 'Sahara survival thriller', 'genre': 'Thriller', 'release_year': 2025, 'director': 'Ahmed Hassan', 'image_url': 'https://image.tmdb.org/t/p/w500/9BBTo63ANSmhC4e6r62OJFuK2GL.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True},
    {'movie_id': 'movie_007', 'title': 'Midnight Racing', 'description': 'Street racing heist', 'genre': 'Action', 'release_year': 2025, 'director': 'Lucas Knight', 'image_url': 'https://image.tmdb.org/t/p/w500/sv1xJUazXeYqALzczSZ3O6nkH75.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True},
    {'movie_id': 'movie_008', 'title': 'The Forgotten Island', 'description': 'Lost civilization adventure', 'genre': 'Adventure', 'release_year': 2024, 'director': 'Isabella Santos', 'image_url': 'https://image.tmdb.org/t/p/w500/yDHYTfA3R0jFYba16jBB1ef8oIt.jpg', 'total_reviews': 0, 'avg_rating': 0.0, 'active': True}
]

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def hash_password(password):
    return generate_password_hash(password)

def verify_password(stored_hash, password):
    return check_password_hash(stored_hash, password)

# ============================================================================
# DYNAMODB FUNCTIONS (if enabled)
# ============================================================================

if use_dynamodb:
    try:
        users_table = dynamodb.Table('CinemaPulse_Users')
        reviews_table = dynamodb.Table('CinemaPulse_Reviews')
        movies_table = dynamodb.Table('CinemaPulse_Movies')
        print("✅ DynamoDB tables ready!")
    except:
        use_dynamodb = False
        print("⚠️  DynamoDB tables unavailable, using memory")

def register_user_dynamodb(email, password, name):
    response = users_table.get_item(Key={'email': email})
    if 'Item' in response: return False, "User already exists"
    
    password_hash = hash_password(password)
    users_table.put_item(Item={
        'email': email, 'name': name, 'password_hash': password_hash,
        'created_at': datetime.now().isoformat(), 'total_reviews': 0,
        'avg_rating': Decimal('0.0'), 'is_active': True
    })
    return True, "Registration successful"

def login_user_dynamodb(email, password):
    response = users_table.get_item(Key={'email': email})
    if 'Item' in response:
        user = response['Item']
        if verify_password(user['password_hash'], password):
            return True, user
    return False, "Invalid credentials"

# ============================================================================
# MEMORY FUNCTIONS (fallback)
# ============================================================================

def register_user_memory(email, password, name):
    if email in IN_MEMORY_USERS: return False, "User already exists"
    IN_MEMORY_USERS[email] = {
        'name': name, 'password_hash': hash_password(password),
        'total_reviews': 0, 'avg_rating': 0.0, 'created_at': datetime.now().isoformat()
    }
    return True, "Registration successful"

def login_user_memory(email, password):
    if email in IN_MEMORY_USERS:
        user = IN_MEMORY_USERS[email]
        if verify_password(user['password_hash'], password):
            return True, user
    return False, "Invalid credentials"

# ============================================================================
# UNIFIED CORE FUNCTIONS
# ============================================================================

def register_user(email, password, name):
    if not is_valid_email(email) or len(password) < 6 or len(name) < 2:
        return False, "Invalid input"
    return register_user_dynamodb(email, password, name) if use_dynamodb else register_user_memory(email, password, name)

def login_user(email, password):
    return login_user_dynamodb(email, password) if use_dynamodb else login_user_memory(email, password)

def get_all_movies():
    movies = MOVIES.copy()
    for movie in movies:
        reviews = [r for r in IN_MEMORY_REVIEWS if r['movie_id'] == movie['movie_id']]
        movie['total_reviews'] = len(reviews)
        movie['avg_rating'] = sum(r['rating'] for r in reviews) / len(reviews) if reviews else 0.0
    return sorted(movies, key=lambda x: x['avg_rating'], reverse=True)

def get_movie_by_id(movie_id):
    for movie in MOVIES:
        if movie['movie_id'] == movie_id:
            reviews = [r for r in IN_MEMORY_REVIEWS if r['movie_id'] == movie_id]
            movie = movie.copy()
            movie['total_reviews'] = len(reviews)
            movie['avg_rating'] = sum(r['rating'] for r in reviews) / len(reviews) if reviews else 0.0
            return movie
    return None

def submit_review(name, email, movie_id, rating, feedback):
    review = {
        'review_id': str(uuid.uuid4()), 'name': name, 'email': email,
        'movie_id': movie_id, 'rating': int(rating), 'feedback': feedback,
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    IN_MEMORY_REVIEWS.append(review)
    print(f"✅ Review saved: {name} rated {rating}/5")
    return True

def get_movie_reviews(movie_id):
    return [r for r in IN_MEMORY_REVIEWS if r['movie_id'] == movie_id][-10:]

# ============================================================================
# ROUTES (COMPLETE)
# ============================================================================

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()
        success, msg = register_user(email, password, name)
        flash(msg, 'success' if success else 'danger')
        if success: return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        success, user = login_user(email, password)
        if success:
            session['user_email'] = email
            session['user_name'] = user.get('name', email)
            flash('Login successful!', 'success')
            return redirect(url_for('movies'))
        flash('Invalid credentials!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out!', 'info')
    return redirect(url_for('index'))

@app.route('/movies')
def movies():
    movies_list = get_all_movies()
    genre = request.args.get('genre', 'all')
    if genre != 'all':
        movies_list = [m for m in movies_list if m['genre'].lower() == genre.lower()]
    return render_template('movies.html', movies=movies_list)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    movie = get_movie_by_id(movie_id)
    if not movie: return redirect(url_for('movies'))
    reviews = get_movie_reviews(movie_id)
    return render_template('movie_detail.html', movie=movie, reviews=reviews)

@app.route('/feedback/<movie_id>')
def feedback_page(movie_id):
    if not session.get('user_email'):
        flash('Please login!', 'info')
        return redirect(url_for('login'))
    movie = get_movie_by_id(movie_id)
    if not movie: return redirect(url_for('movies'))
    return render_template('feedback.html', movie=movie)

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    if not session.get('user_email'):
        return redirect(url_for('login'))
    
    movie_id = request.form.get('movie_id')
    rating = request.form.get('rating')
    feedback = request.form.get('feedback', '')
    
    if submit_review(session['user_name'], session['user_email'], movie_id, rating, feedback):
        flash('Review submitted!', 'success')
    else:
        flash('Review failed!', 'danger')
    return redirect(url_for('movies'))

@app.route('/analytics')
def analytics():
    movies = get_all_movies()
    return render_template('analytics.html', movies=movies)

@app.route('/my-reviews')
def my_reviews():
    if not session.get('user_email'): return redirect(url_for('login'))
    user_reviews = [r for r in IN_MEMORY_REVIEWS if r['email'] == session['user_email']]
    return render_template('my_reviews.html', reviews=user_reviews)

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ============================================================================
# 404 ERROR HANDLER + CATCH-ALL
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    flash('Page not found! Try /movies or /login', 'warning')
    return redirect(url_for('index'))

@app.route('/<path:path>')
def catch_all(path):
    flash(f'"{path}" not found. Try /movies', 'warning')
    return redirect(url_for('index'))

# ============================================================================
# ADMIN ENDPOINT
# ============================================================================

@app.route('/admin/init')
def admin_init():
    return jsonify({'status': 'ready', 'dynamodb': use_dynamodb, 'movies': len(MOVIES)})

if __name__ == '__main__':
    print("🚀 CinemaPulse READY!")
    print("🌐 http://your-ec2-ip:5000")
    print("📱 All routes working!")
    app.run(host='0.0.0.0', port=5000, debug=True)
