from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from sqlalchemy import func

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///accountaparts.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    badges = db.relationship('UserBadge', backref='user', lazy=True)
    partner_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=True)
    
    # Relationships
    goals = db.relationship('Goal', backref='user', lazy=True)
    check_ins = db.relationship('CheckIn', backref='user', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    
    def get_partner(self):
        if self.partner_id:
            return User.query.get(self.partner_id)
        return None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

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
    goal_type = db.Column(db.String(50))  # daily, weekly, monthly
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    difficulty = db.Column(db.Integer, default=1)  # 1-5
    verification_required = db.Column(db.Boolean, default=False)
    points_reward = db.Column(db.Integer, default=10)
    streak = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_streak_update = db.Column(db.DateTime, nullable=True)
    tags = db.relationship('Tag', secondary=goal_tags, lazy='subquery',
        backref=db.backref('goals', lazy=True))
    comments = db.relationship('Comment', backref=db.backref('target_goal', lazy=True), lazy=True)

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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    mood = db.Column(db.String(10), nullable=False)
    message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    goal_id = db.Column(db.Integer, db.ForeignKey('goal.id'), nullable=False)

# Helper functions
def calculate_points(goal):
    """Calculate points for completing a goal based on difficulty and streak"""
    base_points = goal.points_reward or 10  # Use goal's points_reward or default to 10
    difficulty_multiplier = goal.difficulty or 1  # Use goal's difficulty or default to 1
    streak_bonus = min(goal.streak * 0.1, 1.0)  # 10% bonus per streak, max 100% bonus
    
    total_points = int(base_points * (1 + difficulty_multiplier * streak_bonus))
    return max(total_points, 1)  # Ensure at least 1 point is awarded

def update_streak(goal):
    """Update the goal's streak based on completion time"""
    if not goal.last_streak_update:
        goal.streak = 1
    else:
        days_diff = (datetime.utcnow().date() - goal.last_streak_update.date()).days
        if days_diff == 1:  # Consecutive day
            goal.streak += 1
        elif days_diff > 1:  # Streak broken
            goal.streak = 1
    
    goal.last_streak_update = datetime.utcnow()

def check_and_award_badges(user):
    """Check and award badges based on user achievements"""
    # Check Week Warrior badge (7-day streak)
    week_warrior = Badge.query.filter_by(name='Week Warrior').first()
    if week_warrior and not UserBadge.query.filter_by(user_id=user.id, badge_id=week_warrior.id).first():
        goals_with_week_streak = Goal.query.filter_by(user_id=user.id, streak__gte=7).count()
        if goals_with_week_streak >= 1:
            user_badge = UserBadge(user_id=user.id, badge_id=week_warrior.id)
            db.session.add(user_badge)
            user.points += week_warrior.points
            flash(f'Congratulations! You earned the {week_warrior.name} badge and {week_warrior.points} points!', 'success')

    # Check Monthly Master badge (30-day streak)
    monthly_master = Badge.query.filter_by(name='Monthly Master').first()
    if monthly_master and not UserBadge.query.filter_by(user_id=user.id, badge_id=monthly_master.id).first():
        goals_with_month_streak = Goal.query.filter_by(user_id=user.id, streak__gte=30).count()
        if goals_with_month_streak >= 1:
            user_badge = UserBadge(user_id=user.id, badge_id=monthly_master.id)
            db.session.add(user_badge)
            user.points += monthly_master.points
            flash(f'Congratulations! You earned the {monthly_master.name} badge and {monthly_master.points} points!', 'success')

    # Check Perfect Partner badge (7-day partnership streak)
    perfect_partner = Badge.query.filter_by(name='Perfect Partner').first()
    if perfect_partner and not UserBadge.query.filter_by(user_id=user.id, badge_id=perfect_partner.id).first():
        partnerships_with_streak = Partnership.query.filter(
            ((Partnership.user_id == user.id) | (Partnership.partner_id == user.id)) &
            (Partnership.check_in_streak >= 7)
        ).count()
        if partnerships_with_streak >= 1:
            user_badge = UserBadge(user_id=user.id, badge_id=perfect_partner.id)
            db.session.add(user_badge)
            user.points += perfect_partner.points
            flash(f'Congratulations! You earned the {perfect_partner.name} badge and {perfect_partner.points} points!', 'success')

    # Check Goal Getter badge (complete 10 goals)
    goal_getter = Badge.query.filter_by(name='Goal Getter').first()
    if goal_getter and not UserBadge.query.filter_by(user_id=user.id, badge_id=goal_getter.id).first():
        completed_goals = Goal.query.filter_by(user_id=user.id, completed=True).count()
        if completed_goals >= 10:
            user_badge = UserBadge(user_id=user.id, badge_id=goal_getter.id)
            db.session.add(user_badge)
            user.points += goal_getter.points
            flash(f'Congratulations! You earned the {goal_getter.name} badge and {goal_getter.points} points!', 'success')

def get_my_latest_checkin():
    """Get the current user's latest check-in for today"""
    today = datetime.utcnow().date()
    return CheckIn.query.filter(
        CheckIn.user_id == current_user.id,
        func.date(CheckIn.created_at) == today
    ).first()

def get_partner_latest_checkin():
    """Get the partner's latest check-in for today"""
    if not current_user.partner_id:
        return None
        
    today = datetime.utcnow().date()
    return CheckIn.query.filter(
        CheckIn.user_id == current_user.partner_id,
        func.date(CheckIn.created_at) == today
    ).first()

@app.context_processor
def utility_processor():
    """Make check-in helper functions available in templates"""
    return {
        'get_my_latest_checkin': get_my_latest_checkin,
        'get_partner_latest_checkin': get_partner_latest_checkin,
        'today': datetime.utcnow().date()
    }

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
        user.set_password(password)
        
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
    partner = current_user.get_partner()
    
    return render_template('dashboard.html', 
                         categories=categories, 
                         goals=goals, 
                         partner=partner)

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
    category_id = request.form.get('category_id')
    goal_type = request.form.get('goal_type')
    difficulty = request.form.get('difficulty')
    deadline_str = request.form.get('deadline')
    
    if not all([title, description, category_id, goal_type, difficulty, deadline_str]):
        flash('Please fill in all required fields', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        deadline = datetime.strptime(deadline_str, '%Y-%m-%dT%H:%M')
        difficulty = int(difficulty)
        category_id = int(category_id)
        
        goal = Goal(
            title=title,
            description=description,
            category_id=category_id,
            goal_type=goal_type,
            difficulty=difficulty,
            deadline=deadline,
            user_id=current_user.id
        )
        
        db.session.add(goal)
        db.session.commit()
        
        flash('Goal added successfully!', 'success')
    except ValueError as e:
        flash('Invalid form data. Please check your inputs.', 'danger')
    except Exception as e:
        flash('An error occurred while adding the goal.', 'danger')
        
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

@app.route('/add_partner', methods=['POST'])
@login_required
def add_partner():
    partner_username = request.form.get('partner_username')
    
    if not partner_username:
        flash('Please enter a username', 'danger')
        return redirect(url_for('dashboard'))
        
    if partner_username == current_user.username:
        flash('You cannot add yourself as a partner', 'danger')
        return redirect(url_for('dashboard'))
    
    partner = User.query.filter_by(username=partner_username).first()
    
    if not partner:
        flash('User not found', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if either user already has a partner
    if current_user.partner_id:
        flash('You already have a partner', 'danger')
        return redirect(url_for('dashboard'))
        
    if partner.partner_id:
        flash('This user already has a partner', 'danger')
        return redirect(url_for('dashboard'))
    
    # Set up partnership
    current_user.partner_id = partner.id
    partner.partner_id = current_user.id
    
    db.session.commit()
    flash(f'Successfully partnered with {partner.username}!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/remove_partner', methods=['POST'])
@login_required
def remove_partner():
    if not current_user.partner_id:
        flash('You don\'t have a partner to remove', 'danger')
        return redirect(url_for('dashboard'))
    
    partner = User.query.get(current_user.partner_id)
    if partner:
        partner.partner_id = None
    current_user.partner_id = None
    
    db.session.commit()
    flash('Partnership removed successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/check_in', methods=['POST'])
@login_required
def check_in():
    partner = current_user.get_partner()
    if not partner:
        flash('You don\'t have a partner to check in with', 'danger')
        return redirect(url_for('dashboard'))
    
    # Check if already checked in today
    today = datetime.utcnow().date()
    existing_checkin = CheckIn.query.filter(
        CheckIn.user_id == current_user.id,
        func.date(CheckIn.created_at) == today
    ).first()
    
    if existing_checkin:
        flash('You have already checked in today', 'info')
        return redirect(url_for('dashboard'))
    
    mood = request.form.get('mood', type=int)
    message = request.form.get('message', '')
    
    if not mood or mood not in range(1, 6):
        flash('Please select a valid mood', 'error')
        return redirect(url_for('dashboard'))
    
    # Create check-in
    checkin = CheckIn(
        user_id=current_user.id,
        mood=mood,
        message=message
    )
    db.session.add(checkin)

    # Update partnership streak and award points
    partner_checkin = CheckIn.query.filter_by(
        user_id=partner.id,
        created_at=datetime.utcnow().date()
    ).first()
    if partner_checkin:
        current_user.points += 10
        flash('You earned 10 points for checking in with your partner!', 'success')

    # Check for badge achievements
    check_and_award_badges(current_user)

    db.session.commit()
    flash('Check-in recorded!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/complete_goal/<int:goal_id>', methods=['POST'])
@login_required
def complete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash('Unauthorized', 'error')
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    if not goal.completed:
        # Calculate points based on difficulty and streak
        points = calculate_points(goal)
        current_user.points += points
        
        # Update the goal
        goal.completed = True
        goal.completed_at = datetime.utcnow()
        
        # Update streak and check for badges
        update_streak(goal)
        check_and_award_badges(current_user)
        
        db.session.commit()
        flash(f'Goal completed! You earned {points} points!', 'success')
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Goal is already completed'})

@app.route('/goals/<int:goal_id>/comments', methods=['POST'])
@login_required
def add_comment(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    content = request.form.get('content')
    
    if not content:
        flash('Comment cannot be empty', 'danger')
        return redirect(url_for('dashboard'))
    
    comment = Comment(
        content=content,
        user_id=current_user.id,
        goal_id=goal_id
    )
    db.session.add(comment)
    db.session.commit()
    
    flash('Comment added successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/comments/<int:comment_id>', methods=['DELETE'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    
    if comment.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(comment)
    db.session.commit()
    
    return jsonify({'message': 'Comment deleted successfully'})

@app.route('/delete_goal/<int:goal_id>', methods=['POST'])
@login_required
def delete_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    if goal.user_id != current_user.id:
        flash('Unauthorized', 'error')
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    db.session.delete(goal)
    db.session.commit()
    flash('Goal deleted successfully', 'success')
    return jsonify({'success': True})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/how-it-works')
def how_it_works():
    return render_template('how_it_works.html')

@app.route('/accountability_partner')
@login_required
def accountability_partner():
    partner = current_user.get_partner()
    if not partner:
        flash('You need to add an accountability partner first!', 'warning')
        return redirect(url_for('dashboard'))
        
    partner_goals = Goal.query.filter_by(user_id=partner.id).order_by(Goal.created_at.desc()).all()
    partner_stats = {
        'total_goals': len(partner_goals),
        'completed_goals': len([g for g in partner_goals if g.completed]),
        'current_streak': partner.current_streak if hasattr(partner, 'current_streak') else 0,
        'points': partner.points
    }
    
    # Get partner's latest check-in
    latest_checkin = CheckIn.query.filter_by(user_id=partner.id).order_by(CheckIn.created_at.desc()).first()
    
    return render_template('accountability_partner.html', 
                         partner=partner,
                         partner_goals=partner_goals,
                         partner_stats=partner_stats,
                         latest_checkin=latest_checkin)

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
        },
        {
            'name': 'Perfect Partner',
            'description': 'Maintain a 7-day partnership streak',
            'icon': 'fa-users',
            'requirement': 'Maintain a 7-day partnership streak',
            'points': 100
        },
        {
            'name': 'Goal Getter',
            'description': 'Complete 10 goals',
            'icon': 'fa-check',
            'requirement': 'Complete 10 goals',
            'points': 500
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
    test_user1 = User.query.filter_by(username='test_user1').first()
    test_user2 = User.query.filter_by(username='test_user2').first()
    
    if not test_user1:
        test_user1 = User(username='test_user1', email='test1@example.com')
        test_user1.set_password('password123')
        db.session.add(test_user1)
    
    if not test_user2:
        test_user2 = User(username='test_user2', email='test2@example.com')
        test_user2.set_password('password123')
        db.session.add(test_user2)
    
    db.session.commit()
    
    # Set up partnership if it doesn't exist
    if not test_user1.partner_id and not test_user2.partner_id:
        test_user1.partner_id = test_user2.id
        test_user2.partner_id = test_user1.id
        db.session.commit()
        
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
    app.run(host='0.0.0.0', port=5000, debug=True)
