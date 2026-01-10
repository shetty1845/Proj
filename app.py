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

# Initialize DynamoDB
try:
    if not aws_key or not aws_secret:
        raise Exception("AWS credentials not found in .env file")
    
    dynamodb = boto3.resource('dynamodb', 
                               region_name=AWS_REGION,
                               aws_access_key_id=aws_key,
                               aws_secret_access_key=aws_secret)
    
    # Test connection
    dynamodb.meta.client.list_tables()
    print("✅ Connected to AWS DynamoDB successfully!")
    
except Exception as e:
    print(f"❌ FATAL ERROR: Cannot connect to DynamoDB")
    print(f"❌ Error: {e}")
    print(f"❌ Please configure AWS credentials in .env file:")
    print(f"   AWS_ACCESS_KEY_ID=your_access_key")
    print(f"   AWS_SECRET_ACCESS_KEY=your_secret_key")
    print(f"   AWS_REGION=us-east-1")
    print("="*80 + "\n")
    exit(1)

print("="*80 + "\n")

# ============================================================================
# MOVIES DATABASE (Initial Data)
# ============================================================================

MOVIES_INITIAL_DATA = [
    {
        'movie_id': 'movie_001',
        'title': 'The Quantum Paradox',
        'description': 'A mind-bending sci-fi thriller exploring parallel universes and quantum mechanics.',
        'genre': 'Sci-Fi',
        'release_year': 2024,
        'director': 'Sarah Mitchell',
        'image_url': 'https://image.tmdb.org/t/p/w500/8Gxv8gSFCU0XGDykEGv7zR1n2ua.jpg',
    },
    {
        'movie_id': 'movie_002',
        'title': 'Echoes of Tomorrow',
        'description': 'A heartwarming drama about family, time travel, and second chances.',
        'genre': 'Drama',
        'release_year': 2025,
        'director': 'James Chen',
        'image_url': 'https://image.tmdb.org/t/p/w500/kXfqcdQKsToO0OUXHcrrNCHDBzO.jpg',
    },
    {
        'movie_id': 'movie_003',
        'title': 'Shadow Protocol',
        'description': 'An action-packed espionage thriller with explosive sequences and plot twists.',
        'genre': 'Action',
        'release_year': 2025,
        'director': 'Marcus Rodriguez',
        'image_url': 'https://image.tmdb.org/t/p/w500/7WsyChQLEftFiDOVTGkv3hFpyyt.jpg',
    },
    {
        'movie_id': 'movie_004',
        'title': 'The Last Symphony',
        'description': "A biographical drama about a legendary composer's final masterpiece.",
        'genre': 'Drama',
        'release_year': 2024,
        'director': 'Elena Volkov',
        'image_url': 'https://image.tmdb.org/t/p/w500/qNBAXBIQlnOThrVvA6mA2B5ggV6.jpg',
    },
    {
        'movie_id': 'movie_005',
        'title': 'Neon City',
        'description': 'A cyberpunk adventure set in a dystopian future with stunning visuals.',
        'genre': 'Sci-Fi',
        'release_year': 2026,
        'director': 'Kenji Tanaka',
        'image_url': 'https://image.tmdb.org/t/p/w500/pwGmXVKUgKN13psUjlhC9zBcq1o.jpg',
    },
    {
        'movie_id': 'movie_006',
        'title': 'Desert Storm',
        'description': 'A survival thriller about a group stranded in the Sahara Desert.',
        'genre': 'Thriller',
        'release_year': 2025,
        'director': 'Ahmed Hassan',
        'image_url': 'https://image.tmdb.org/t/p/w500/9BBTo63ANSmhC4e6r62OJFuK2GL.jpg',
    },
    {
        'movie_id': 'movie_007',
        'title': 'Midnight Racing',
        'description': 'Underground street racing meets high-stakes heist in this adrenaline rush.',
        'genre': 'Action',
        'release_year': 2025,
        'director': 'Lucas Knight',
        'image_url': 'https://image.tmdb.org/t/p/w500/sv1xJUazXeYqALzczSZ3O6nkH75.jpg',
    },
    {
        'movie_id': 'movie_008',
        'title': 'The Forgotten Island',
        'description': 'Archaeologists discover a mysterious civilization on a remote island.',
        'genre': 'Adventure',
        'release_year': 2024,
        'director': 'Isabella Santos',
        'image_url': 'https://image.tmdb.org/t/p/w500/yDHYTfA3R0jFYba16jBB1ef8oIt.jpg',
    }
]

