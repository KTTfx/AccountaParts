from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///accountaparts.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    points = db.Column(db.Integer, default=0)
    level = db.Column(db.Integer, default=1)
    goals = db.relationship('Goal', backref='user', lazy=True)
    partnerships = db.relationship('Partnership', 
                                 foreign_keys='Partnership.user_id',
                                 backref='user', 
                                 lazy=True)
    partner_in = db.relationship('Partnership',
                               foreign_keys='Partnership.partner_id',
                               backref='partner',
                               lazy=True)
    badges = db.relationship('UserBadge', backref='user', lazy=True)

    def get_partnerships(self):
        return Partnership.query.filter(
            (Partnership.user_id == self.id) | 
            (Partnership.partner_id == self.id)
        ).all()

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    icon = db.Column(db.String(50))  # Font Awesome icon class
    requirement = db.Column(db.String(200))
    points = db.Column(db.Integer, default=0)
    users = db.relationship('UserBadge', backref='badge', lazy=True)

class UserBadge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    badge_id = db.Column(db.Integer, db.ForeignKey('badge.id'), nullable=False)
    earned_date = db.Column(db.DateTime, default=datetime.utcnow)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    color = db.Column(db.String(7), default='#007bff')  # Hex color code
    goals = db.relationship('Goal', backref='category', lazy=True)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

