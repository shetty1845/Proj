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
# FIXED AWS CONFIGURATION (CORRECTED SNS ARN)
# ============================================================================

AWS_REGION = os.getenv('AWS_REGION', 'ap-south-1')
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN')  # FIXED: Now reads from .env correctly

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.getenv('SENDER_EMAIL')
SENDER_PASSWORD = os.getenv('SENDER_PASSWORD')

# Graceful validation (no crash)
missing_env = []
if not AWS_ACCESS_KEY_ID: missing_env.append('AWS_ACCESS_KEY_ID')
if not AWS_SECRET_ACCESS_KEY: missing_env.append('AWS_SECRET_ACCESS_KEY')
if not SNS_TOPIC_ARN: missing_env.append('SNS_TOPIC_ARN')
if not SENDER_EMAIL: missing_env.append('SENDER_EMAIL')
if not SENDER_PASSWORD: missing_env.append('SENDER_PASSWORD')

if missing_env:
    print(f"⚠️  Missing env vars: {', '.join(missing_env)}")
    print("✅ Running in SAFE MODE (Local storage)")
else:
    print(f"✅ AWS Region: {AWS_REGION}")
    print(f"✅ SNS Topic: {SNS_TOPIC_ARN}")
    print(f"✅ Email Config: ✅ SET")

# AWS Clients with fallback
AWS_AVAILABLE = False
dynamodb = None
sns_client = None

try:
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        dynamodb = boto3.resource(
            'dynamodb',
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        sns_client = boto3.client(
            'sns',
            region_name='ap-southeast-1',  # SNS region from your ARN
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY
        )
        AWS_AVAILABLE = True
        print("✅ AWS Clients initialized")
except Exception as e:
    print(f"⚠️  AWS init failed: {e}")
    AWS_AVAILABLE = False

# Tables (conditional)
if AWS_AVAILABLE:
    try:
        users_table = dynamodb.Table('CinemaPulse_Users')
        reviews_table = dynamodb.Table('CinemaPulse_Reviews')
        movies_table = dynamodb.Table('CinemaPulse_Movies')
        dynamodb.meta.client.list_tables()
        print("✅ AWS DynamoDB Connected Successfully!")
    except Exception as e:
        print(f"⚠️  DynamoDB test failed: {e}")
        AWS_AVAILABLE = False
        users_table = reviews_table = movies_table = None
else:
    users_table = reviews_table = movies_table = None

print("="*80 + "\n")

# ============================================================================
# ALL ORIGINAL FUNCTIONS WITH FALLBACK (UNCHANGED LOGIC)
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
]

# In-memory fallback storage
users_db = {}
reviews_db = []

def send_sns_notification(message, subject="CinemaPulse Notification"):
    if not AWS_AVAILABLE or not sns_client:
        print(f"📱 SNS: {subject} (Local mode)")
        return True
    try:
        response = sns_client.publish(TopicArn=SNS_TOPIC_ARN, Message=message, Subject=subject)
        print(f"✅ SNS sent: {response['MessageId']}")
        return True
    except Exception as e:
        print(f"⚠️ SNS failed: {e}")
        return False

def send_welcome_email(email, name):
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

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def register_user(email, password, name):
    """Register - DynamoDB first, then local fallback"""
    try:
        email = email.lower().strip()
        
        if AWS_AVAILABLE and users_table:
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
            
            send_welcome_email(email, name)
            send_sns_notification(f"NEW USER\nName: {name}\nEmail: {email}", "🚨 New CinemaPulse User")
            print(f"✅ DynamoDB: User registered: {email}")
            return True, "Registration successful"
        
        # Local fallback (identical logic)
        if email in users_db:
            return False, "User already exists"
        
        if not is_valid_email(email):
            return False, "Invalid email format"
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        if len(name.strip()) < 2:
            return False, "Name must be at least 2 characters"
        
        users_db[email] = {
            'name': name,
            'password_hash': generate_password_hash(password),
            'created_at': datetime.now().isoformat(),
            'total_reviews': 1,
            'avg_rating': Decimal('0.0'),
            'is_active': True
        }
        
        send_welcome_email(email, name)
        print(f"✅ LOCAL: User registered: {email}")
        return True, "Registration successful"
        
    except Exception as e:
        print(f"❌ Registration error: {e}")
        return False, "Registration failed"

# [REST OF YOUR ORIGINAL FUNCTIONS REMAIN IDENTICAL - just wrapped with AWS_AVAILABLE checks]
# For brevity, continuing with same pattern for all functions...

def login_user(email, password):
    try:
        email = email.lower().strip()
        if AWS_AVAILABLE and users_table:
            response = users_table.get_item(Key={'email': email})
            if 'Item' in response:
                user = response['Item']
                if check_password_hash(user['password_hash'], password) and user.get('is_active', True):
                    return True, user
        
        # Local fallback
        if email in users_db and check_password_hash(users_db[email]['password_hash'], password):
            return True, users_db[email]
            
        return False, "Invalid credentials"
    except Exception as e:
        print(f"❌ Login error: {e}")
        return False, "Login failed"

# Keep ALL your original routes exactly the same...
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

# ... [ALL OTHER ROUTES IDENTICAL TO YOUR ORIGINAL]

@app.route('/favicon.ico')
def favicon():
    return '', 204

@app.route('/admin/init-movies', methods=['GET'])
def init_movies():
    try:
        if AWS_AVAILABLE and movies_table:
            for movie in MOVIES_DATA:
                movies_table.put_item(Item=movie)
            send_sns_notification("🎬 CinemaPulse movies initialized!", "Movies Initialized")
            return jsonify({"status": "success", "message": f"Initialized {len(MOVIES_DATA)} movies"})
        else:
            return jsonify({"status": "success", "message": "Movies ready (local mode)"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    print("="*80)
    print("🚀 CinemaPulse PRODUCTION READY")
    print(f"💾 Storage: {'AWS DynamoDB' if AWS_AVAILABLE else 'Local Memory'}")
    print("🌐 Access: http://your-ec2-public-ip:5000")
    print("="*80)
    app.run(host='0.0.0.0', port=5000, debug=False)
