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

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, supports_credentials=True)  # Allow credentials for session management
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-change-this")

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-jwt-secret-change-this")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Neo4j connection configuration
class Neo4jConnection:
    def __init__(self):
        # Replace with your Neo4j Aura credentials
        self.uri = os.getenv("NEO4J_URI", "neo4j+s://your-instance-id.databases.neo4j.io")
        self.username = os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "your-password")
        self.driver = None
    
    def connect(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.username, self.password))
            # Test connection
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Connected to Neo4j successfully!")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def close(self):
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")
    
    def execute_query(self, query, parameters=None):
        if not self.driver:
            raise Exception("Database not connected")
        
        with self.driver.session() as session:
            try:
                result = session.run(query, parameters or {})
                return [record.data() for record in result]
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                raise

# Initialize database connection
db = Neo4jConnection()

# Helper functions
def handle_error(e, message="An error occurred"):
    logger.error(f"{message}: {str(e)}")
    return jsonify({
        "status": "error",
        "message": f"{message}: {str(e)}"
    }), 500

def hash_password(password):
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password, hashed):
    """Verify a password against its hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def generate_jwt_token(user_data):
    """Generate JWT token for user"""
    payload = {
        'user_id': user_data['id'],
        'username': user_data['username'],
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token):
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Za-z]', password):
        return False, "Password must contain at least one letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, "Password is valid"

# Authentication decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'status': 'error', 'message': 'Token is missing'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            payload = verify_jwt_token(token)
            if not payload:
                return jsonify({'status': 'error', 'message': 'Token is invalid or expired'}), 401
            request.current_user = payload
        except Exception as e:
            return jsonify({'status': 'error', 'message': 'Token is invalid'}), 401
        
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def home():
    return jsonify({
        "message": "Restaurant Recommendation System API",
        "status": "running",
        "version": "2.0",
        "endpoints": {
            "auth": {
                "register": "/auth/register",
                "login": "/auth/login",
                "logout": "/auth/logout",
                "profile": "/auth/profile"
            },
            "restaurants": {
                "get_all": "/restaurants",
                "get_details": "/restaurants/<restaurant_id>",
                "search": "/restaurants/search"
            },
            "recommendations": {
                "personalized": "/recommendations/<user_name>",
                "advanced": "/recommendations/advanced"
            },
            "users": {
                "get_all": "/users",
                "get_details": "/users/<user_name>",
                "update_preferences": "/users/<user_name>/preferences"
            }
        }
    })

# Authentication Routes
@app.route('/auth/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ["username", "email", "password", "name", "age", "budget"]
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    "status": "error",
                    "message": f"Missing required field: {field}"
                }), 400
        
        # Validate email format
        if not validate_email(data["email"]):
            return jsonify({
                "status": "error",
                "message": "Invalid email format"
            }), 400
        
        # Validate password strength
        is_valid, message = validate_password(data["password"])
        if not is_valid:
            return jsonify({
                "status": "error",
                "message": message
            }), 400
        
        # Check if user already exists
        check_query = """
        MATCH (u:User)
        WHERE u.username = $username OR u.email = $email
        RETURN u.username as username, u.email as email
        """
        existing_users = db.execute_query(check_query, {
            "username": data["username"].lower(),
            "email": data["email"].lower()
        })
        
        if existing_users:
            existing_user = existing_users[0]
            if existing_user["username"] == data["username"].lower():
                return jsonify({
                    "status": "error",
                    "message": "Username already exists"
                }), 409
            else:
                return jsonify({
                    "status": "error",
                    "message": "Email already exists"
                }), 409
        
        # Hash password
        password_hash = hash_password(data["password"])
        
        # Create user
        create_query = """
        CREATE (u:User {
            id: randomUUID(),
            username: $username,
            email: $email,
            password_hash: $password_hash,
            name: $name,
            age: $age,
            budget: $budget,
            tiene_mascota: $has_pet,
            tiene_niños: $has_children,
            necesita_accesibilidad: $needs_accessibility,
            desea_promociones: $wants_promotions,
            cantidad_personas: $group_size,
            is_active: true,
            created_at: datetime(),
            updated_at: datetime()
        })
        RETURN u.id as id, u.username as username, u.email as email, u.name as name
        """
        
        parameters = {
            "username": data["username"].lower(),
            "email": data["email"].lower(),
            "password_hash": password_hash,
            "name": data["name"],
            "age": data["age"],
            "budget": data["budget"],
            "has_pet": data.get("has_pet", False),
            "has_children": data.get("has_children", False),
            "needs_accessibility": data.get("needs_accessibility", False),
            "wants_promotions": data.get("wants_promotions", False),
            "group_size": data.get("group_size", 2)
        }
        
        result = db.execute_query(create_query, parameters)
        
        if result:
            user_data = result[0]
            token = generate_jwt_token(user_data)
            
            return jsonify({
                "status": "success",
                "message": "User registered successfully",
                "user": {
                    "id": user_data["id"],
                    "username": user_data["username"],
                    "email": user_data["email"],
                    "name": user_data["name"]
                },
                "token": token
            }), 201
        else:
            return jsonify({
                "status": "error",
                "message": "Failed to create user"
            }), 500
            
    except Exception as e:
        return handle_error(e, "Registration failed")

@app.route('/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.json
        
        # Validate required fields
        if not data.get("username") or not data.get("password"):
            return jsonify({
                "status": "error",
                "message": "Username and password are required"
            }), 400
        
        # Find user by username or email
        query = """
        MATCH (u:User)
        WHERE (u.username = $login OR u.email = $login) AND u.is_active = true
        RETURN u.id as id, u.username as username, u.email as email, u.name as name,
               u.password_hash as password_hash, u.age as age, u.budget as budget,
               u.tiene_mascota as has_pet, u.tiene_niños as has_children,
               u.necesita_accesibilidad as needs_accessibility,
               u.desea_promociones as wants_promotions,
               u.cantidad_personas as group_size
        """
        
        users = db.execute_query(query, {"login": data["username"].lower()})
        
        if not users:
            return jsonify({
                "status": "error",
                "message": "Invalid username or password"
            }), 401
        
        user = users[0]
        
        # Verify password
        if not verify_password(data["password"], user["password_hash"]):
            return jsonify({
                "status": "error",
                "message": "Invalid username or password"
            }), 401
        
        # Generate token
        token = generate_jwt_token(user)
        
        # Update last login
        update_query = """
        MATCH (u:User {id: $user_id})
        SET u.last_login = datetime(), u.updated_at = datetime()
        """
        db.execute_query(update_query, {"user_id": user["id"]})
        
        return jsonify({
            "status": "success",
            "message": "Login successful",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "name": user["name"],
                "age": user["age"],
                "budget": user["budget"],
                "has_pet": user["has_pet"],
                "has_children": user["has_children"],
                "needs_accessibility": user["needs_accessibility"],
                "wants_promotions": user["wants_promotions"],
                "group_size": user["group_size"]
            },
            "token": token
        })
        
    except Exception as e:
        return handle_error(e, "Login failed")

@app.route('/auth/logout', methods=['POST'])
@token_required
def logout():
    """Logout user (in a real app, you'd invalidate the token)"""
    return jsonify({
        "status": "success",
        "message": "Logged out successfully"
    })

@app.route('/auth/profile')
@token_required
def get_profile():
    """Get current user profile"""
    try:
        user_id = request.current_user['user_id']
        
        query = """
        MATCH (u:User {id: $user_id})
        OPTIONAL MATCH (u)-[:PREFERS]->(c:Category)
        OPTIONAL MATCH (u)-[:LIKES_AMBIANCE]->(a:Ambiance)
        OPTIONAL MATCH (u)-[:PREFERS_ZONE]->(z:Zone)
        RETURN u.id as id, u.username as username, u.email as email, u.name as name,
               u.age as age, u.budget as budget, u.tiene_mascota as has_pet,
               u.tiene_niños as has_children, u.necesita_accesibilidad as needs_accessibility,
               u.desea_promociones as wants_promotions, u.cantidad_personas as group_size,
               u.created_at as created_at, u.last_login as last_login,
               collect(DISTINCT c.nombre) as preferred_categories,
               collect(DISTINCT a.name) as preferred_ambiance,
               collect(DISTINCT z.name) as preferred_zones
        """
        
        result = db.execute_query(query, {"user_id": user_id})
        
        if not result:
            return jsonify({
                "status": "error",
                "message": "User not found"
            }), 404
        
        return jsonify({
            "status": "success",
            "user": result[0]
        })
        
    except Exception as e:
        return handle_error(e, "Failed to get profile")

# Update existing routes to work with new auth system
@app.route('/recommendations/<user_name>')
def get_recommendations(user_name):
    """Get personalized restaurant recommendations for a user (enhanced algorithm)"""
    query = """
    MATCH (u:User {username: $user_name})
    MATCH (r:Restaurant)
    WHERE r.precio_promedio <= u.budget
    
    // Calculate compatibility scores for different criteria
    WITH u, r,
         // Category match
         CASE WHEN EXISTS((u)-[:PREFERS]->(:Category)<-[:HAS_CATEGORY]-(r)) THEN 2 ELSE 0 END as category_score,
         // Ambiance match
         CASE WHEN EXISTS((u)-[:LIKES_AMBIANCE]->(:Ambiance)<-[:HAS_AMBIANCE]-(r)) THEN 2 ELSE 0 END as ambiance_score,
         // Zone match
         CASE WHEN EXISTS((u)-[:PREFERS_ZONE]->(:Zone)<-[:LOCATED_IN]-(r)) THEN 1 ELSE 0 END as zone_score,
         // Pet-friendly match
         CASE WHEN u.tiene_mascota = true AND r.pet_friendly = true THEN 1 
              WHEN u.tiene_mascota = false OR r.pet_friendly = true THEN 0 
              ELSE -1 END as pet_score,
         // Kids games match
         CASE WHEN u.tiene_niños = true AND r.juegos_niños = true THEN 1 
              WHEN u.tiene_niños = false OR r.juegos_niños = true THEN 0 
              ELSE -1 END as kids_score,
         // Accessibility match
         CASE WHEN u.necesita_accesibilidad = true AND r.accesible = true THEN 2 
              WHEN u.necesita_accesibilidad = false OR r.accesible = true THEN 0 
              ELSE -2 END as accessibility_score,
         // Promotions match
         CASE WHEN u.desea_promociones = true AND r.promociones = true THEN 1 ELSE 0 END as promotion_score,
         // Capacity check
         CASE WHEN r.capacidad >= u.cantidad_personas THEN 0 ELSE -3 END as capacity_score
    
    WITH u, r, (category_score + ambiance_score + zone_score + pet_score + 
                kids_score + accessibility_score + promotion_score + capacity_score) as total_score
    
    WHERE total_score >= 1  // Only recommend restaurants with positive compatibility
    
    OPTIONAL MATCH (r)-[:HAS_CATEGORY]->(cat:Category)
    OPTIONAL MATCH (r)-[:HAS_AMBIANCE]->(amb:Ambiance)
    OPTIONAL MATCH (r)-[:LOCATED_IN]->(zone:Zone)
    
    RETURN r.id as restaurant_id, r.nombre as restaurant_name, 
           r.precio_promedio as price, total_score as compatibility_score,
           r.pet_friendly as pet_friendly, r.juegos_niños as kids_games,
           r.accesible as accessible, r.promociones as promotions,
           r.nivel_servicio as service_level, r.tiempo_espera as wait_time,
           collect(DISTINCT cat.nombre) as categories,
           collect(DISTINCT amb.name) as ambiance,
           collect(DISTINCT zone.name) as zones
    ORDER BY total_score DESC, r.precio_promedio ASC
    LIMIT 10
    """
    try:
        results = db.execute_query(query, {"user_name": user_name})
        
        if not results:
            return jsonify({
                "status": "success",
                "user": user_name,
                "message": "No recommendations found matching your criteria",
                "recommendations": []
            })
        
        return jsonify({
            "status": "success",
            "user": user_name,
            "count": len(results),
            "recommendations": results
        })
    except Exception as e:
        return handle_error(e, "Failed to generate recommendations")

# Continue with all other existing routes...
# (Keep all the existing restaurant, search, and other endpoints from the original code)

@app.route('/restaurants')
def get_all_restaurants():
    """Get all restaurants with their details"""
    query = """
    MATCH (r:Restaurant)
    OPTIONAL MATCH (r)-[:HAS_CATEGORY]->(c:Category)
    OPTIONAL MATCH (r)-[:HAS_AMBIANCE]->(a:Ambiance)
    OPTIONAL MATCH (r)-[:LOCATED_IN]->(z:Zone)
    RETURN r.id as id, r.nombre as name, r.precio_promedio as price,
           r.pet_friendly as pet_friendly, r.juegos_niños as kids_games,
           r.accesible as accessible, r.promociones as promotions,
           r.capacidad as capacity, r.acepta_reservas as accepts_reservations,
           r.nivel_servicio as service_level, r.tiempo_espera as wait_time,
           collect(DISTINCT c.nombre) as categories,
           collect(DISTINCT a.name) as ambiance,
           collect(DISTINCT z.name) as zones
    ORDER BY r.nombre
    """
    try:
        results = db.execute_query(query)
        return jsonify({
            "status": "success",
            "count": len(results),
            "restaurants": results
        })
    except Exception as e:
        return handle_error(e, "Failed to fetch restaurants")

@app.route('/restaurants/search')
def search_restaurants():
    """Search restaurants by name or category"""
    search_term = request.args.get('q', '').strip()
    if not search_term:
        return jsonify({
            "status": "error",
            "message": "Search term is required"
        }), 400
    
    query = """
    MATCH (r:Restaurant)
    WHERE toLower(r.nombre) CONTAINS toLower($search_term)
       OR EXISTS((r)-[:HAS_CATEGORY]->(:Category)) AND 
          ANY(cat IN [(r)-[:HAS_CATEGORY]->(c:Category) | c.nombre] 
              WHERE toLower(cat) CONTAINS toLower($search_term))
    OPTIONAL MATCH (r)-[:HAS_CATEGORY]->(c:Category)
    OPTIONAL MATCH (r)-[:LOCATED_IN]->(z:Zone)
    RETURN r.id as id, r.nombre as name, r.precio_promedio as price,
           collect(DISTINCT c.nombre) as categories,
           collect(DISTINCT z.name) as zones
    ORDER BY r.nombre
    """
    try:
        results = db.execute_query(query, {"search_term": search_term})
        return jsonify({
            "status": "success",
            "search_term": search_term,
            "count": len(results),
            "results": results
        })
    except Exception as e:
        return handle_error(e, "Failed to search restaurants")

# Health check endpoint
@app.route('/health')
def health_check():
    """Check if the API and database are working"""
    try:
        # Test database connection
        db.execute_query("RETURN 1 as test")
        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500



# Add these debug endpoints to your backend.py to verify data import

@app.route('/debug/categories', methods=['GET'])
def debug_categories():
    """Debug endpoint to check all categories in the database"""
    try:
        query = """
        MATCH (c:Category)
        RETURN c.id as id, c.nombre as nombre
        ORDER BY c.id
        """
        
        results = db.execute_query(query)
        
        return jsonify({
            'status': 'success',
            'total_categories': len(results),
            'categories': results
        })
        
    except Exception as e:
        return handle_error(e, "Failed to fetch debug categories")

@app.route('/debug/restaurant-categories', methods=['GET'])
def debug_restaurant_categories():
    """Debug endpoint to check restaurant-category relationships"""
    try:
        query = """
        MATCH (r:Restaurant)-[:HAS_CATEGORY]->(c:Category)
        RETURN r.id as restaurant_id, r.nombre as restaurant_name, 
               c.id as category_id, c.nombre as category_name
        ORDER BY r.id, c.id
        """
        
        results = db.execute_query(query)
        
        return jsonify({
            'status': 'success',
            'total_relationships': len(results),
            'relationships': results
        })
        
    except Exception as e:
        return handle_error(e, "Failed to fetch debug restaurant-categories")

@app.route('/debug/node-counts', methods=['GET'])
def debug_node_counts():
    """Debug endpoint to check node counts in the database"""
    try:
        queries = {
            'restaurants': "MATCH (r:Restaurant) RETURN count(r) as count",
            'categories': "MATCH (c:Category) RETURN count(c) as count",
            'has_category_relationships': "MATCH ()-[:HAS_CATEGORY]->() RETURN count(*) as count"
        }
        
        results = {}
        for name, query in queries.items():
            result = db.execute_query(query)
            results[name] = result[0]['count'] if result else 0
        
        return jsonify({
            'status': 'success',
            'node_counts': results
        })
        
    except Exception as e:
        return handle_error(e, "Failed to fetch debug node counts")


if __name__ == '__main__':
    try:
        db.connect()
        logger.info("Starting Flask application...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
    finally:
        db.close()

