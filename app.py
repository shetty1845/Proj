from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from datetime import datetime
from decimal import Decimal
import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(32))

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

print("\n" + "="*80)
print("🎬 CinemaPulse - AWS DynamoDB + SNS Production App")
print("="*80)

# ============================================================================
# AWS PRODUCTION CONFIGURATION (MANDATORY)
# ============================================================================

AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')  # Required: arn:aws:sns:REGION:ACCOUNT:topic-name

# Email Configuration (Gmail App Password)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv('SENDER_EMAIL')  # your-email@gmail.com
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')  # Gmail App Password

# Validate required env vars
required_env = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'SNS_TOPIC_ARN', 'SENDER_EMAIL', 'SENDER_PASSWORD']
missing_env = [var for var in required_env if not os.getenv(var)]
if missing_env:
    raise Exception(f"❌ Missing required environment variables: {', '.join(missing_env)}")

print(f"✅ AWS Region: {AWS_REGION}")
print(f"✅ SNS Topic: {SNS_TOPIC_ARN}")
print(f"✅ Email Config: ✅ SET")

# Initialize AWS Clients
dynamodb = boto3.resource(
    'dynamodb',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)
sns_client = boto3.client(
    'sns',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY
)

# DynamoDB Tables (Pre-created in AWS Console - NO AUTO-CREATION)
users_table = dynamodb.Table('CinemaPulse_Users')
reviews_table = dynamodb.Table('CinemaPulse_Reviews')
movies_table = dynamodb.Table('CinemaPulse_Movies')

# Test AWS Connection
try:
    dynamodb.meta.client.list_tables()
    print("✅ AWS DynamoDB Connected Successfully!")
except Exception as e:
    raise Exception(f"❌ AWS Connection Failed: {e}")

print("="*80 + "\n")

# ============================================================================
# MOVIES DATA (Static - Loaded once into DynamoDB)
# ============================================================================

MOVIES_DATA = [
    {
        'movie_id': 'movie_001',
        'title': 'The Quantum Paradox',
        'description': 'A mind-bending sci-fi thriller exploring parallel universes and quantum mechanics.',
        'genre': 'Sci-Fi',
        'release_year': 2024,
        'director': 'Sarah Mitchell',
        'image_url': 'https://image.tmdb.org/t/p/w500/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg',
        'total_reviews': 0,
        'avg_rating': Decimal('0.0'),
        'active': True,
        'last_updated': datetime.now().isoformat()
    },
    {
        'movie_id': 'movie_002',
        'title': 'Echoes of Tomorrow',
        'description': 'A heartwarming drama about family, time travel, and second chances.',
        'genre': 'Drama',
        'release_year': 2025,
        'director': 'James Chen',
        'image_url': 'https://image.tmdb.org/t/p/w500/kXfqcdQKsToO0OUXHcrrNCHDBzO.jpg',
        'total_reviews': 0,
        'avg_rating': Decimal('0.0'),
        'active': True,
        'last_updated': datetime.now().isoformat()
    },
    {
        'movie_id': 'movie_003',
        'title': 'Shadow Protocol',
        'description': 'An action-packed espionage thriller with explosive sequences and plot twists.',
        'genre': 'Action',
        'release_year': 2025,
        'director': 'Marcus Rodriguez',
        'image_url': 'https://image.tmdb.org/t/p/w500/7WsyChQLEftFiDOVTGkv3hFpyyt.jpg',
        'total_reviews': 0,
        'avg_rating': Decimal('0.0'),
        'active': True,
        'last_updated': datetime.now().isoformat()
    }
    # Add more movies as needed
]

# ============================================================================
# AWS SNS NOTIFICATION SYSTEM
# ============================================================================

def send_sns_notification(message, subject="CinemaPulse Notification"):
    """Send SNS notification for admin alerts"""
    try:
        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject=subject
        )
        print(f"✅ SNS sent: {response['MessageId']}")
        return True
    except Exception as e:
        print(f"⚠️ SNS failed: {e}")
        return False

def send_welcome_email(email, name):
    """Send welcome email to new users"""
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = email
    msg['Subject'] = f"Welcome to CinemaPulse, {name}! 🎬"
    
    body = f"""
Dear {name},

Welcome to CinemaPulse! Your real-time movie feedback platform is ready.

✨ What you can do:
• Rate & review your favorite movies
• Get personalized recommendations
• Track your review analytics
• Share your movie opinions

Start exploring movies and sharing your feedback!

Best regards,
CinemaPulse Team
https://yourdomain.com
    """
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, email, text)
        server.quit()
        print(f"✅ Welcome email sent to {email}")
        return True
    except Exception as e:
        print(f"⚠️ Email failed: {e}")
        return False

