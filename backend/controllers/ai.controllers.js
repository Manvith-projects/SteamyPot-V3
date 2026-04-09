import User from "../models/user.model.js"
import Shop from "../models/shop.model.js"
import Item from "../models/item.model.js"
import Order from "../models/order.model.js"

const AI_LAYER_URL = process.env.AI_LAYER_URL || "http://localhost:9001"
const AI_TIMEOUT_MS = 8000 // 8s timeout for AI calls
const FOOD_AI_TIMEOUT_MS = 30000 // Food assistant can take longer due LLM parsing

function aiAbort(timeoutMs = AI_TIMEOUT_MS) {
    return AbortSignal.timeout(timeoutMs)
}

// ─── ETA Prediction ────────────────────────────────────────────────
export const predictETA = async (req, res) => {
    try {
        const {
            restaurant_lat, restaurant_lon,
            customer_lat, customer_lon,
            order_hour, day_of_week,
            weather, traffic_level,
            prep_time_min, rider_availability,
            order_size, historical_avg_delivery_min
        } = req.body

        const now = new Date()
        const aiResponse = await fetch(`${AI_LAYER_URL}/api/eta/predict`, {
            signal: aiAbort(),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                restaurant_lat: restaurant_lat || 17.4486,
                restaurant_lon: restaurant_lon || 78.3908,
                customer_lat: customer_lat || 17.4400,
                customer_lon: customer_lon || 78.3489,
                order_hour: order_hour ?? now.getHours(),
                day_of_week: day_of_week ?? now.getDay(),
                weather: weather || "Clear",
                traffic_level: traffic_level || "Medium",
                prep_time_min: prep_time_min || 15,
                rider_availability: rider_availability || "Medium",
                order_size: order_size || "Medium",
                historical_avg_delivery_min: historical_avg_delivery_min || 35
            })
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer ETA responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("ETA prediction error:", error.message)
        return res.status(200).json({
            predicted_time: 35,
            confidence_score: 0.5,
            unit: "minutes",
            model_used: "fallback"
        })
    }
}

// ─── Dynamic Pricing ───────────────────────────────────────────────
export const calculatePricing = async (req, res) => {
    try {
        const {
            hour, day_of_week, is_holiday, weather,
            traffic_level, active_orders, available_riders,
            avg_prep_time_min, zone_id, distance_km,
            hist_demand_trend, hist_cancel_rate, base_delivery_fee
        } = req.body

        const now = new Date()
        // Calculate defaults based on time of day for realistic pricing
        const hour_now = now.getHours()
        const is_peak = (hour_now >= 12 && hour_now <= 14) || (hour_now >= 19 && hour_now <= 21)
        const demand_multiplier = is_peak ? 1.2 : 0.8
        
        const aiResponse = await fetch(`${AI_LAYER_URL}/api/pricing/calculate`, {
            signal: aiAbort(),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                hour: hour ?? hour_now,
                day_of_week: day_of_week ?? now.getDay(),
                is_holiday: is_holiday ?? 0,
                weather: weather || "Clear",
                traffic_level: traffic_level ?? 2,
                active_orders: Math.ceil((active_orders ?? 30) * demand_multiplier),
                available_riders: Math.ceil((available_riders ?? 15) / demand_multiplier),
                avg_prep_time_min: avg_prep_time_min ?? 18,
                zone_id: zone_id ?? 3,
                distance_km: distance_km ?? 4.5,
                hist_demand_trend: hist_demand_trend ?? (is_peak ? 1.3 : 0.9),
                hist_cancel_rate: hist_cancel_rate ?? 0.08,
                base_delivery_fee: base_delivery_fee ?? 45
            })
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer pricing responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("Dynamic pricing error:", error.message)
        return res.status(200).json({
            surge_multiplier: 1.0,
            final_delivery_fee: 40,
            recommended_discount: 0,
            pricing_reason: "Standard delivery fee (AI unavailable)",
            is_peak_hour: false
        })
    }
}

