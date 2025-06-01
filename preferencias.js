async function saveUserPreferences(filters) {
    if (!currentUser) {
        console.log('❌ saveUserPreferences: No hay usuario logueado');
        return;
    }
    
    console.log('💾 Guardando preferencias:', filters);
    console.log('👤 Para usuario:', currentUser.name);
    
    try {
        const token = localStorage.getItem('token');
        const response = await fetch('http://localhost:5000/preferences', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ preferences: filters })
        });
        
        const data = await response.json();
        console.log('📡 Respuesta del servidor al guardar:', data);
        
        if (data.status === 'success') {
            console.log("✅ Preferencias guardadas exitosamente");
        } else {
            console.log("❌ Error al guardar preferencias:", data.message);
        }
    } catch (err) {
        console.error("❌ Error de red al guardar preferencias:", err);
    }
}

async function getUserPreferences() {
    if (!currentUser) {
        console.log('❌ getUserPreferences: No hay usuario logueado');
        return null;
    }
    
    console.log('🔍 Obteniendo preferencias para usuario:', currentUser.name);
    
    try {
        const token = localStorage.getItem('token');
        console.log('🔐 Token encontrado:', token ? 'SÍ' : 'NO');
        
        const res = await fetch('http://localhost:5000/preferences', {
            headers: {
                'Authorization': 'Bearer ' + token
            }
        });
        
        console.log('📡 Respuesta del servidor preferences:', res.status);
        
        const data = await res.json();
        console.log('📦 Datos completos de preferencias:', data);
        
        if (data.status === 'success' && data.preferences) {
            const parsedPrefs = typeof data.preferences === 'string' 
                ? JSON.parse(data.preferences) 
                : data.preferences;
            
            console.log('✅ Preferencias parseadas:', parsedPrefs);
            return parsedPrefs;
        } else {
            console.log('⚠️ No se encontraron preferencias o error:', data.message);
        }
    } catch (err) {
        console.error("❌ Error al obtener preferencias:", err);
    }
    return null;
}