def send_review_notification(email, name, movie_title, rating):
    """Send review confirmation email"""
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = email
    msg['Subject'] = f"Your {rating}/5 Review for {movie_title} Saved! 🎥"
    
    body = f"""
Dear {name},

Your review for "{movie_title}" has been successfully saved!

⭐ Your Rating: {rating}/5
📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Thank you for sharing your feedback with CinemaPulse!

Happy movie watching! 🍿
CinemaPulse Team
    """
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        text = msg.as_string()
        server.sendmail(SENDER_EMAIL, email, text)
        server.quit()
        return True
    except Exception as e:
        print(f"⚠️ Review email failed: {e}")
        return False

# ============================================================================
# AUTHENTICATION FUNCTIONS (DYNAMODB)
# ============================================================================

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def register_user(email, password, name):
    """Register new user in DynamoDB"""
    try:
        # Check if user exists
        response = users_table.get_item(Key={'email': email})
        if 'Item' in response:
            return False, "User already exists"
        
        if not is_valid_email(email):
            return False, "Invalid email format"
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        if len(name.strip()) < 2:
            return False, "Name must be at least 2 characters"
        
        password_hash = generate_password_hash(password)
        timestamp = datetime.now().isoformat()
        
        # Create user
        users_table.put_item(Item={
            'email': email,
            'name': name,
            'password_hash': password_hash,
            'created_at': timestamp,
            'total_reviews': 0,
            'avg_rating': Decimal('0.0'),
            'last_review_date': None,
            'is_active': True
        })
        
        # Send notifications
        send_welcome_email(email, name)
        sns_message = f"NEW USER REGISTRATION\n\nName: {name}\nEmail: {email}\nRegistered: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        send_sns_notification(sns_message, "🚨 New CinemaPulse User")
        
        print(f"✅ User registered: {email}")
        return True, "Registration successful"
    except Exception as e:
        print(f"❌ Registration error: {e}")
        return False, "Registration failed"

def login_user(email, password):
    """Login user from DynamoDB"""
    try:
        response = users_table.get_item(Key={'email': email})
        if 'Item' in response:
            user = response['Item']
            if check_password_hash(user['password_hash'], password) and user.get('is_active', True):
                return True, user
        return False, "Invalid credentials"
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False, "Login failed"

def get_user(email):
    """Get user info from DynamoDB"""
    try:
        response = users_table.get_item(Key={'email': email})
        return response.get('Item')
    except Exception as e:
        print(f"❌ Get user error: {e}")
        return None

# ============================================================================
# REVIEW FUNCTIONS (DYNAMODB ONLY)
# ============================================================================

def save_review(name, email, movie_id, rating, feedback_text):
    """Save review to DynamoDB"""
    try:
        timestamp = datetime.now().isoformat()
        review_id = f"{movie_id}#{int(datetime.now().timestamp())}"
        
        # Save review
        reviews_table.put_item(Item={
            'user_email': email,
            'review_id': review_id,
            'movie_id': movie_id,
            'rating': int(rating),
            'feedback': feedback_text,
            'name': name,
            'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'timestamp': timestamp
        })
        
        # Update user stats
        user_response = users_table.get_item(Key={'email': email})
        if 'Item' in user_response:
            user = user_response['Item']
            total_reviews = user.get('total_reviews', 0) + 1
            old_avg = float(user.get('avg_rating', 0))
            new_avg = ((old_avg * (total_reviews - 1)) + rating) / total_reviews
            
            users_table.update_item(
                Key={'email': email},
                UpdateExpression='SET total_reviews = :tr, avg_rating = :ar, last_review_date = :lrd',
                ExpressionAttributeValues={
                    ':tr': total_reviews,
                    ':ar': Decimal(str(new_avg)),
                    ':lrd': datetime.now().strftime("%Y-%m-%d")
                }
            )
        
        # Update movie stats
        movie_reviews = reviews_table.query(
            IndexName='MovieIndex',
            KeyConditionExpression=Key('movie_id').eq(movie_id)
        )
        reviews_list = movie_reviews.get('Items', [])
        total_reviews = len(reviews_list)
        avg_rating = sum(r['rating'] for r in reviews_list) / total_reviews if total_reviews > 0 else 0
        
        movies_table.update_item(
            Key={'movie_id': movie_id},
            UpdateExpression='SET total_reviews = :tr, avg_rating = :ar, last_updated = :lu',
            ExpressionAttributeValues={
                ':tr': total_reviews,
                ':ar': Decimal(str(avg_rating)),
                ':lu': timestamp
            }
        )
        
        # Send notifications
        movie = get_movie_by_id(movie_id)
        send_review_notification(email, name, movie['title'], rating)
        sns_message = f"NEW MOVIE REVIEW\n\nUser: {name} ({email})\nMovie: {movie['title']}\nRating: {rating}/5\nFeedback: {feedback_text[:100]}..."
        send_sns_notification(sns_message, f"⭐ New Review: {movie['title']}")
        
        print(f"✅ Review saved: {name} rated {rating}/5 for {movie_id}")
        return True
        
    except Exception as e:
        print(f"❌ Save review error: {e}")
        return False