goal_tags = db.Table('goal_tags',
    db.Column('goal_id', db.Integer, db.ForeignKey('goal.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class Goal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime)
    completed = db.Column(db.Boolean, default=False)
    goal_type = db.Column(db.String(20))  # daily, weekly, monthly, yearly
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    streak = db.Column(db.Integer, default=0)
    last_streak_update = db.Column(db.DateTime)
    difficulty = db.Column(db.Integer, default=1)  # 1-5 scale
    verification_required = db.Column(db.Boolean, default=False)
    verification_image = db.Column(db.String(200))
    points_reward = db.Column(db.Integer, default=10)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tags = db.relationship('Tag', secondary=goal_tags, lazy='subquery',
        backref=db.backref('goals', lazy=True))

class Partnership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    partner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    check_in_streak = db.Column(db.Integer, default=0)
    last_check_in = db.Column(db.DateTime)

class CheckIn(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    partnership_id = db.Column(db.Integer, db.ForeignKey('partnership.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    mood = db.Column(db.Integer)  # 1-5 scale
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    goal_id = db.Column(db.Integer, db.ForeignKey('goal.id'), nullable=False)
    is_verification = db.Column(db.Boolean, default=False)
    is_encouragement = db.Column(db.Boolean, default=False)

# Helper functions
def calculate_points(goal):
    base_points = 10
    difficulty_multiplier = goal.difficulty
    streak_multiplier = max(1, min(2, goal.streak / 10))  # Cap at 2x multiplier
    return int(base_points * difficulty_multiplier * streak_multiplier)

def update_streak(goal):
    today = datetime.utcnow().date()
    if goal.last_streak_update:
        days_diff = (today - goal.last_streak_update.date()).days
        if days_diff == 1:  # Consecutive day
            goal.streak += 1
        elif days_diff > 1:  # Streak broken
            goal.streak = 1
    else:
        goal.streak = 1
    goal.last_streak_update = datetime.utcnow()

def check_and_award_badges(user):
    # Check for streak badges
    streak_badges = {
        7: "Week Warrior",
        30: "Monthly Master",
        100: "Century Champion"
    }
    
    max_streak = db.session.query(db.func.max(Goal.streak)).filter_by(user_id=user.id).scalar() or 0
    
    for streak, badge_name in streak_badges.items():
        if max_streak >= streak:
            badge = Badge.query.filter_by(name=badge_name).first()
            if badge and not UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
                user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
                db.session.add(user_badge)
                flash(f'Congratulations! You earned the {badge_name} badge!')

    # Check for category badges
    categories_completed = db.session.query(Goal.category_id).filter_by(
        user_id=user.id, completed=True
    ).distinct().count()
    
    if categories_completed >= 5:
        badge = Badge.query.filter_by(name="Versatility Victor").first()
        if badge and not UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
            user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(user_badge)
            flash(f'Congratulations! You earned the Versatility Victor badge!')

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('register'))
            
        user = User(username=username, email=email)
        user.password_hash = generate_password_hash(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful! Please login.')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('dashboard'))
            
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    categories = Category.query.all()
    goals = Goal.query.filter_by(user_id=current_user.id).order_by(Goal.created_at.desc()).all()
    
    # Get all accepted partnerships where the current user is either the user or partner
    partnerships = Partnership.query.filter(
        db.or_(
            db.and_(Partnership.user_id == current_user.id, Partnership.status == 'accepted'),
            db.and_(Partnership.partner_id == current_user.id, Partnership.status == 'accepted')
        )
    ).all()
    
    partner_goals = []
    for partnership in partnerships:
        partner_id = partnership.partner_id if partnership.user_id == current_user.id else partnership.user_id
        partner_goals.extend(Goal.query.filter_by(user_id=partner_id).all())
    
    return render_template('dashboard.html', categories=categories, goals=goals, partner_goals=partner_goals)

@app.route('/categories')
@login_required
def categories():
    categories = Category.query.all()
    return render_template('categories.html', categories=categories)

@app.route('/add_category', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name')
    description = request.form.get('description')
    color = request.form.get('color', '#007bff')
    
    if name:
        category = Category(name=name, description=description, color=color)
        db.session.add(category)
        db.session.commit()
        flash('Category added successfully!', 'success')
    return redirect(url_for('categories'))

@app.route('/add_goal', methods=['POST'])
@login_required
def add_goal():
    title = request.form.get('title')
    description = request.form.get('description')
    deadline = datetime.strptime(request.form.get('deadline'), '%Y-%m-%dT%H:%M')
    goal_type = request.form.get('goal_type')
    category_id = request.form.get('category_id')
    difficulty = int(request.form.get('difficulty', 1))
    verification_required = 'verification_required' in request.form
    tags = request.form.get('tags', '').split(',')
    
    goal = Goal(
        title=title,
        description=description,
        deadline=deadline,
        goal_type=goal_type,
        user_id=current_user.id,
        category_id=category_id,
        difficulty=difficulty,
        verification_required=verification_required,
        points_reward=10 * difficulty  # Base points * difficulty
    )
    
    # Handle tags
    for tag_name in tags:
        tag_name = tag_name.strip()
        if tag_name:
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
            goal.tags.append(tag)
    
    db.session.add(goal)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/toggle_goal/<int:goal_id>')
@login_required
def toggle_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id == current_user.id:
        goal.completed = not goal.completed
        if goal.completed:
            update_streak(goal)
            points = calculate_points(goal)
            current_user.points += points
            current_user.level = (current_user.points // 100) + 1
            check_and_award_badges(current_user)
            flash(f'Congratulations! You earned {points} points!')
        db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/encourage/<int:goal_id>', methods=['POST'])
@login_required
def encourage(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    content = request.form.get('content', 'You can do it! ')
    
    comment = Comment(
        content=content,
        user_id=current_user.id,
        goal_id=goal_id,
        is_encouragement=True
    )
    
    db.session.add(comment)
    db.session.commit()
    
    flash('Encouragement sent!')
    return redirect(url_for('dashboard'))

@app.route('/goal/<int:goal_id>/verify', methods=['POST'])
@login_required
def verify_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('dashboard'))
    
    if 'verification_image' not in request.files:
        flash('No file uploaded!', 'danger')
        return redirect(url_for('dashboard'))
        
    file = request.files['verification_image']
    if file.filename == '':
        flash('No file selected!', 'danger')
        return redirect(url_for('dashboard'))
        
    if file:
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        goal.verification_image = filename
        db.session.commit()
        flash('Verification image uploaded successfully!', 'success')
    
    return redirect(url_for('dashboard'))

@app.route('/check_in/<int:partnership_id>', methods=['POST'])
@login_required
def check_in(partnership_id):
    partnership = Partnership.query.get_or_404(partnership_id)
    if partnership.user_id != current_user.id and partnership.partner_id != current_user.id:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('dashboard'))
    
    mood = request.form.get('mood', type=int)
    message = request.form.get('message', '')
    
    check_in = CheckIn(
        partnership_id=partnership_id,
        user_id=current_user.id,
        mood=mood,
        message=message
    )
    db.session.add(check_in)
    
    # Update partnership check-in streak
    if partnership.last_check_in:
        last_check_in_date = partnership.last_check_in.date()
        today = datetime.utcnow().date()
        if (today - last_check_in_date).days == 1:
            partnership.check_in_streak += 1
        elif (today - last_check_in_date).days > 1:
            partnership.check_in_streak = 1
    else:
        partnership.check_in_streak = 1
    
    partnership.last_check_in = datetime.utcnow()
    db.session.commit()
    
    flash('Check-in recorded successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/goal/<int:goal_id>/complete', methods=['POST'])
@login_required
def complete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash('Unauthorized access!', 'danger')
        return redirect(url_for('dashboard'))
    
    goal.completed = True
    
    # Update streak
    if goal.last_streak_update:
        last_update = goal.last_streak_update.date()
        today = datetime.utcnow().date()
        if (today - last_update).days == 1:
            goal.streak += 1
        elif (today - last_update).days > 1:
            goal.streak = 1
    else:
        goal.streak = 1
    
    goal.last_streak_update = datetime.utcnow()
    
    # Award points based on difficulty and streak
    points = calculate_points(goal)
    current_user.points += points
    
    # Update user level (every 100 points = 1 level)
    current_user.level = (current_user.points // 100) + 1
    
    # Check for badge achievements
    check_badges(current_user, goal)
    
    db.session.commit()
    flash(f'Goal completed! You earned {points} points!', 'success')
    return redirect(url_for('dashboard'))

def calculate_points(goal):
    base_points = goal.points_reward
    streak_bonus = min(goal.streak * 0.1, 1.0)  # Max 100% bonus for streaks
    difficulty_bonus = (goal.difficulty - 1) * 0.2  # 20% bonus per difficulty level above 1
    return int(base_points * (1 + streak_bonus + difficulty_bonus))

def check_badges(user, goal):
    # Check Week Warrior badge
    if goal.streak >= 7:
        badge = Badge.query.filter_by(name='Week Warrior').first()
        if badge and not UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
            user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(user_badge)
            user.points += badge.points
            flash(f'Congratulations! You earned the {badge.name} badge and {badge.points} points!', 'success')
    
    # Check Monthly Master badge
    if goal.streak >= 30:
        badge = Badge.query.filter_by(name='Monthly Master').first()
        if badge and not UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
            user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(user_badge)
            user.points += badge.points
            flash(f'Congratulations! You earned the {badge.name} badge and {badge.points} points!', 'success')
    
    # Check Century Champion badge
    if goal.streak >= 100:
        badge = Badge.query.filter_by(name='Century Champion').first()
        if badge and not UserBadge.query.filter_by(user_id=user.id, badge_id=badge.id).first():
            user_badge = UserBadge(user_id=user.id, badge_id=badge.id)
            db.session.add(user_badge)
            user.points += badge.points
            flash(f'Congratulations! You earned the {badge.name} badge and {badge.points} points!', 'success')

@app.route('/add_comment/<int:goal_id>', methods=['POST'])
@login_required
def add_comment(goal_id):
    content = request.form.get('content')
    comment = Comment(
        content=content,
        user_id=current_user.id,
        goal_id=goal_id
    )
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/add_partner', methods=['POST'])
@login_required
def add_partner():
    partner_username = request.form.get('partner_username')
    partner = User.query.filter_by(username=partner_username).first()
    
    if not partner:
        flash('User not found')
        return redirect(url_for('dashboard'))
        
    if partner.id == current_user.id:
        flash('You cannot partner with yourself')
        return redirect(url_for('dashboard'))
        
    existing_partnership = Partnership.query.filter_by(
        user_id=current_user.id,
        partner_id=partner.id
    ).first()
    
    if existing_partnership:
        flash('Partnership already exists')
        return redirect(url_for('dashboard'))
        
    partnership = Partnership(user_id=current_user.id, partner_id=partner.id)
    db.session.add(partnership)
    db.session.commit()
    
    flash(f'Partnership request sent to {partner_username}')
    return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Create test users and sample data
def create_sample_data():
    # Create badges
    badges_data = [
        {
            'name': 'Week Warrior',
            'description': 'Maintain a 7-day streak',
            'icon': 'fa-fire',
            'requirement': 'Maintain a 7-day streak on any goal',
            'points': 50
        },
        {
            'name': 'Monthly Master',
            'description': 'Maintain a 30-day streak',
            'icon': 'fa-crown',
            'requirement': 'Maintain a 30-day streak on any goal',
            'points': 200
        },
        {
            'name': 'Century Champion',
            'description': 'Maintain a 100-day streak',
            'icon': 'fa-trophy',
            'requirement': 'Maintain a 100-day streak on any goal',
            'points': 1000
        },
        {
            'name': 'Versatility Victor',
            'description': 'Complete goals in 5 different categories',
            'icon': 'fa-star',
            'requirement': 'Complete at least one goal in 5 different categories',
            'points': 300
        }
    ]

    for badge_data in badges_data:
        if not Badge.query.filter_by(name=badge_data['name']).first():
            badge = Badge(**badge_data)
            db.session.add(badge)
    
    # Create categories
    categories_data = [
        {
            'name': 'Health & Fitness',
            'description': 'Exercise, nutrition, and wellness goals',
            'color': '#28a745'
        },
        {
            'name': 'Career & Education',
            'description': 'Professional development and learning goals',
            'color': '#007bff'
        },
        {
            'name': 'Personal Growth',
            'description': 'Self-improvement and lifestyle goals',
            'color': '#6f42c1'
        },
        {
            'name': 'Relationships',
            'description': 'Family, friends, and social goals',
            'color': '#e83e8c'
        },
        {
            'name': 'Finance',
            'description': 'Money management and financial goals',
            'color': '#fd7e14'
        }
    ]

    for category_data in categories_data:
        if not Category.query.filter_by(name=category_data['name']).first():
            category = Category(**category_data)
            db.session.add(category)

    # Create test users if they don't exist
    test_user1 = User.query.filter_by(username='john_doe').first()
    test_user2 = User.query.filter_by(username='jane_doe').first()
    
    if not test_user1:
        test_user1 = User(
            username='john_doe',
            email='john@example.com',
            password_hash=generate_password_hash('password123')
        )
        db.session.add(test_user1)
    
    if not test_user2:
        test_user2 = User(
            username='jane_doe',
            email='jane@example.com',
            password_hash=generate_password_hash('password123')
        )
        db.session.add(test_user2)
    
    db.session.commit()
    
    # Create partnership if it doesn't exist
    partnership = Partnership.query.filter_by(
        user_id=test_user1.id,
        partner_id=test_user2.id
    ).first()
    
    if not partnership:
        partnership = Partnership(
            user_id=test_user1.id,
            partner_id=test_user2.id,
            status='accepted'
        )
        db.session.add(partnership)
        
        # Create reverse partnership
        reverse_partnership = Partnership(
            user_id=test_user2.id,
            partner_id=test_user1.id,
            status='accepted'
        )
        db.session.add(reverse_partnership)
    
    # Add sample goals if they don't exist
    if not Goal.query.first():
        health_category = Category.query.filter_by(name='Health & Fitness').first()
        career_category = Category.query.filter_by(name='Career & Education').first()
        personal_category = Category.query.filter_by(name='Personal Growth').first()

        goals = [
            Goal(
                title='Complete Python Project',
                description='Finish the web application project using Flask',
                deadline=datetime(2025, 1, 3, 23, 59, 59),
                goal_type='daily',
                user_id=test_user1.id,
                category_id=career_category.id,
                difficulty=3,
                verification_required=True,
                points_reward=30
            ),
            Goal(
                title='Exercise Routine',
                description='Go to gym 3 times this week',
                deadline=datetime(2025, 1, 7, 23, 59, 59),
                goal_type='weekly',
                user_id=test_user1.id,
                category_id=health_category.id,
                difficulty=2,
                verification_required=True,
                points_reward=20
            ),
            Goal(
                title='Learn French',
                description='Complete basic French course',
                deadline=datetime(2025, 12, 31, 23, 59, 59),
                goal_type='yearly',
                user_id=test_user2.id,
                category_id=personal_category.id,
                difficulty=4,
                verification_required=False,
                points_reward=100
            )
        ]
        
        for goal in goals:
            db.session.add(goal)
    
    db.session.commit()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_sample_data()
    app.run(debug=True)
