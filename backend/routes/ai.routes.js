import express from "express"
import { isAuth } from "../middlewares/isAuth.js"
import {
    predictETA,
    calculatePricing,
    predictChurn,
    foodAssistant,
    summarizeReviews,
    getReviewRestaurants,
    allocateDriver,
    optimiseRoute,
    triggerRecovery,
    aiHealth
} from "../controllers/ai.controllers.js"

const aiRouter = express.Router()

// ETA Prediction
aiRouter.post("/eta/predict", isAuth, predictETA)

// Dynamic Pricing
aiRouter.post("/pricing/calculate", isAuth, calculatePricing)

// Churn Prediction (computes features from user's order history)
aiRouter.get("/churn/predict", isAuth, predictChurn)

// Food Assistant (natural language food search)
aiRouter.post("/food/assistant", isAuth, foodAssistant)

// Review Summarizer
aiRouter.post("/review/summarize", isAuth, summarizeReviews)
aiRouter.get("/review/restaurants", isAuth, getReviewRestaurants)

// Driver Allocation
aiRouter.post("/driver/allocate", isAuth, allocateDriver)

// Route Optimization
aiRouter.post("/eta/optimise-route", isAuth, optimiseRoute)

// Recovery Agent
aiRouter.post("/recovery/agent", isAuth, triggerRecovery)

// Health Check
aiRouter.get("/health", aiHealth)

export default aiRouter
