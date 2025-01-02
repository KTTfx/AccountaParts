from app import app, db, User, Badge, Category, Goal, Partnership
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

def init_db():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        
        # Create all tables
        db.create_all()
        
        print("Creating sample data...")
        
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
            }
        ]

        for badge_data in badges_data:
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
            }
        ]

        for category_data in categories_data:
            category = Category(**category_data)
            db.session.add(category)
        
        db.session.commit()
        
        # Create test users
        test_user1 = User(
            username='john_doe',
            email='john@example.com',
            password_hash=generate_password_hash('password123'),
            points=100,
            level=2
        )
        db.session.add(test_user1)
        
        test_user2 = User(
            username='jane_doe',
            email='jane@example.com',
            password_hash=generate_password_hash('password123'),
            points=150,
            level=3
        )
        db.session.add(test_user2)
        
        db.session.commit()
        
        # Create partnership
        partnership = Partnership(
            user_id=test_user1.id,
            partner_id=test_user2.id,
            status='accepted'
        )
        db.session.add(partnership)
        
        reverse_partnership = Partnership(
            user_id=test_user2.id,
            partner_id=test_user1.id,
            status='accepted'
        )
        db.session.add(reverse_partnership)
        
        # Create sample goals
        health_category = Category.query.filter_by(name='Health & Fitness').first()
        career_category = Category.query.filter_by(name='Career & Education').first()
        
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
            )
        ]
        
        for goal in goals:
            db.session.add(goal)
        
        db.session.commit()
        print("Database initialized successfully with sample data!")

init_db()
