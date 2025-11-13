from flask import Blueprint, request, jsonify
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
import logging
from config import Config

# Logging configuration
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Create Blueprint
auth_bp = Blueprint('auth', __name__)

# -------------------------
# Database connection
# -------------------------
def get_db_connection():
    try:
        conn = pymysql.connect(
            host=Config.DB_HOST,
            user=Config.DB_USERNAME,
            password=Config.DB_PASSWORD,
            database=Config.DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except pymysql.Error as e:
        logger.error(f"Database connection failed: {e}")
        raise

# -------------------------
# Admin Signup
# -------------------------
@auth_bp.route('/admin/signup', methods=['POST'])
def admin_signup():
    try:
        data = request.get_json()
        logger.debug(f"Admin signup received data: {data}")
        
        username = data.get('username')
        email = data.get('email')
        phone_number = data.get('phone_number')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        # Validate all required fields
        if not all([username, email, phone_number, password, confirm_password]):
            missing_fields = []
            if not username: missing_fields.append('username')
            if not email: missing_fields.append('email')
            if not phone_number: missing_fields.append('phone_number')
            if not password: missing_fields.append('password')
            if not confirm_password: missing_fields.append('confirm_password')
            logger.error(f"Missing fields: {missing_fields}")
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        if password != confirm_password:
            return jsonify({'error': 'Passwords do not match'}), 400

        # Basic validation
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400

        if '@' not in email:
            return jsonify({'error': 'Invalid email format'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        password_hash = generate_password_hash(password)

        try:
            # role_id 1 = admin
            cursor.execute("""
                INSERT INTO users (username, email, phone_number, password_hash, role_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, email, phone_number, password_hash, 1))
            conn.commit()
            logger.info(f"Admin user created: {username}")
            return jsonify({'message': 'Admin registered successfully!'}), 201
        except pymysql.err.IntegrityError as e:
            error_msg = str(e)
            logger.error(f"Integrity error: {error_msg}")
            if 'Duplicate entry' in error_msg and ('email' in error_msg or 'users.email' in error_msg):
                return jsonify({'error': 'Email already exists'}), 400
            elif 'Duplicate entry' in error_msg and ('phone_number' in error_msg or 'users.phone_number' in error_msg):
                return jsonify({'error': 'Phone number already exists'}), 400
            elif 'Duplicate entry' in error_msg and ('username' in error_msg or 'users.username' in error_msg):
                return jsonify({'error': 'Username already exists'}), 400
            return jsonify({'error': 'User already exists'}), 400
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            return jsonify({'error': 'Database error occurred'}), 500
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Admin signup error: {e}")
        return jsonify({'error': 'Server error during signup'}), 500

# -------------------------
# Customer Signup (Updated)
# -------------------------
@auth_bp.route('/customer/signup', methods=['POST'])
def customer_signup():
    try:
        data = request.get_json()
        logger.debug(f"Customer signup received data: {data}")
        
        username = data.get('username')
        email = data.get('email')
        phone_number = data.get('phone_number')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        # Validate all required fields
        if not all([username, email, phone_number, password, confirm_password]):
            missing_fields = []
            if not username: missing_fields.append('username')
            if not email: missing_fields.append('email')
            if not phone_number: missing_fields.append('phone_number')
            if not password: missing_fields.append('password')
            if not confirm_password: missing_fields.append('confirm_password')
            logger.error(f"Missing fields: {missing_fields}")
            return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        
        if password != confirm_password:
            return jsonify({'error': 'Passwords do not match'}), 400

        # Basic validation
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400

        if '@' not in email:
            return jsonify({'error': 'Invalid email format'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        password_hash = generate_password_hash(password)

        try:
            # role_id 2 = customer
            cursor.execute("""
                INSERT INTO users (username, email, phone_number, password_hash, role_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, email, phone_number, password_hash, 2))
            conn.commit()
            logger.info(f"Customer user created: {username}")
            return jsonify({'message': 'Customer registered successfully!'}), 201
        except pymysql.err.IntegrityError as e:
            error_msg = str(e)
            logger.error(f"Integrity error: {error_msg}")
            if 'Duplicate entry' in error_msg and ('email' in error_msg or 'users.email' in error_msg):
                return jsonify({'error': 'Email already exists'}), 400
            elif 'Duplicate entry' in error_msg and ('phone_number' in error_msg or 'users.phone_number' in error_msg):
                return jsonify({'error': 'Phone number already exists'}), 400
            elif 'Duplicate entry' in error_msg and ('username' in error_msg or 'users.username' in error_msg):
                return jsonify({'error': 'Username already exists'}), 400
            return jsonify({'error': 'User already exists'}), 400
        except Exception as db_error:
            logger.error(f"Database error: {db_error}")
            return jsonify({'error': 'Database error occurred'}), 500
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Customer signup error: {e}")
        return jsonify({'error': 'Server error during signup'}), 500

# -------------------------
# Admin Login
# -------------------------
@auth_bp.route('/admin/login', methods=['POST'])
def admin_login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s AND role_id = 1", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid username or password'}), 401

        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'role_id': user['role_id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }, Config.SECRET_KEY, algorithm='HS256')

        return jsonify({'message': 'Admin login successful', 'token': token}), 200
    except Exception as e:
        logger.error(f"Admin login error: {e}")
        return jsonify({'error': 'Server error'}), 500

# -------------------------
# Customer Login
# -------------------------
@auth_bp.route('/customer/login', methods=['POST'])
def customer_login():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = %s AND role_id = 2", (username,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid username or password'}), 401

        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'role_id': user['role_id'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        }, Config.SECRET_KEY, algorithm='HS256')

        return jsonify({'message': 'Customer login successful', 'token': token}), 200
    except Exception as e:
        logger.error(f"Customer login error: {e}")
        return jsonify({'error': 'Server error'}), 500


# -------------------------
# Role-protected Dashboard
# -------------------------
@auth_bp.route('/dashboard', methods=['GET'])
def dashboard():
    token = request.headers.get('Authorization')
    if not token:
        return jsonify({'error': 'Token missing'}), 401

    try:
        decoded = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        role_id = decoded['role_id']
        username = decoded['username']  # Fixed: was trying to access 'email' which isn't in token
        if role_id == 1:
            return jsonify({'message': f'Welcome Admin {username}!'}), 200
        elif role_id == 2:
            return jsonify({'message': f'Welcome Customer {username}!'}), 200
        else:
            return jsonify({'error': 'Unknown role'}), 403
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401


# -------------------------
# Get User Details (Protected)
# -------------------------
@auth_bp.route('/user/details', methods=['GET'])
def user_details():
    token = request.headers.get('Authorization')
    
    if not token:
        return jsonify({'error': 'Valid Authorization header required'}), 401

    try:
        # Decode the JWT token
        decoded = jwt.decode(token, Config.SECRET_KEY, algorithms=['HS256'])
        user_id = decoded.get('user_id')

        # Fetch user details from database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT username, email, phone_number, role_id FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Role name for readability
        role_name = 'Admin' if user['role_id'] == 1 else 'Customer' if user['role_id'] == 2 else 'Unknown'

        return jsonify({
            'username': user['username'],
            'email': user['email'],
            'phone_number': user['phone_number'],
            'role': role_name
        }), 200

    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token expired'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Invalid token'}), 401
    except Exception as e:
        logger.error(f"Error fetching user details: {e}")
        return jsonify({'error': 'Server error while fetching user details'}), 500
