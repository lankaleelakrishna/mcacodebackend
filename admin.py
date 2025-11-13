from flask import Flask, jsonify, request, abort
import pymysql
import base64
import re
import logging
import os

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# MySQL database credentials
DB_HOST = 'localhost'
DB_PORT = 3306
DB_USERNAME = 'root'
DB_PASSWORD = os.getenv('DB_PASSWORD', 'Dp@333666')
DB_NAME = 'perfume'

# Authorization token
AUTH_TOKEN = os.getenv('AUTH_TOKEN', 'mysecrettoken')

# Maximum image size (10MB in bytes)
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB

# Supported image MIME types
SUPPORTED_IMAGE_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/gif': 'gif',
    'image/bmp': 'bmp',
    'image/webp': 'webp'
}

# Function to create a database connection
def get_db_connection():
    logger.debug("Attempting to connect to database")
    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USERNAME,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        logger.debug("Database connection successful")
        return conn
    except pymysql.MySQLError as e:
        logger.error(f"Database connection failed: {e}")
        raise

# Middleware to check authorization token
def check_auth_token():
    auth_header = request.headers.get('Authorization')
    logger.debug(f"Authorization header: {auth_header}")
    if not auth_header or auth_header != AUTH_TOKEN:
        logger.warning(f"Unauthorized access attempt: {auth_header}")
        abort(401, description="Unauthorized: Invalid or missing authorization token")

# Validate image data (base64 or file upload)
def validate_image(data, is_file=False):
    if not data:
        return None, None
    try:
        logger.debug("Validating image data")
        if is_file:
            # Handle file upload
            if data.mimetype not in SUPPORTED_IMAGE_TYPES:
                logger.warning(f"Unsupported image type: {data.mimetype}")
                return None, f'Unsupported image type. Supported types: {", ".join(SUPPORTED_IMAGE_TYPES.keys())}'
            photo_bytes = data.read()
            if len(photo_bytes) > MAX_IMAGE_SIZE:
                logger.warning(f"Image size exceeds 10MB: {len(photo_bytes) / (1024 * 1024):.2f}MB")
                return None, f'Image size exceeds 10MB limit (size: {len(photo_bytes) / (1024 * 1024):.2f}MB)'
            mime_type = data.mimetype
        else:
            # Handle base64
            match = re.match(r'^data:(image/[\w+]+);base64,(.+)$', data)
            if not match:
                logger.warning("Invalid image format")
                return None, 'Invalid image format. Must include valid MIME type and base64 data'
            mime_type, base64_string = match.groups()
            if mime_type not in SUPPORTED_IMAGE_TYPES:
                logger.warning(f"Unsupported image type: {mime_type}")
                return None, f'Unsupported image type. Supported types: {", ".join(SUPPORTED_IMAGE_TYPES.keys())}'
            photo_bytes = base64.b64decode(base64_string)
            if len(photo_bytes) > MAX_IMAGE_SIZE:
                logger.warning(f"Image size exceeds 10MB: {len(photo_bytes) / (1024 * 1024):.2f}MB")
                return None, f'Image size exceeds 10MB limit (size: {len(photo_bytes) / (1024 * 1024):.2f}MB)'
        logger.debug("Image validation successful")
        return photo_bytes, mime_type
    except Exception as e:
        logger.error(f"Image validation error: {e}")
        return None, 'Invalid image data'

@app.route('/')
def home():
    logger.debug("Received request for /")
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name, description, price, CASE WHEN photo IS NOT NULL THEN TRUE ELSE FALSE END AS has_photo FROM adminaccess")
            perfumes = cursor.fetchall()
        connection.close()
        logger.info("Fetched perfumes successfully")
        return jsonify({
            'message': 'Welcome to the Perfume Store API!',
            'perfumes': perfumes
        })
    except Exception as e:
        logger.error(f"Error fetching perfumes: {e}")
        return jsonify({'error': f'Error fetching perfumes: {str(e)}'}), 500

@app.route('/perfumes/photo/<int:id>', methods=['GET'])
def get_perfume_photo(id):
    logger.debug(f"Received request for /perfumes/photo/{id}")
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT photo FROM adminaccess WHERE id = %s", (id,))
            result = cursor.fetchone()
            if not result or not result['photo']:
                connection.close()
                logger.warning(f"Photo not found for id: {id}")
                return jsonify({'error': 'Photo not found'}), 404
            photo_base64 = base64.b64encode(result['photo']).decode('utf-8')
            connection.close()
            logger.info(f"Fetched photo for id: {id}")
            return jsonify({'photo': f'data:image/jpeg;base64,{photo_base64}'})
    except Exception as e:
        connection.close()
        logger.error(f"Error fetching photo for id {id}: {e}")
        return jsonify({'error': f'Error fetching photo: {str(e)}'}), 500