def get_movie_reviews(movie_id, limit=20):
    """Get reviews for movie from DynamoDB"""
    try:
        response = reviews_table.query(
            IndexName='MovieIndex',
            KeyConditionExpression=Key('movie_id').eq(movie_id),
            ScanIndexForward=False,
            Limit=limit
        )
        return response.get('Items', [])
    except Exception as e:
        print(f"❌ Get reviews error: {e}")
        return []

def get_user_reviews(email):
    """Get all user reviews from DynamoDB"""
    try:
        response = reviews_table.query(
            KeyConditionExpression=Key('user_email').eq(email)
        )
        return response.get('Items', [])
    except Exception as e:
        print(f"❌ Get user reviews error: {e}")
        return []

def get_all_movies():
    """Get all movies from DynamoDB"""
    try:
        response = movies_table.scan()
        movies = response.get('Items', [])
        for movie in movies:
            movie['avg_rating'] = float(movie.get('avg_rating', 0))
            movie['total_reviews'] = int(movie.get('total_reviews', 0))
        return [m for m in movies if m.get('active', True)]
    except Exception as e:
        print(f"❌ Get movies error: {e}")
        return []

def get_movie_by_id(movie_id):
    """Get specific movie from DynamoDB"""
    try:
        response = movies_table.get_item(Key={'movie_id': movie_id})
        movie = response.get('Item')
        if movie:
            movie['avg_rating'] = float(movie.get('avg_rating', 0))
            movie['total_reviews'] = int(movie.get('total_reviews', 0))
        return movie
    except Exception as e:
        print(f"❌ Get movie error: {e}")
        return None

def calculate_user_average(email):
    """Get user average rating"""
    user = get_user(email)
    return float(user.get('avg_rating', 0)) if user else 0.0

def get_recommendations(email, limit=5):
    """Get movie recommendations"""
    all_movies = get_all_movies()
    user_reviews = get_user_reviews(email)
    
    if not user_reviews:
        return sorted(all_movies, key=lambda x: x.get('avg_rating', 0), reverse=True)[:limit]
    
    # Simple genre-based recommendation
    genres_rated = {}
    for review in user_reviews:
        movie = get_movie_by_id(review['movie_id'])
        if movie:
            genre = movie['genre']
            genres_rated[genre] = genres_rated.get(genre, 0) + review['rating']
    
    recommendations = []
    for movie in all_movies:
        if movie['movie_id'] not in [r['movie_id'] for r in user_reviews]:
            score = genres_rated.get(movie['genre'], 0)
            movie['_rec_score'] = score
            recommendations.append(movie)
    
    return sorted(recommendations, key=lambda x: x.get('_rec_score', 0), reverse=True)[:limit]

# ============================================================================
# AUTH ROUTES
# ============================================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        name = request.form.get('name', '').strip()
        
        success, message = register_user(email, password, name)
        if success:
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        else:
            flash(message, 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        success, result = login_user(email, password)
        if success:
            user = result
            session['user_email'] = email
            session['user_name'] = user.get('name', email.split('@')[0])
            flash('Login successful! Welcome back!', 'success')
            return redirect(url_for('movies'))
        else:
            flash(result, 'danger')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('index'))

# ============================================================================
# MAIN ROUTES (PROTECTED)
# ============================================================================

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/movies')
def movies():
    all_movies = get_all_movies()
    genre_filter = request.args.get('genre', 'all').lower()
    
    if genre_filter != 'all':
        all_movies = [m for m in all_movies if m.get('genre', '').lower() == genre_filter]
    
    all_movies.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
    return render_template('movies.html', movies=all_movies, current_genre=genre_filter)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    movie = get_movie_by_id(movie_id)
    if not movie:
        flash("Movie not found!", "danger")
        return redirect(url_for('movies'))
    
    reviews = get_movie_reviews(movie_id)
    return render_template('movie_detail.html', movie=movie, feedback_list=reviews)

