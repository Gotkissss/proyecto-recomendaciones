from flask import Flask, jsonify, request
from neo4j import GraphDatabase
import os
from flask_cors import CORS
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Allow frontend to connect

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

# Helper function for error handling
def handle_error(e, message="An error occurred"):
    logger.error(f"{message}: {str(e)}")
    return jsonify({
        "status": "error",
        "message": f"{message}: {str(e)}"
    }), 500

@app.route('/')
def home():
    return jsonify({
        "message": "Restaurant Recommendation System API",
        "status": "running",
        "version": "1.0",
        "endpoints": {
            "get_recommendations": "/recommendations/<user_name>",
            "advanced_recommendations": "/recommendations/advanced",
            "get_all_restaurants": "/restaurants",
            "get_restaurant_details": "/restaurants/<restaurant_id>",
            "get_all_users": "/users",
            "get_user_details": "/users/<user_name>",
            "add_user": "/add_user",
            "add_restaurant": "/add_restaurant",
            "update_user_preferences": "/users/<user_name>/preferences",
            "search_restaurants": "/restaurants/search"
        }
    })

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

@app.route('/restaurants/<restaurant_id>')
def get_restaurant_details(restaurant_id):
    """Get detailed information about a specific restaurant"""
    query = """
    MATCH (r:Restaurant {id: $restaurant_id})
    OPTIONAL MATCH (r)-[:HAS_CATEGORY]->(c:Category)
    OPTIONAL MATCH (r)-[:HAS_AMBIANCE]->(a:Ambiance)
    OPTIONAL MATCH (r)-[:LOCATED_IN]->(z:Zone)
    RETURN r.id as id, r.nombre as name, r.precio_promedio as price,
           r.pet_friendly as pet_friendly, r.juegos_niños as kids_games,
           r.accesible as accessible, r.promociones as promotions,
           r.capacidad as capacity, r.acepta_reservas as accepts_reservations,
           r.nivel_servicio as service_level, r.tiempo_espera as wait_time,
           r.horario_apertura as opening_hours, r.telefono as phone,
           r.direccion as address, r.terraza as has_terrace,
           collect(DISTINCT c.nombre) as categories,
           collect(DISTINCT a.name) as ambiance,
           collect(DISTINCT z.name) as zones
    """
    try:
        results = db.execute_query(query, {"restaurant_id": restaurant_id})
        if not results:
            return jsonify({
                "status": "error",
                "message": "Restaurant not found"
            }), 404
        
        return jsonify({
            "status": "success",
            "restaurant": results[0]
        })
    except Exception as e:
        return handle_error(e, "Failed to fetch restaurant details")

@app.route('/users')
def get_all_users():
    """Get all users with their preferences"""
    query = """
    MATCH (u:User)
    OPTIONAL MATCH (u)-[:PREFERS]->(c:Category)
    OPTIONAL MATCH (u)-[:LIKES_AMBIANCE]->(a:Ambiance)
    OPTIONAL MATCH (u)-[:PREFERS_ZONE]->(z:Zone)
    RETURN u.id as id, u.name as name, u.age as age, u.budget as budget,
           u.tiene_mascota as has_pet, u.tiene_niños as has_children,
           u.necesita_accesibilidad as needs_accessibility,
           collect(DISTINCT c.nombre) as preferred_categories,
           collect(DISTINCT a.name) as preferred_ambiance,
           collect(DISTINCT z.name) as preferred_zones
    ORDER BY u.name
    """
    try:
        results = db.execute_query(query)
        return jsonify({
            "status": "success",
            "count": len(results),
            "users": results
        })
    except Exception as e:
        return handle_error(e, "Failed to fetch users")

