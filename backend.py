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

# Neo4j connection
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
        RETURN
            r.id as id,
            r.nombre as name,
            r.precio_promedio as price,
            r.ubicacion as location,
            r.telefono as phone,
            r.horario as schedule,
            r.calificacion as rating,
            r.resenas as reviews,
            r.web as website,
            r.instagram as instagram,
            r.facebook as facebook,
            r.pet_friendly as pet_friendly,
            r.juegos_ninios as kids_games,
            r.accesible as accessible,
            r.promociones as promotions,
            r.acepta_reservas as accepts_reservations,
            r.delivery as delivery,
            r.takeout as takeout,
            r.terraza as outdoor_seating,
            r.wifi as wifi,
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
        query = "MATCH (u:User {email: $email}) RETURN u"
        if db.execute_query(query, {"email": email}):
            return jsonify({"status": "error", "message": "Email ya registrado"}), 400
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
        timestamp = datetime.utcnow().isoformat()

        line = f"{timestamp} | {author} | Restaurante ID: {restaurant_id} | {text}\n"

        with open("comentarios.txt", "a", encoding="utf-8") as f:
            f.write(line)

        return jsonify({"status": "success", "comment": {
            "text": text,
            "author": author,
            "timestamp": timestamp
        }})

    except Exception as e:
        return handle_error(e, "Error al guardar comentario")
    
@app.route('/comments/<restaurant_id>', methods=['GET'])
def get_comments(restaurant_id):
    try:
        comments = []
        if os.path.exists("comentarios.txt"):
            with open("comentarios.txt", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(" | ")
                    if len(parts) == 4 and f"Restaurante ID: {restaurant_id}" in parts[2]:
                        comments.append({
                            "timestamp": parts[0],
                            "author": parts[1],
                            "text": parts[3]
                        })
        return jsonify({"status": "success", "comments": comments})
    except Exception as e:
        return handle_error(e, "Error al leer comentarios")


@app.route('/rate', methods=['POST'])
@token_required
def rate_restaurant():
    try:
        data = request.get_json()
        restaurant_id = data.get('restaurant_id')
        score = int(data.get('score'))
        user_id = request.current_user['user_id']

        if score < 1 or score > 5:
            return jsonify({"status": "error", "message": "La calificación debe estar entre 1 y 5"}), 400

        query = """
        MATCH (u:User {id: $user_id}), (r:Restaurant {id: $restaurant_id})
        MERGE (u)-[rel:RATED]->(r)
        SET rel.score = $score
        RETURN rel.score AS score
        """

        result = db.execute_query(query, {"user_id": user_id, "restaurant_id": restaurant_id, "score": score})
        return jsonify({"status": "success", "score": result[0]['score']})
    except Exception as e:
        return handle_error(e, "Error al guardar calificación")

@app.route('/rating/<restaurant_id>', methods=['GET'])
def get_restaurant_rating(restaurant_id):
    try:
        query = """
        MATCH (:User)-[r:RATED]->(res:Restaurant {id: $restaurant_id})
        RETURN avg(r.score) AS average, count(r) AS total
        """
        result = db.execute_query(query, {"restaurant_id": restaurant_id})
        rating = result[0]
        return jsonify({
            "status": "success",
            "average": round(rating["average"], 2) if rating["average"] is not None else None,
            "total": rating["total"]
        })
    except Exception as e:
        return handle_error(e, "Error al obtener calificación")




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