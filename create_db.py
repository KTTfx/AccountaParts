from app import app, db, User, Goal, Category, Badge, UserBadge, CheckIn
from werkzeug.security import generate_password_hash
from datetime import datetime

def init_db():
    with app.app_context():
        # Drop all tables
        db.drop_all()
        
        # Create all tables
        db.create_all()
        
        # Create default categories
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
                'description': 'Social connections and relationships goals',
                'color': '#6610f2'
            },
            {
                'name': 'Finance',
                'description': 'Financial management and planning goals',
                'color': '#e83e8c'
            },
            {
                'name': 'Hobbies & Recreation',
                'description': 'Leisure activities and hobbies goals',
                'color': '#dc3545'
            }
        ]

        for category_data in categories_data:
            category = Category(**category_data)
            db.session.add(category)
        
        # Create badges
        badges_data = [
            {
                'name': 'Early Bird',
                'description': 'Complete 5 goals before noon',
                'icon': 'fa-sun',
                'requirement': 5
            },
            {
                'name': 'Streak Master',
                'description': 'Maintain a 7-day streak',
                'icon': 'fa-fire',
                'requirement': 7
            },
            {
                'name': 'Goal Crusher',
                'description': 'Complete 10 goals',
                'icon': 'fa-trophy',
                'requirement': 10
            },
            {
                'name': 'Team Player',
                'description': 'Partner with someone for 30 days',
                'icon': 'fa-users',
                'requirement': 30
            },
            {
                'name': 'Perfectionist',
                'description': 'Complete 5 difficult goals',
                'icon': 'fa-star',
                'requirement': 5
            },
            {
                'name': 'Motivator',
                'description': 'Leave 20 comments on goals',
                'icon': 'fa-comments',
                'requirement': 20
            },
            {
                'name': 'Early Achiever',
                'description': 'Complete 3 goals before deadline',
                'icon': 'fa-clock',
                'requirement': 3
            },
            {
                'name': 'Consistency King',
                'description': 'Complete daily goals for 5 days',
                'icon': 'fa-crown',
                'requirement': 5
            }
        ]

        for badge_data in badges_data:
            if not Badge.query.filter_by(name=badge_data['name']).first():
                badge = Badge(**badge_data)
                db.session.add(badge)
        
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
        
        # Set up partnership between test users
        test_user1.partner_id = test_user2.id
        test_user2.partner_id = test_user1.id
        db.session.commit()
        
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

if __name__ == '__main__':
    init_db()