@app.route('/users/<user_name>')
def get_user_details(user_name):
    """Get detailed information about a specific user"""
    query = """
    MATCH (u:User {name: $user_name})
    OPTIONAL MATCH (u)-[:PREFERS]->(c:Category)
    OPTIONAL MATCH (u)-[:LIKES_AMBIANCE]->(a:Ambiance)
    OPTIONAL MATCH (u)-[:PREFERS_ZONE]->(z:Zone)
    RETURN u.id as id, u.name as name, u.age as age, u.budget as budget,
           u.tiene_mascota as has_pet, u.tiene_niños as has_children,
           u.necesita_accesibilidad as needs_accessibility,
           u.desea_promociones as wants_promotions, u.cantidad_personas as group_size,
           collect(DISTINCT c.nombre) as preferred_categories,
           collect(DISTINCT a.name) as preferred_ambiance,
           collect(DISTINCT z.name) as preferred_zones
    """
    try:
        results = db.execute_query(query, {"user_name": user_name})
        if not results:
            return jsonify({
                "status": "error",
                "message": "User not found"
            }), 404
        
        return jsonify({
            "status": "success",
            "user": results[0]
        })
    except Exception as e:
        return handle_error(e, "Failed to fetch user details")

@app.route('/recommendations/<user_name>')
def get_recommendations(user_name):
    """Get personalized restaurant recommendations for a user (enhanced algorithm)"""
    query = """
    MATCH (u:User {name: $user_name})
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

@app.route('/recommendations/advanced', methods=['POST'])
def get_advanced_recommendations():
    """Get recommendations based on custom criteria sent in request body"""
    try:
        data = request.json
        
        # Build dynamic query based on provided criteria
        conditions = ["r.precio_promedio <= $budget"]
        parameters = {"budget": data.get("budget", 1000)}
        
        if data.get("zone"):
            conditions.append("EXISTS((r)-[:LOCATED_IN]->(:Zone {name: $zone}))")
            parameters["zone"] = data["zone"]
        
        if data.get("categories"):
            conditions.append("EXISTS((r)-[:HAS_CATEGORY]->(:Category)) AND ANY(cat IN $categories WHERE EXISTS((r)-[:HAS_CATEGORY]->(:Category {nombre: cat})))")
            parameters["categories"] = data["categories"]
        
        if data.get("pet_friendly"):
            conditions.append("r.pet_friendly = true")
        
        if data.get("kids_games"):
            conditions.append("r.juegos_niños = true")
        
        if data.get("accessible"):
            conditions.append("r.accesible = true")
        
        if data.get("promotions"):
            conditions.append("r.promociones = true")
        
        if data.get("min_service_level"):
            conditions.append("r.nivel_servicio >= $min_service_level")
            parameters["min_service_level"] = data["min_service_level"]
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
        MATCH (r:Restaurant)
        WHERE {where_clause}
        OPTIONAL MATCH (r)-[:HAS_CATEGORY]->(c:Category)
        OPTIONAL MATCH (r)-[:HAS_AMBIANCE]->(a:Ambiance)
        OPTIONAL MATCH (r)-[:LOCATED_IN]->(z:Zone)
        RETURN r.id as restaurant_id, r.nombre as restaurant_name,
               r.precio_promedio as price, r.pet_friendly as pet_friendly,
               r.juegos_niños as kids_games, r.accesible as accessible,
               r.promociones as promotions, r.nivel_servicio as service_level,
               collect(DISTINCT c.nombre) as categories,
               collect(DISTINCT a.name) as ambiance,
               collect(DISTINCT z.name) as zones
        ORDER BY r.nivel_servicio DESC, r.precio_promedio ASC
        """
        
        results = db.execute_query(query, parameters)
        
        return jsonify({
            "status": "success",
            "criteria": data,
            "count": len(results),
            "recommendations": results
        })
    except Exception as e:
        return handle_error(e, "Failed to generate advanced recommendations")

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

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add a new user to the system"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ["name", "age", "budget"]
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "status": "error",
                    "message": f"Missing required field: {field}"
                }), 400
        
        query = """
        CREATE (u:User {
            id: randomUUID(),
            name: $name,
            age: $age,
            budget: $budget,
            tiene_mascota: $has_pet,
            tiene_niños: $has_children,
            necesita_accesibilidad: $needs_accessibility,
            desea_promociones: $wants_promotions,
            cantidad_personas: $group_size,
            created_at: datetime()
        })
        RETURN u.id as id, u.name as name
        """
        parameters = {
            "name": data["name"],
            "age": data["age"],
            "budget": data["budget"],
            "has_pet": data.get("has_pet", False),
            "has_children": data.get("has_children", False),
            "needs_accessibility": data.get("needs_accessibility", False),
            "wants_promotions": data.get("wants_promotions", False),
            "group_size": data.get("group_size", 2)
        }
        
        result = db.execute_query(query, parameters)
        
        return jsonify({
            "status": "success",
            "message": f"User {data['name']} added successfully",
            "user": result[0] if result else None
        })
    except Exception as e:
        return handle_error(e, "Failed to add user")