# ============================================================================
# DYNAMODB TABLE INITIALIZATION
# ============================================================================

def create_dynamodb_tables():
    """Create DynamoDB tables if they don't exist"""
    try:
        existing_tables = dynamodb.meta.client.list_tables()['TableNames']
        print(f"📋 Existing DynamoDB tables: {existing_tables}")
        
        # ========== USERS TABLE ==========
        USERS_TABLE_NAME = 'CinemaPulse_Users'
        if USERS_TABLE_NAME not in existing_tables:
            print(f"🔨 Creating {USERS_TABLE_NAME} table...")
            table = dynamodb.create_table(
                TableName=USERS_TABLE_NAME,
                KeySchema=[
                    {'AttributeName': 'email', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'email', 'AttributeType': 'S'}
                ],
                BillingMode='PAY_PER_REQUEST',
                Tags=[{'Key': 'Application', 'Value': 'CinemaPulse'}]
            )
            table.wait_until_exists()
            print(f"✅ {USERS_TABLE_NAME} created successfully!")
        else:
            print(f"✅ {USERS_TABLE_NAME} already exists")
        
        # ========== REVIEWS TABLE ==========
        REVIEWS_TABLE_NAME = 'CinemaPulse_Reviews'
        if REVIEWS_TABLE_NAME not in existing_tables:
            print(f"🔨 Creating {REVIEWS_TABLE_NAME} table with GSI...")
            table = dynamodb.create_table(
                TableName=REVIEWS_TABLE_NAME,
                KeySchema=[
                    {'AttributeName': 'review_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'review_id', 'AttributeType': 'S'},
                    {'AttributeName': 'user_email', 'AttributeType': 'S'},
                    {'AttributeName': 'movie_id', 'AttributeType': 'S'},
                    {'AttributeName': 'created_at', 'AttributeType': 'S'}
                ],
                GlobalSecondaryIndexes=[
                    {
                        'IndexName': 'MovieIndex',
                        'KeySchema': [
                            {'AttributeName': 'movie_id', 'KeyType': 'HASH'},
                            {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    },
                    {
                        'IndexName': 'UserIndex',
                        'KeySchema': [
                            {'AttributeName': 'user_email', 'KeyType': 'HASH'},
                            {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                        ],
                        'Projection': {'ProjectionType': 'ALL'}
                    }
                ],
                BillingMode='PAY_PER_REQUEST',
                Tags=[{'Key': 'Application', 'Value': 'CinemaPulse'}]
            )
            table.wait_until_exists()
            print(f"✅ {REVIEWS_TABLE_NAME} created successfully!")
        else:
            print(f"✅ {REVIEWS_TABLE_NAME} already exists")
        
        # ========== MOVIES TABLE ==========
        MOVIES_TABLE_NAME = 'CinemaPulse_Movies'
        if MOVIES_TABLE_NAME not in existing_tables:
            print(f"🔨 Creating {MOVIES_TABLE_NAME} table...")
            table = dynamodb.create_table(
                TableName=MOVIES_TABLE_NAME,
                KeySchema=[
                    {'AttributeName': 'movie_id', 'KeyType': 'HASH'}
                ],
                AttributeDefinitions=[
                    {'AttributeName': 'movie_id', 'AttributeType': 'S'}
                ],
                BillingMode='PAY_PER_REQUEST',
                Tags=[{'Key': 'Application', 'Value': 'CinemaPulse'}]
            )
            table.wait_until_exists()
            print(f"✅ {MOVIES_TABLE_NAME} created successfully!")
        else:
            print(f"✅ {MOVIES_TABLE_NAME} already exists")
        
        print("\n✅ All DynamoDB tables are ready!\n")
        return True
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        import traceback
        traceback.print_exc()
        return False

# Initialize tables
print("🔄 Initializing DynamoDB tables...\n")
if not create_dynamodb_tables():
    print("❌ Failed to initialize DynamoDB tables. Exiting...")
    exit(1)

# Get table references
users_table = dynamodb.Table('CinemaPulse_Users')
reviews_table = dynamodb.Table('CinemaPulse_Reviews')
movies_table = dynamodb.Table('CinemaPulse_Movies')

# ============================================================================
# INITIALIZE MOVIES IN DYNAMODB
# ============================================================================

def initialize_movies():
    """Initialize movies in DynamoDB if not already present"""
    print("📽️  Initializing movies in DynamoDB...")
    initialized_count = 0
    
    for movie in MOVIES_INITIAL_DATA:
        try:
            # Check if movie exists
            response = movies_table.get_item(Key={'movie_id': movie['movie_id']})
            
            if 'Item' not in response:
                # Movie doesn't exist, create it
                movies_table.put_item(Item={
                    'movie_id': movie['movie_id'],
                    'title': movie['title'],
                    'description': movie['description'],
                    'genre': movie['genre'],
                    'release_year': movie['release_year'],
                    'director': movie['director'],
                    'image_url': movie['image_url'],
                    'total_reviews': 0,
                    'avg_rating': Decimal('0.0'),
                    'active': True,
                    'created_at': datetime.now().isoformat(),
                    'last_updated': datetime.now().isoformat()
                })
                initialized_count += 1
                print(f"   ✅ Added: {movie['title']}")
            
        except Exception as e:
            print(f"   ⚠️  Error with {movie['movie_id']}: {e}")
    
    if initialized_count > 0:
        print(f"✅ Initialized {initialized_count} new movies!")
    else:
        print(f"✅ All {len(MOVIES_INITIAL_DATA)} movies already exist in DynamoDB")
    print()

initialize_movies()

# ============================================================================
# HELPER FUNCTIONS - VALIDATION
# ============================================================================

def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def hash_password(password):
    """Hash password securely"""
    return generate_password_hash(password)

def verify_password(stored_hash, password):
    """Verify password against hash"""
    return check_password_hash(stored_hash, password)

# ============================================================================
# USER MANAGEMENT - DYNAMODB
# ============================================================================

def register_user(email, password, name):
    """Register new user in DynamoDB"""
    try:
        # Validate inputs
        if not is_valid_email(email):
            return False, "Invalid email format"
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        if len(name.strip()) < 2:
            return False, "Name must be at least 2 characters"
        
        email = email.strip().lower()
        name = name.strip()
        
        # Check if user exists
        response = users_table.get_item(Key={'email': email})
        if 'Item' in response:
            return False, "User already exists"
        
        # Create new user
        password_hash = hash_password(password)
        timestamp = datetime.now().isoformat()
        
        users_table.put_item(Item={
            'email': email,
            'name': name,
            'password_hash': password_hash,
            'created_at': timestamp,
            'total_reviews': 0,
            'avg_rating': Decimal('0.0'),
            'last_review_date': '',
            'is_active': True
        })
        
        print(f"✅ New user registered: {email}")
        return True, "Registration successful"
        
    except Exception as e:
        print(f"❌ Error registering user: {e}")
        import traceback
        traceback.print_exc()
        return False, "Registration failed. Please try again."

def login_user(email, password):
    """Login user from DynamoDB"""
    try:
        email = email.strip().lower()
        
        response = users_table.get_item(Key={'email': email})
        
        if 'Item' in response:
            user = response['Item']
            if verify_password(user['password_hash'], password):
                if user.get('is_active', True):
                    print(f"✅ User logged in: {email}")
                    return True, user
                else:
                    return False, "Account is deactivated"
            else:
                return False, "Invalid email or password"
        else:
            return False, "Invalid email or password"
            
    except Exception as e:
        print(f"❌ Error during login: {e}")
        import traceback
        traceback.print_exc()
        return False, "Login failed. Please try again."

def get_user(email):
    """Get user info from DynamoDB"""
    try:
        response = users_table.get_item(Key={'email': email})
        return response.get('Item')
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None

# ============================================================================
# MOVIE MANAGEMENT - DYNAMODB
# ============================================================================

def get_all_movies():
    """Get all active movies from DynamoDB"""
    try:
        response = movies_table.scan(
            FilterExpression=Attr('active').eq(True)
        )
        
        movies = response.get('Items', [])
        
        # Convert Decimal to float for JSON serialization
        for movie in movies:
            movie['avg_rating'] = float(movie.get('avg_rating', 0))
            movie['total_reviews'] = int(movie.get('total_reviews', 0))
        
        return movies
        
    except Exception as e:
        print(f"❌ Error getting movies: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_movie_by_id(movie_id):
    """Get specific movie from DynamoDB"""
    try:
        response = movies_table.get_item(Key={'movie_id': str(movie_id)})
        
        if 'Item' in response:
            movie = response['Item']
            movie['avg_rating'] = float(movie.get('avg_rating', 0))
            movie['total_reviews'] = int(movie.get('total_reviews', 0))
            return movie
        
        return None
        
    except Exception as e:
        print(f"❌ Error getting movie: {e}")
        return None

def update_movie_stats(movie_id):
    """Update movie statistics based on reviews"""
    try:
        # Get all reviews for this movie
        response = reviews_table.query(
            IndexName='MovieIndex',
            KeyConditionExpression=Key('movie_id').eq(movie_id)
        )
        
        reviews = response.get('Items', [])
        total_reviews = len(reviews)
        
        if total_reviews > 0:
            avg_rating = sum(r['rating'] for r in reviews) / total_reviews
        else:
            avg_rating = 0.0
        
        # Update movie
        movies_table.update_item(
            Key={'movie_id': movie_id},
            UpdateExpression='SET total_reviews = :tr, avg_rating = :ar, last_updated = :lu',
            ExpressionAttributeValues={
                ':tr': total_reviews,
                ':ar': Decimal(str(round(avg_rating, 2))),
                ':lu': datetime.now().isoformat()
            }
        )
        
        print(f"✅ Updated movie stats: {movie_id} - {total_reviews} reviews, {avg_rating:.2f} avg")
        return True
        
    except Exception as e:
        print(f"❌ Error updating movie stats: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# REVIEW MANAGEMENT - DYNAMODB
# ============================================================================

def submit_review(name, email, movie_id, rating, feedback_text):
    """Submit a movie review to DynamoDB"""
    try:
        timestamp = datetime.now().isoformat()
        review_id = f"{str(uuid.uuid4())}"
        
        # Save review
        reviews_table.put_item(Item={
            'review_id': review_id,
            'user_email': email,
            'movie_id': movie_id,
            'name': name,
            'rating': int(rating),
            'feedback': feedback_text,
            'created_at': timestamp,
            'display_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        
        print(f"✅ Review saved: {review_id}")
        
        # Update movie statistics
        update_movie_stats(movie_id)
        
        # Update user statistics
        update_user_stats(email)
        
        return True
        
    except Exception as e:
        print(f"❌ Error submitting review: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_movie_reviews(movie_id, limit=50):
    """Get all reviews for a movie from DynamoDB"""
    try:
        response = reviews_table.query(
            IndexName='MovieIndex',
            KeyConditionExpression=Key('movie_id').eq(movie_id),
            ScanIndexForward=False,
            Limit=limit
        )
        
        reviews = response.get('Items', [])
        
        # Convert Decimal to int for ratings
        for review in reviews:
            review['rating'] = int(review.get('rating', 0))
        
        return reviews
        
    except Exception as e:
        print(f"❌ Error getting movie reviews: {e}")
        import traceback
        traceback.print_exc()
        return []

def get_user_reviews(email):
    """Get all reviews by user from DynamoDB"""
    try:
        response = reviews_table.query(
            IndexName='UserIndex',
            KeyConditionExpression=Key('user_email').eq(email),
            ScanIndexForward=False
        )
        
        reviews = response.get('Items', [])
        
        # Convert Decimal to int and add movie details
        for review in reviews:
            review['rating'] = int(review.get('rating', 0))
            
            # Get movie details
            movie = get_movie_by_id(review['movie_id'])
            if movie:
                review['movie_title'] = movie['title']
                review['movie_genre'] = movie['genre']
                review['movie_image'] = movie['image_url']
        
        return reviews
        
    except Exception as e:
        print(f"❌ Error getting user reviews: {e}")
        import traceback
        traceback.print_exc()
        return []

def update_user_stats(email):
    """Update user statistics based on reviews"""
    try:
        # Get all user reviews
        response = reviews_table.query(
            IndexName='UserIndex',
            KeyConditionExpression=Key('user_email').eq(email)
        )
        
        reviews = response.get('Items', [])
        total_reviews = len(reviews)
        
        if total_reviews > 0:
            avg_rating = sum(r['rating'] for r in reviews) / total_reviews
            last_review = max(r['created_at'] for r in reviews)
        else:
            avg_rating = 0.0
            last_review = ''
        
        # Update user
        users_table.update_item(
            Key={'email': email},
            UpdateExpression='SET total_reviews = :tr, avg_rating = :ar, last_review_date = :lrd',
            ExpressionAttributeValues={
                ':tr': total_reviews,
                ':ar': Decimal(str(round(avg_rating, 2))),
                ':lrd': last_review
            }
        )
        
        print(f"✅ Updated user stats: {email} - {total_reviews} reviews, {avg_rating:.2f} avg")
        return True
        
    except Exception as e:
        print(f"❌ Error updating user stats: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================================================
# RECOMMENDATIONS ENGINE
# ============================================================================

def get_recommendations(email, limit=5):
    """Get personalized movie recommendations"""
    try:
        all_movies = get_all_movies()
        user_reviews = get_user_reviews(email)
        
        if not user_reviews:
            # No reviews yet - return top-rated movies
            return sorted(all_movies, key=lambda x: x.get('avg_rating', 0), reverse=True)[:limit]
        
        # Analyze user preferences
        genre_ratings = {}
        rated_movie_ids = set()
        
        for review in user_reviews:
            rated_movie_ids.add(review['movie_id'])
            rating = review.get('rating', 0)
            genre = review.get('movie_genre', 'Unknown')
            
            if genre not in genre_ratings:
                genre_ratings[genre] = []
            genre_ratings[genre].append(rating)
        
        # Find favorite genres (avg rating >= 4)
        favorite_genres = []
        for genre, ratings in genre_ratings.items():
            avg = sum(ratings) / len(ratings)
            if avg >= 4:
                favorite_genres.append(genre)
        
        # Get unwatched movies from favorite genres
        recommendations = [
            m for m in all_movies 
            if m['movie_id'] not in rated_movie_ids 
            and m.get('genre') in favorite_genres
        ]
        
        # Sort by rating
        recommendations.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
        
        # If not enough recommendations, add top-rated unwatched movies
        if len(recommendations) < limit:
            other_movies = [
                m for m in all_movies 
                if m['movie_id'] not in rated_movie_ids 
                and m not in recommendations
            ]
            other_movies.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
            recommendations.extend(other_movies[:limit - len(recommendations)])
        
        return recommendations[:limit]
        
    except Exception as e:
        print(f"❌ Error getting recommendations: {e}")
        return []

# ============================================================================
# ANALYTICS FUNCTIONS
# ============================================================================

def get_total_reviews_count():
    """Get total number of reviews in system"""
    try:
        response = reviews_table.scan(Select='COUNT')
        return response.get('Count', 0)
    except Exception as e:
        print(f"❌ Error getting total reviews: {e}")
        return 0

def get_genre_distribution():
    """Get distribution of movies by genre"""
    try:
        movies = get_all_movies()
        genres = {}
        for movie in movies:
            genre = movie.get('genre', 'Unknown')
            genres[genre] = genres.get(genre, 0) + 1
        return genres
    except Exception as e:
        print(f"❌ Error getting genre distribution: {e}")
        return {}

# ============================================================================
# FLASK ROUTES - AUTHENTICATION
# ============================================================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration page"""
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
    """User login page"""
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
    """User logout"""
    session.clear()
    flash('Logged out successfully!', 'info')
    return redirect(url_for('index'))

# ============================================================================
# FLASK ROUTES - MAIN APPLICATION
# ============================================================================

@app.route('/')
def index():
    """Home page"""
    return render_template('home.html')

@app.route('/movies')
def movies():
    """Movies listing page"""
    all_movies = get_all_movies()
    genre_filter = request.args.get('genre', 'all').lower()
    
    if genre_filter != 'all':
        all_movies = [m for m in all_movies if m.get('genre', '').lower() == genre_filter]
    
    # Sort by average rating
    all_movies.sort(key=lambda x: x.get('avg_rating', 0), reverse=True)
    
    return render_template('movies.html', movies=all_movies, current_genre=genre_filter)

@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    """Movie detail page"""
    movie = get_movie_by_id(movie_id)
    
    if not movie:
        flash("Movie not found!", "danger")
        return redirect(url_for('movies'))
    
    reviews = get_movie_reviews(movie_id)
    
    return render_template('movie_detail.html', movie=movie, feedback_list=reviews)

@app.route('/feedback/<movie_id>')
def feedback_page(movie_id):
    """Feedback submission page"""
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
    """Handle feedback submission"""
    try:
        print("\n" + "="*50)
        print("📝 FEEDBACK SUBMISSION")
        print("="*50)
        
        # Check authentication
        if not session.get('user_email'):
            flash('Please login to submit feedback!', 'danger')
            return redirect(url_for('login'))
        
        # Get form data
        movie_id = request.form.get('movie_id', '').strip()
        feedback_text = request.form.get('feedback', '').strip()
        rating_raw = request.form.get('rating', '')
        
        name = session.get('user_name', '')
        email = session.get('user_email', '')
        
        print(f"User: {name} ({email})")
        print(f"Movie ID: {movie_id}")
        print(f"Rating: {rating_raw}")
        print(f"Feedback: {feedback_text[:100]}...")
        
        # Validation
        if not movie_id or not feedback_text or not rating_raw:
            flash('All fields are required!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        try:
            rating = int(rating_raw)
            if rating < 1 or rating > 5:
                raise ValueError("Rating must be between 1 and 5")
        except ValueError:
            flash('Invalid rating value!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        if len(feedback_text) < 10:
            flash('Feedback must be at least 10 characters long!', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
        # Verify movie exists
        movie = get_movie_by_id(movie_id)
        if not movie:
            flash('Invalid movie!', 'danger')
            return redirect(url_for('movies'))
        
        # Submit review
        success = submit_review(name, email, movie_id, rating, feedback_text)
        
        if success:
            print("✅ Feedback submitted successfully!")
            print("="*50 + "\n")
            flash('Thank you for your feedback! 🎉', 'success')
            return redirect(url_for('movie_detail', movie_id=movie_id))
        else:
            print("❌ Feedback submission failed!")
            print("="*50 + "\n")
            flash('Failed to submit feedback. Please try again.', 'danger')
            return redirect(url_for('feedback_page', movie_id=movie_id))
        
    except Exception as e:
        print(f"❌ Error in submit_feedback_route: {e}")
        import traceback
        traceback.print_exc()
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('movies'))

@app.route('/dashboard')
def dashboard():
    """User dashboard page"""
    if not session.get('user_email'):
        flash('Please login to view your dashboard!', 'info')
        return redirect(url_for('login'))
    
    email = session.get('user_email')
    user = get_user(email)
    user_reviews = get_user_reviews(email)
    recommendations = get_recommendations(email)
    
    return render_template('dashboard.html', 
                         user=user, 
                         reviews=user_reviews, 
                         recommendations=recommendations)

@app.route('/analytics')
def analytics():
    """Analytics dashboard page"""
    if not session.get('user_email'):
        flash('Please login to view analytics!', 'info')
        return redirect(url_for('login'))
    
    # Get analytics data
    all_movies = get_all_movies()
    total_reviews = get_total_reviews_count()
    genre_dist = get_genre_distribution()
    
    # Top rated movies
    top_movies = sorted(all_movies, key=lambda x: x.get('avg_rating', 0), reverse=True)[:5]
    
    # Most reviewed movies
    most_reviewed = sorted(all_movies, key=lambda x: x.get('total_reviews', 0), reverse=True)[:5]
    
    return render_template('analytics.html',
                         total_movies=len(all_movies),
                         total_reviews=total_reviews,
                         genre_distribution=genre_dist,
                         top_movies=top_movies,
                         most_reviewed=most_reviewed)

# ============================================================================
# API ENDPOINTS (JSON)
# ============================================================================

@app.route('/api/movies')
def api_movies():
    """API: Get all movies"""
    movies = get_all_movies()
    return jsonify({'success': True, 'movies': movies})

@app.route('/api/movie/<movie_id>')
def api_movie_detail(movie_id):
    """API: Get movie details"""
    movie = get_movie_by_id(movie_id)
    if movie:
        return jsonify({'success': True, 'movie': movie})
    else:
        return jsonify({'success': False, 'error': 'Movie not found'}), 404

@app.route('/api/movie/<movie_id>/reviews')
def api_movie_reviews(movie_id):
    """API: Get movie reviews"""
    reviews = get_movie_reviews(movie_id)
    return jsonify({'success': True, 'reviews': reviews})

@app.route('/api/user/reviews')
def api_user_reviews():
    """API: Get user's reviews"""
    if not session.get('user_email'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    email = session.get('user_email')
    reviews = get_user_reviews(email)
    return jsonify({'success': True, 'reviews': reviews})

@app.route('/api/recommendations')
def api_recommendations():
    """API: Get personalized recommendations"""
    if not session.get('user_email'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    email = session.get('user_email')
    recommendations = get_recommendations(email)
    return jsonify({'success': True, 'recommendations': recommendations})

@app.route('/api/analytics')
def api_analytics():
    """API: Get analytics data"""
    if not session.get('user_email'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    all_movies = get_all_movies()
    total_reviews = get_total_reviews_count()
    genre_dist = get_genre_distribution()
    
    return jsonify({
        'success': True,
        'data': {
            'total_movies': len(all_movies),
            'total_reviews': total_reviews,
            'genre_distribution': genre_dist
        }
    })

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def page_not_found(e):
    """404 error handler"""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(e):
    """500 error handler"""
    return render_template('500.html'), 500

# ============================================================================
# CONTEXT PROCESSORS
# ============================================================================

@app.context_processor
def inject_user():
    """Inject user session data into all templates"""
    return {
        'logged_in': 'user_email' in session,
        'user_email': session.get('user_email', ''),
        'user_name': session.get('user_name', ''),
    }

@app.context_processor
def inject_genres():
    """Inject available genres into all templates"""
    try:
        movies = get_all_movies()
        genres = sorted(set(m.get('genre', '') for m in movies if m.get('genre')))
        return {'available_genres': genres}
    except:
        return {'available_genres': []}

# ============================================================================
# UTILITY ROUTES
# ============================================================================

@app.route('/search')
def search():
    """Search movies"""
    query = request.args.get('q', '').strip().lower()
    
    if not query:
        flash('Please enter a search term', 'info')
        return redirect(url_for('movies'))
    
    all_movies = get_all_movies()
    results = [
        m for m in all_movies 
        if query in m.get('title', '').lower() 
        or query in m.get('description', '').lower()
        or query in m.get('director', '').lower()
    ]
    
    return render_template('search_results.html', query=query, movies=results)

@app.route('/about')
def about():
    """About page"""
    return render_template('about.html')

@app.route('/contact')
def contact():
    """Contact page"""
    return render_template('contact.html')

# ============================================================================
# ADMIN ROUTES (Optional)
# ============================================================================

@app.route('/admin/add-movie', methods=['GET', 'POST'])
def admin_add_movie():
    """Admin: Add new movie"""
    if not session.get('user_email'):
        flash('Please login to access admin features!', 'danger')
        return redirect(url_for('login'))
    
    # Simple admin check - you can enhance this
    if session.get('user_email') not in ['admin@cinemapulse.com']:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('movies'))
    
    if request.method == 'POST':
        try:
            movie_id = f"movie_{str(uuid.uuid4())[:8]}"
            
            movies_table.put_item(Item={
                'movie_id': movie_id,
                'title': request.form.get('title', '').strip(),
                'description': request.form.get('description', '').strip(),
                'genre': request.form.get('genre', '').strip(),
                'release_year': int(request.form.get('release_year', 2025)),
                'director': request.form.get('director', '').strip(),
                'image_url': request.form.get('image_url', '').strip(),
                'total_reviews': 0,
                'avg_rating': Decimal('0.0'),
                'active': True,
                'created_at': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat()
            })
            
            flash('Movie added successfully!', 'success')
            return redirect(url_for('movies'))
            
        except Exception as e:
            print(f"Error adding movie: {e}")
            flash('Error adding movie!', 'danger')
    
    return render_template('admin_add_movie.html')

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        # Test DynamoDB connection
        dynamodb.meta.client.list_tables()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# ============================================================================
# RUN APPLICATION
# ============================================================================

if __name__ == '__main__':
    
    # Run the Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=True
    )
