# recomendaciones.py
from flask import request, jsonify
from backend import app, db, token_required, handle_error


@app.route('/preferences', methods=['POST'])
@token_required
def save_preferences():
    try:
        user_id = request.current_user['user_id']
        preferences = request.json.get('preferences', {})

        query = """
        MATCH (u:User {id: $user_id})
        SET u.preferences = $preferences
        RETURN u.preferences AS preferences
        """
        import json
        result = db.execute_query(query, {"user_id": user_id, "preferences": json.dumps(preferences)})

        return jsonify({"status": "success", "preferences": result[0]["preferences"]})
    except Exception as e:
        return handle_error(e, "Error al guardar preferencias")

@app.route('/preferences', methods=['GET'])
@token_required
def get_preferences():
    try:
        user_id = request.current_user['user_id']
        query = """
        MATCH (u:User {id: $user_id})
        RETURN u.preferences AS preferences
        """
        result = db.execute_query(query, {"user_id": user_id})
        prefs = result[0].get("preferences") if result else None
        if prefs:
            import json
            prefs = json.loads(prefs)
            
        return jsonify({"status": "success", "preferences": prefs})
    except Exception as e:
        return handle_error(e, "Error al obtener preferencias")
