from flask import Flask, jsonify, request, session
from neo4j import GraphDatabase
import os
from flask_cors import CORS
from datetime import datetime, timedelta
import logging
from dotenv import load_dotenv
import bcrypt
import jwt
from functools import wraps
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
CORS(app, supports_credentials=True)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key")

# JWT config
JWT_SECRET = os.getenv("JWT_SECRET", "your-jwt-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Neo4j
class Neo4jConnection:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI")
        self.username = os.getenv("NEO4J_USERNAME")
        self.password = os.getenv("NEO4J_PASSWORD")
        self.driver = None

    def connect(self):
        self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
        with self.driver.session() as session:
            session.run("RETURN 1")

    def close(self):
        if self.driver:
            self.driver.close()

    def execute_query(self, query, parameters=None):
        with self.driver.session() as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

# Init DB
db = Neo4jConnection()

# Helpers
def handle_error(e, msg="An error occurred"):
    logger.error(f"{msg}: {str(e)}")
    return jsonify({"status": "error", "message": f"{msg}: {str(e)}"}), 500

def hash_password(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_jwt_token(user_data):
    payload = {
        'user_id': user_data['id'],
        'username': user_data['username'],
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'status': 'error', 'message': 'Token is missing'}), 401

        if token.startswith('Bearer '):
            token = token[7:]
        payload = verify_jwt_token(token)
        if not payload:
            return jsonify({'status': 'error', 'message': 'Token is invalid or expired'}), 401

        request.current_user = payload
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def home():
    return jsonify({"status": "running"})

@app.route('/categories', methods=['GET'])
def get_all_categories():
    try:
        query = """
        MATCH (c:Category)
        RETURN DISTINCT c.nombre AS name
        ORDER BY name
        """
        results = db.execute_query(query)
        categories = [r['name'] for r in results]
        return jsonify({"status": "success", "categories": categories})
    except Exception as e:
        return handle_error(e, "Failed to fetch categories")

@app.route('/restaurants')
def get_all_restaurants():
    try:
        query = """
        MATCH (r:Restaurant)
        OPTIONAL MATCH (r)-[:HAS_CATEGORY]->(c:Category)
        RETURN r.id as id, r.nombre as name, r.precio_promedio as price,
               r.pet_friendly as pet_friendly, r.juegos_niños as kids_games,
               r.accesible as accessible, r.promociones as promotions,
               r.acepta_reservas as accepts_reservations,
               collect(DISTINCT c.nombre) as categories
        ORDER BY r.nombre
        """
        results = db.execute_query(query)
        return jsonify({"status": "success", "restaurants": results})
    except Exception as e:
        return handle_error(e, "Failed to fetch restaurants")

@app.route('/health')
def health():
    try:
        db.execute_query("RETURN 1")
        return jsonify({"status": "healthy"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)})

if __name__ == '__main__':
    try:
        db.connect()
        logger.info("Starting Flask server...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Startup failed: {e}")
    finally:
        db.close()
