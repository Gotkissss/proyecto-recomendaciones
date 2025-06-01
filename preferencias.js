// Guarda las preferencias actuales del usuario (filtros aplicados)
async function saveUserPreferences(filters) {
    if (!currentUser) return;
    try {
        await fetch('http://localhost:5000/preferences', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + localStorage.getItem('token'),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ preferences: filters })
        });
        console.log("✅ Preferencias guardadas");
    } catch (err) {
        console.error("❌ Error al guardar preferencias", err);
    }
}

// Obtiene las preferencias guardadas del usuario al iniciar sesión
async function getUserPreferences() {
    if (!currentUser) return null;
    try {
        const res = await fetch('http://localhost:5000/preferences', {
            headers: {
                'Authorization': 'Bearer ' + localStorage.getItem('token')
            }
        });
        const data = await res.json();
        if (data.status === 'success' && data.preferences) {
            return JSON.parse(data.preferences);
        }
    } catch (err) {
        console.error("❌ Error al obtener preferencias", err);
    }
    return null;
}

// Ordena los restaurantes dándoles prioridad a los que coinciden con preferencias
function ordenarRestaurantesPorPreferencias(restaurants, preferences) {
    if (!preferences) return restaurants;

    function scoreRestaurant(r) {
        let score = 0;
        if (preferences.pet_friendly && r.features.pet_friendly) score += 5;
        if (preferences.payment_methods && r.payment_methods?.toLowerCase().includes(preferences.payment_methods.toLowerCase())) score += 3;
        if (preferences.healthy_options && r.healthy_options?.toLowerCase() === preferences.healthy_options.toLowerCase()) score += 2;
        if (preferences.zone && r.zone?.toLowerCase() === preferences.zone.toLowerCase()) score += 1;
        return score;
    }

    return restaurants.slice().sort((a, b) => scoreRestaurant(b) - scoreRestaurant(a));
}
