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
        'username': user_data['name'],
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

@app.route('/register', methods=['POST'])
def register_user():
    try:
        data = request.get_json()
        email = data.get('email')
        name = data.get('name')
        password = hash_password(data.get('password'))
        budget = data.get('budget')

        # Check if user exists
        query = "MATCH (u:User {email: $email}) RETURN u"
        if db.execute_query(query, {"email": email}):
            return jsonify({"status": "error", "message": "Email ya registrado"}), 400

        # Create user
        query = """
        CREATE (u:User {id: randomUUID(), name: $name, email: $email, password: $password, budget: $budget})
        RETURN u.id as id, u.name as name, u.email as email, u.budget as budget
        """
        user = db.execute_query(query, {"name": name, "email": email, "password": password, "budget": budget})[0]
        token = generate_jwt_token(user)
        return jsonify({"status": "success", "user": user, "token": token})
    except Exception as e:
        return handle_error(e, "Error al registrar")

@app.route('/login', methods=['POST'])
def login_user():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        query = "MATCH (u:User {email: $email}) RETURN u"
        result = db.execute_query(query, {"email": email})
        if not result:
            return jsonify({"status": "error", "message": "Usuario no encontrado"}), 404

        user = result[0]['u']
        if not verify_password(password, user['password']):
            return jsonify({"status": "error", "message": "Contraseña incorrecta"}), 401

        token = generate_jwt_token(user)
        user_data = {k: user[k] for k in ['id', 'name', 'email', 'budget']}
        return jsonify({"status": "success", "user": user_data, "token": token})
    except Exception as e:
        return handle_error(e, "Error al iniciar sesión")

@app.route('/comment', methods=['POST'])
@token_required
def add_comment():
    try:
        data = request.get_json()
        text = data.get('text')
        restaurant_id = data.get('restaurant_id')
        author = request.current_user['username']

        logger.info(f"Comentario recibido: '{text}' para restaurante ID: {restaurant_id} por {author}")

        # Verificar existencia de usuario
        user_check = db.execute_query("MATCH (u:User {name: $name}) RETURN u", {"name": author})
        if not user_check:
            logger.warning(f"Usuario no encontrado: {author}")
            return jsonify({"status": "error", "message": "Usuario no encontrado"}), 404

        # Verificar existencia de restaurante
        restaurant_check = db.execute_query("MATCH (r:Restaurant {id: $id}) RETURN r", {"id": restaurant_id})
        if not restaurant_check:
            logger.warning(f"Restaurante no encontrado con ID: {restaurant_id}")
            return jsonify({"status": "error", "message": "Restaurante no encontrado"}), 404

        # Crear comentario
        query = """
        MATCH (u:User {name: $author}), (r:Restaurant {id: $restaurant_id})
        CREATE (c:Comment {id: randomUUID(), text: $text, timestamp: timestamp()})
        CREATE (u)-[:WROTE]->(c)-[:ABOUT]->(r)
        RETURN c.text AS text, c.timestamp AS timestamp
        """
        comment_result = db.execute_query(query, {
            "author": author,
            "restaurant_id": restaurant_id,
            "text": text
        })

        return jsonify({"status": "success", "comment": comment_result[0]})
    except Exception as e:
        return handle_error(e, "Error al guardar comentario")





#-----------------------------------------------------------------------------------------------------#

if __name__ == '__main__':
    try:
        db.connect()
        logger.info("Starting Flask server...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Startup failed: {e}")
    finally:
        db.close()