@app.route('/add_restaurant', methods=['POST'])
def add_restaurant():
    """Add a new restaurant to the system"""
    try:
        data = request.json
        
        # Validate required fields
        required_fields = ["nombre", "precio_promedio"]
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "status": "error",
                    "message": f"Missing required field: {field}"
                }), 400
        
        query = """
        CREATE (r:Restaurant {
            id: randomUUID(),
            nombre: $nombre,
            precio_promedio: $precio_promedio,
            pet_friendly: $pet_friendly,
            juegos_niños: $juegos_niños,
            accesible: $accesible,
            promociones: $promociones,
            capacidad: $capacidad,
            acepta_reservas: $acepta_reservas,
            nivel_servicio: $nivel_servicio,
            tiempo_espera: $tiempo_espera,
            created_at: datetime()
        })
        RETURN r.id as id, r.nombre as nombre
        """
        parameters = {
            "nombre": data["nombre"],
            "precio_promedio": data["precio_promedio"],
            "pet_friendly": data.get("pet_friendly", False),
            "juegos_niños": data.get("juegos_niños", False),
            "accesible": data.get("accesible", False),
            "promociones": data.get("promociones", False),
            "capacidad": data.get("capacidad", 50),
            "acepta_reservas": data.get("acepta_reservas", True),
            "nivel_servicio": data.get("nivel_servicio", 3),
            "tiempo_espera": data.get("tiempo_espera", 15)
        }
        
        result = db.execute_query(query, parameters)
        
        return jsonify({
            "status": "success",
            "message": f"Restaurant {data['nombre']} added successfully",
            "restaurant": result[0] if result else None
        })
    except Exception as e:
        return handle_error(e, "Failed to add restaurant")

@app.route('/users/<user_name>/preferences', methods=['PUT'])
def update_user_preferences(user_name):
    """Update user preferences"""
    try:
        data = request.json
        
        # Update user properties
        set_clauses = []
        parameters = {"user_name": user_name}
        
        updatable_fields = {
            "budget": "u.budget = $budget",
            "has_pet": "u.tiene_mascota = $has_pet",
            "has_children": "u.tiene_niños = $has_children",
            "needs_accessibility": "u.necesita_accesibilidad = $needs_accessibility",
            "wants_promotions": "u.desea_promociones = $wants_promotions",
            "group_size": "u.cantidad_personas = $group_size"
        }
        
        for field, clause in updatable_fields.items():
            if field in data:
                set_clauses.append(clause)
                parameters[field] = data[field]
        
        if not set_clauses:
            return jsonify({
                "status": "error",
                "message": "No valid fields to update"
            }), 400
        
        query = f"""
        MATCH (u:User {{name: $user_name}})
        SET {', '.join(set_clauses)}
        RETURN u.name as name
        """
        
        result = db.execute_query(query, parameters)
        
        if not result:
            return jsonify({
                "status": "error",
                "message": "User not found"
            }), 404
        
        return jsonify({
            "status": "success",
            "message": f"Preferences updated for user {user_name}"
        })
    except Exception as e:
        return handle_error(e, "Failed to update user preferences")

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

if __name__ == '__main__':
    try:
        db.connect()
        logger.info("Starting Flask application...")
        app.run(debug=True, host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
    finally:
        db.close()