@app.route('/feedback/<movie_id>')
def feedback_page(movie_id):
    if not session.get('user_email'):
        flash('Please login to submit feedback!', 'info')
        return redirect(url_for('login'))
    
    movie = get_movie_by_id(movie_id)
    if not movie:
        flash("Movie not found!", "danger")
        return redirect(url_for('movies'))
    
    return render_template('feedback.html', movie=movie)

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback_route():
    if not session.get('user_email'):
        flash('Please login to submit feedback!', 'danger')
        return redirect(url_for('login'))
    
    movie_id = request.form.get('movie_id')
    name = session.get('user_name')
    email = session.get('user_email')
    feedback_text = request.form.get('feedback', '').strip()
    rating_raw = request.form.get('rating', '')
    
    if not rating_raw or not (1 <= int(rating_raw) <= 5):
        flash('Please select a valid rating (1-5)!', 'danger')
        return redirect(url_for('feedback_page', movie_id=movie_id))
    
    success = save_review(name, email, movie_id, int(rating_raw), feedback_text)
    
    if success:
        flash('Thank you for your review!', 'success')
        return redirect(url_for('thankyou', movie_id=movie_id))
    else:
        flash('Failed to submit review. Please try again.', 'danger')
        return redirect(url_for('feedback_page', movie_id=movie_id))

@app.route('/thankyou')
def thankyou():
    movie_id = request.args.get('movie_id')
    movie = get_movie_by_id(movie_id) if movie_id else None
    
    user_email = session.get('user_email')
    if user_email:
        recommendations = get_recommendations(user_email, 4)
        user_avg = calculate_user_average(user_email)
    else:
        recommendations = []
        user_avg = 0.0
    
    return render_template('thankyou.html', 
                         movie=movie,
                         recommendations=recommendations,
                         user_avg_rating=user_avg)

@app.route('/analytics')
def analytics():
    all_movies = get_all_movies()
    user_email = session.get('user_email')
    
    if user_email:
        user_reviews = get_user_reviews(user_email)
        user_avg = calculate_user_average(user_email)
        recommendations = get_recommendations(user_email, 5)
    else:
        user_reviews = []
        user_avg = 0.0
        recommendations = []
    
    genres = {}
    for m in all_movies:
        genre = m.get('genre', 'Unknown')
        genres[genre] = genres.get(genre, 0) + 1
    
    response = reviews_table.scan(Select='COUNT')
    total_reviews = response.get('Count', 0)
    
    return render_template('analytics.html',
                         total_movies=len(all_movies),
                         total_reviews=total_reviews,
                         top_movies=sorted(all_movies, key=lambda x: x.get('avg_rating', 0), reverse=True)[:10],
                         most_reviewed=sorted(all_movies, key=lambda x: x.get('total_reviews', 0), reverse=True)[:10],
                         genres=genres,
                         recommendations=recommendations,
                         user_name=session.get('user_name'),
                         user_email=user_email,
                         user_avg_rating=round(user_avg, 2),
                         user_total_reviews=len(user_reviews))

@app.route('/my-reviews')
def my_reviews():
    user_email = session.get('user_email')
    if not user_email:
        flash('Please login to see your reviews!', 'info')
        return redirect(url_for('login'))
    
    user_reviews = get_user_reviews(user_email)
    all_movies = get_all_movies()
    
    for review in user_reviews:
        movie = get_movie_by_id(review['movie_id'])
        if movie:
            review['movie_title'] = movie['title']
            review['movie_genre'] = movie['genre']
            review['movie_image'] = movie['image_url']
    
    recommendations = get_recommendations(user_email, 6)
    avg_rating = calculate_user_average(user_email)
    
    return render_template('my_reviews.html',
                         user_name=session.get('user_name'),
                         user_email=user_email,
                         user_feedback=user_reviews,
                         recommendations=recommendations,
                         total_reviews=len(user_reviews),
                         avg_user_rating=avg_rating)

@app.route('/favicon.ico')
def favicon():
    return '', 204

# ============================================================================
# ADMIN INITIALIZATION ENDPOINT (Run once)
# ============================================================================

@app.route('/admin/init-movies', methods=['GET'])
def init_movies():
    """Admin endpoint to initialize movies (run once)"""
    try:
        for movie in MOVIES_DATA:
            movies_table.put_item(Item=movie)
        send_sns_notification("🎬 CinemaPulse movies initialized successfully!", "Movies Initialized")
        return jsonify({"status": "success", "message": f"Initialized {len(MOVIES_DATA)} movies"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ============================================================================
# PRODUCTION RUN
# ============================================================================

if __name__ == '__main__':
    print("="*80)
    print("🚀 CinemaPulse PRODUCTION READY")
    print("💾 Storage: AWS DynamoDB")
    print("📧 Notifications: AWS SNS + Email")
    print("🌐 Access: http://your-ec2-public-ip:5000")
    print("="*80)
    
    # Initialize movies on first run (optional)
    # with app.app_context():
    #     init_movies()
    
    app.run(host='0.0.0.0', port=5000, debug=False)