@app.route('/admin/perfumes', methods=['GET', 'POST', 'PUT', 'DELETE'])
def admin_perfumes():
    logger.debug(f"Received request for /admin/perfumes ({request.method})")
    check_auth_token()
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            if request.method == 'GET':
                cursor.execute("SELECT id, name, description, price, CASE WHEN photo IS NOT NULL THEN TRUE ELSE FALSE END AS has_photo FROM adminaccess")
                perfumes = cursor.fetchall()
                connection.close()
                logger.info("Fetched perfumes for admin")
                return jsonify({'perfumes': perfumes})

            elif request.method == 'POST':
                photo = None
                mime_type = None
                if request.content_type.startswith('multipart/form-data'):
                    logger.debug("Processing multipart/form-data")
                    data = request.form
                    if not data or not all(key in data for key in ['name', 'description', 'price']):
                        connection.close()
                        logger.warning("Missing required fields in form-data")
                        return jsonify({'error': 'Missing required fields: name, description, price'}), 400
                    if 'photo' in request.files:
                        photo_file = request.files['photo']
                        if photo_file.filename:
                            photo, error = validate_image(photo_file, is_file=True)
                            if error:
                                connection.close()
                                logger.warning(f"Image validation failed: {error}")
                                return jsonify({'error': error}), 400
                    else:
                        logger.debug("No photo provided in form-data")
                else:
                    logger.debug("Processing JSON data")
                    data = request.get_json()
                    if not data or not all(key in data for key in ['name', 'description', 'price']):
                        connection.close()
                        logger.warning("Missing required fields in JSON")
                        return jsonify({'error': 'Missing required fields: name, description, price'}), 400
                    if 'photo' in data and data['photo']:
                        photo, error = validate_image(data['photo'])
                        if error:
                            connection.close()
                            logger.warning(f"Image validation failed: {error}")
                            return jsonify({'error': error}), 400
                cursor.execute("""
                    INSERT INTO adminaccess (name, description, price, photo)
                    VALUES (%s, %s, %s, %s)
                """, (data['name'], data['description'], float(data['price']), photo))
                connection.commit()
                connection.close()
                logger.info(f"Created perfume: {data['name']}")
                return jsonify({'message': 'Perfume created successfully'}), 201

            elif request.method == 'PUT':
                photo = None
                if request.content_type.startswith('multipart/form-data'):
                    logger.debug("Processing multipart/form-data")
                    data = request.form
                    if not data or 'id' not in data or not all(key in data for key in ['name', 'description', 'price']):
                        connection.close()
                        logger.warning("Missing required fields in form-data")
                        return jsonify({'error': 'Missing required fields: id, name, description, price'}), 400
                    if 'photo' in request.files:
                        photo_file = request.files['photo']
                        if photo_file.filename:
                            photo, error = validate_image(photo_file, is_file=True)
                            if error:
                                connection.close()
                                logger.warning(f"Image validation failed: {error}")
                                return jsonify({'error': error}), 400
                    else:
                        logger.debug("No photo provided in form-data")
                else:
                    logger.debug("Processing JSON data")
                    data = request.get_json()
                    if not data or 'id' not in data or not all(key in data for key in ['name', 'description', 'price']):
                        connection.close()
                        logger.warning("Missing required fields in JSON")
                        return jsonify({'error': 'Missing required fields: id, name, description, price'}), 400
                    if 'photo' in data:
                        if data['photo']:
                            photo, error = validate_image(data['photo'])
                            if error:
                                connection.close()
                                logger.warning(f"Image validation failed: {error}")
                                return jsonify({'error': error}), 400
                        else:
                            photo = None  # Allow clearing the photo
                cursor.execute("""
                    UPDATE adminaccess
                    SET name = %s, description = %s, price = %s, photo = %s
                    WHERE id = %s
                """, (data['name'], data['description'], float(data['price']), photo, int(data['id'])))
                if cursor.rowcount == 0:
                    connection.close()
                    logger.warning(f"Perfume not found for id: {data['id']}")
                    return jsonify({'error': 'Perfume not found'}), 404
                connection.commit()
                connection.close()
                logger.info(f"Updated perfume id: {data['id']}")
                return jsonify({'message': 'Perfume updated successfully'})

            elif request.method == 'DELETE':
                data = request.get_json()
                logger.debug(f"DELETE data: {data}")
                if not data or 'id' not in data:
                    connection.close()
                    logger.warning("Missing required field: id")
                    return jsonify({'error': 'Missing required field: id'}), 400
                cursor.execute("DELETE FROM adminaccess WHERE id = %s", (int(data['id']),))
                if cursor.rowcount == 0:
                    connection.close()
                    logger.warning(f"Perfume not found for id: {data['id']}")
                    return jsonify({'error': 'Perfume not found'}), 404
                connection.commit()
                connection.close()
                logger.info(f"Deleted perfume id: {data['id']}")
                return jsonify({'message': 'Perfume deleted successfully'})

    except Exception as e:
        connection.close()
        logger.error(f"Error processing /admin/perfumes: {e}")
        return jsonify({'error': f'Error processing request: {str(e)}'}), 500

if __name__ == '__main__':
    logger.info("Starting Flask application")
    app.run(debug=True, host='127.0.0.1', port=5000)