// ─── Churn Prediction ──────────────────────────────────────────────
export const predictChurn = async (req, res) => {
    try {
        const userId = req.userId
        const user = await User.findById(userId)
        if (!user) return res.status(404).json({ message: "User not found" })

        // Compute churn features from user's order history
        const now = new Date()
        const thirtyDaysAgo = new Date(now - 30 * 24 * 60 * 60 * 1000)
        const ninetyDaysAgo = new Date(now - 90 * 24 * 60 * 60 * 1000)

        const allOrders = await Order.find({ user: userId }).sort({ createdAt: -1 })
        const ordersLast30d = allOrders.filter(o => o.createdAt >= thirtyDaysAgo).length
        const ordersLast90d = allOrders.filter(o => o.createdAt >= ninetyDaysAgo).length
        const avgOrderValue = allOrders.length > 0
            ? allOrders.reduce((sum, o) => sum + (o.totalAmount || 0), 0) / allOrders.length : 0
        const daysSinceLastOrder = allOrders.length > 0
            ? Math.floor((now - allOrders[0].createdAt) / (24 * 60 * 60 * 1000)) : 999
        const orderFrequency = allOrders.length > 0
            ? allOrders.length / Math.max(1, Math.floor((now - allOrders[allOrders.length - 1].createdAt) / (7 * 24 * 60 * 60 * 1000))) : 0
        const accountAgeDays = Math.floor((now - user.createdAt) / (24 * 60 * 60 * 1000))

        const churnPayload = {
            orders_last_30d: ordersLast30d,
            orders_last_90d: ordersLast90d,
            avg_order_value: avgOrderValue,
            days_since_last_order: daysSinceLastOrder,
            order_frequency: orderFrequency,
            cancellation_rate: user.cancellationRate || 0,
            avg_delivery_delay_min: user.avgDeliveryDelayMin || 0,
            avg_user_rating: user.avgUserRating || 4.0,
            num_complaints: user.numComplaints || 0,
            discount_usage_rate: user.discountUsageRate || 0,
            app_sessions_per_week: user.appSessionsPerWeek || 5,
            preferred_order_hour: user.preferredOrderHour || 12,
            account_age_days: accountAgeDays
        }

        const aiResponse = await fetch(`${AI_LAYER_URL}/api/churn/predict`, {
            signal: aiAbort(),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(churnPayload)
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer churn responded ${aiResponse.status}`)
        const data = await aiResponse.json()

        // Cache churn result on user
        user.churnRisk = data.risk_level
        user.churnProbability = data.churn_probability
        user.lastChurnCheck = now
        user.ordersLast30d = ordersLast30d
        user.ordersLast90d = ordersLast90d
        user.avgOrderValue = avgOrderValue
        user.daysSinceLastOrder = daysSinceLastOrder
        user.orderFrequency = orderFrequency
        await user.save()

        return res.status(200).json(data)
    } catch (error) {
        console.log("Churn prediction error:", error.message)
        return res.status(200).json({
            churn_probability: 0,
            risk_level: "low",
            recommended_action: "Continue engagement",
            features_used: 0
        })
    }
}

// ─── Food Assistant ────────────────────────────────────────────────
export const foodAssistant = async (req, res) => {
    try {
        const { query, user_lat, user_lon } = req.body

        const aiResponse = await fetch(`${AI_LAYER_URL}/api/food/assistant`, {
            signal: aiAbort(FOOD_AI_TIMEOUT_MS),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                query: query || "",
                user_lat: user_lat || 17.4486,
                user_lon: user_lon || 78.3908
            })
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer food responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("Food assistant error:", error.message)
        return res.status(200).json({
            message: "Sorry, the AI assistant is temporarily unavailable. Please try searching manually.",
            intent: "error",
            results: [],
            total_candidates: 0
        })
    }
}

// ─── Review Summarizer ─────────────────────────────────────────────
export const summarizeReviews = async (req, res) => {
    try {
        let { restaurant_id, max_reviews } = req.body
        
        // If no restaurant_id provided, use a default known restaurant ID
        // This handles UI calls that may not have been updated with proper restaurant ID
        if (!restaurant_id || restaurant_id === "") {
            // Query database for an existing restaurant with reviews
            try {
                const shop = await Shop.findOne().select('_id').lean()
                if (shop && shop._id) {
                    restaurant_id = shop._id.toString()
                } else {
                    // Return graceful fallback if no restaurants exist
                    return res.status(200).json({
                        summary: "No restaurants with reviews available yet.",
                        top_positive_points: [],
                        common_complaints: [],
                        overall_sentiment: "unknown",
                        reviews_analyzed: 0
                    })
                }
            } catch (dbError) {
                console.log("Database lookup failed for restaurant:", dbError.message)
                return res.status(200).json({
                    summary: "Unable to fetch reviews at this time.",
                    top_positive_points: [],
                    common_complaints: [],
                    overall_sentiment: "unknown",
                    reviews_analyzed: 0
                })
            }
        }

        const aiResponse = await fetch(`${AI_LAYER_URL}/api/review/summarize`, {
            signal: AbortSignal.timeout(60000),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                restaurant_id: restaurant_id,
                max_reviews: max_reviews || 200
            })
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer review responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("Review summarizer error:", error.message)
        return res.status(200).json({
            summary: "Review summary is temporarily unavailable.",
            top_positive_points: [],
            common_complaints: [],
            overall_sentiment: "unknown",
            reviews_analyzed: 0
        })
    }
}

// ─── Get Review Restaurants ────────────────────────────────────────
export const getReviewRestaurants = async (req, res) => {
    try {
        const aiResponse = await fetch(`${AI_LAYER_URL}/api/review/restaurants`, { signal: aiAbort() })
        if (!aiResponse.ok) throw new Error(`AI-Layer review restaurants responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("Review restaurants error:", error.message)
        return res.status(200).json([])
    }
}

// ─── Driver Allocation ─────────────────────────────────────────────
export const allocateDriver = async (req, res) => {
    try {
        const { restaurant_location, customer_location, estimated_prep_time, order_size } = req.body

        const aiResponse = await fetch(`${AI_LAYER_URL}/api/driver/allocate`, {
            signal: aiAbort(),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                restaurant_location: restaurant_location || { lat: 17.4486, lon: 78.3908 },
                customer_location: customer_location || { lat: 17.44, lon: 78.35 },
                estimated_prep_time: estimated_prep_time || 15,
                order_size: order_size || 2
            })
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer driver responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("Driver allocation error:", error.message)
        return res.status(200).json({
            selected_driver: null,
            allocation_reason: "AI driver allocation unavailable, using proximity-based fallback"
        })
    }
}

// ─── Route Optimization ────────────────────────────────────────────
export const optimiseRoute = async (req, res) => {
    try {
        const { rider_lat, rider_lon, deliveries } = req.body

        const aiResponse = await fetch(`${AI_LAYER_URL}/api/eta/optimise-route`, {
            signal: aiAbort(),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                rider_lat: rider_lat || 17.4486,
                rider_lon: rider_lon || 78.3908,
                deliveries: deliveries || []
            })
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer route responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("Route optimization error:", error.message)
        return res.status(200).json({
            optimised_order: [],
            total_distance_km: 0,
            savings_pct: 0,
            method: "fallback"
        })
    }
}

// ─── Recovery Agent ────────────────────────────────────────────────
export const triggerRecovery = async (req, res) => {
    try {
        const { event_type, order_id, details } = req.body

        const aiResponse = await fetch(`${AI_LAYER_URL}/api/recovery/agent`, {
            signal: aiAbort(),
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                event_type: event_type || "delivery_delay",
                order_id: order_id || "",
                details: details || {}
            })
        })

        if (!aiResponse.ok) throw new Error(`AI-Layer recovery responded ${aiResponse.status}`)
        const data = await aiResponse.json()

        // Save recovery action to the order if we have an order_id
        if (order_id) {
            try {
                await Order.findByIdAndUpdate(order_id, {
                    recoveryAction: data.action_taken || null,
                    recoveryCoupon: data.coupon_applied || null
                })
            } catch (e) { /* order might not match MongoDB ID format */ }
        }

        return res.status(200).json(data)
    } catch (error) {
        console.log("Recovery agent error:", error.message)
        return res.status(200).json({
            action_taken: "Recovery agent unavailable",
            severity: "unknown"
        })
    }
}

// ─── AI Health Check ───────────────────────────────────────────────
export const aiHealth = async (req, res) => {
    try {
        const aiResponse = await fetch(`${AI_LAYER_URL}/health`, { signal: aiAbort() })
        if (!aiResponse.ok) throw new Error(`AI-Layer health responded ${aiResponse.status}`)
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        return res.status(200).json({
            status: "offline",
            error: error.message
        })
    }
}