function ordenarRestaurantesPorPreferencias(restaurants, preferences) {
    console.log('🧮 ==> INICIANDO ALGORITMO DE RECOMENDACIONES <==');
    console.log('📊 Restaurantes recibidos:', restaurants.length);
    console.log('🎯 Preferencias recibidas:', preferences);

    if (!preferences || !restaurants || restaurants.length === 0) {
        console.log('⚠️ Sin preferencias o restaurantes - retornando orden original');
        return restaurants;
    }

    function scoreRestaurant(restaurant) {
        let score = 0;
        let reasons = [];

        console.log(`\n🏪 Evaluando: ${restaurant.name}`);

        // 🐕 Pet Friendly
        if (preferences.pet_friendly && restaurant.features?.pet_friendly) {
            score += 15;
            reasons.push('🐕 Pet Friendly (+15)');
            console.log(`   ✅ Pet Friendly: ${restaurant.features.pet_friendly}`);
        } else if (preferences.pet_friendly) {
            console.log(`   ❌ No es Pet Friendly`);
        }

        // 📍 Zona
        if (preferences.zone && restaurant.zone) {
            const prefZone = preferences.zone.toLowerCase().trim();
            const restZone = restaurant.zone.toLowerCase().trim();
            console.log(`   🔍 Comparando zonas: "${prefZone}" vs "${restZone}"`);
            
            if (restZone.includes(prefZone) || prefZone.includes(restZone)) {
                score += 12;
                reasons.push(`📍 Zona coincide (+12)`);
                console.log(`   ✅ Zona coincide!`);
            } else {
                console.log(`   ❌ Zona no coincide`);
            }
        }

        // 💳 Métodos de pago
        if (preferences.payment_methods && restaurant.payment_methods) {
            const prefPayment = preferences.payment_methods.toLowerCase().trim();
            const restPayment = restaurant.payment_methods.toLowerCase().trim();
            console.log(`   🔍 Comparando pagos: "${prefPayment}" vs "${restPayment}"`);
            
            if (restPayment.includes(prefPayment)) {
                score += 8;
                reasons.push(`💳 Pago coincide (+8)`);
                console.log(`   ✅ Método de pago coincide!`);
            } else {
                console.log(`   ❌ Método de pago no coincide`);
            }
        }

        // 🥗 Opciones saludables
        if (preferences.healthy_options && restaurant.healthy_options) {
            const prefHealthy = preferences.healthy_options.toLowerCase().trim();
            const restHealthy = restaurant.healthy_options.toString().toLowerCase().trim();
            console.log(`   🔍 Comparando saludable: "${prefHealthy}" vs "${restHealthy}"`);
            
            if (restHealthy === prefHealthy) {
                score += 6;
                reasons.push(`🥗 Opciones saludables (+6)`);
                console.log(`   ✅ Opciones saludables coinciden!`);
            } else {
                console.log(`   ❌ Opciones saludables no coinciden`);
            }
        }

        // Características adicionales
        if (restaurant.features) {
            if (restaurant.features.reservations) {
                score += 2;
                reasons.push('📅 Acepta reservas (+2)');
            }
            if (restaurant.features.delivery) {
                score += 2;
                reasons.push('🚚 Delivery (+2)');
            }
            if (restaurant.features.promotions) {
                score += 3;
                reasons.push('🎯 Promociones (+3)');
            }
        }

        // ⭐ Bonificación por rating alto
        if (restaurant.rating) {
            const rating = parseFloat(restaurant.rating);
            if (rating >= 4.5) {
                score += 5;
                reasons.push(`⭐ Excelente rating: ${rating} (+5)`);
            } else if (rating >= 4.0) {
                score += 3;
                reasons.push(`⭐ Buen rating: ${rating} (+3)`);
            }
        }


        if (currentUser?.budget && restaurant.price_range) {
            const userBudget = parseFloat(currentUser.budget) || 1000;
            const restaurantPrice = parseFloat(restaurant.price_range.replace(/[^\d]/g, '')) || 0;
            
            if (userBudget !== 'unlimited' && restaurantPrice > 0) {
                if (restaurantPrice <= userBudget * 0.7) {
                    score += 4; // Muy dentro del presupuesto
                    reasons.push('💰 Muy accesible (+4)');
                } else if (restaurantPrice <= userBudget) {
                    score += 2; // Dentro del presupuesto
                    reasons.push('💰 Accesible (+2)');
                } else {
                    score -= 5; // Fuera del presupuesto
                    reasons.push('💸 Caro (-5)');
                }
            }
        }

        if (!restaurant.phone) score -= 1;
        if (!restaurant.address) score -= 1;

        console.log(`   📊 SCORE FINAL: ${score}`);
        if (reasons.length > 0) {
            console.log(`   🎯 RAZONES: ${reasons.join(', ')}`);
        }

        return score;
    }


    console.log('\n📊 ==> CALCULANDO SCORES PARA TODOS LOS RESTAURANTES <==');
    const restaurantsWithScores = restaurants.map(restaurant => ({
        ...restaurant,
        recomendationScore: scoreRestaurant(restaurant)
    }));


    const sorted = restaurantsWithScores.sort((a, b) => {
        if (b.recomendationScore !== a.recomendationScore) {
            return b.recomendationScore - a.recomendationScore;
        }
        return a.name.localeCompare(b.name);
    });


    const withPositiveScore = sorted.filter(r => r.recomendationScore > 0);
    const maxScore = Math.max(...sorted.map(r => r.recomendationScore));

    console.log('\n📈 ==> ESTADÍSTICAS FINALES <==');
    console.log(`🏆 Score máximo: ${maxScore}`);
    console.log(`✨ Restaurantes recomendados: ${withPositiveScore.length}/${restaurants.length}`);
    console.log('\n🥇 TOP 5 RECOMENDADOS:');
    sorted.slice(0, 5).forEach((r, i) => {
        console.log(`   ${i + 1}. ${r.name} (Score: ${r.recomendationScore})`);
    });

    console.log('\n✅ ==> ALGORITMO DE RECOMENDACIONES COMPLETADO <==');
    
    return sorted.map(({ recomendationScore, ...restaurant }) => restaurant);
}