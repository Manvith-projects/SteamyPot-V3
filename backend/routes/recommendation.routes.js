import express from "express"
import { isAuth } from "../middlewares/isAuth.js"
import { getRecommendations, getContactRecommendations, refreshRecommendations } from "../controllers/recommendation.controllers.js"

const recommendationRouter = express.Router()

recommendationRouter.get("/", isAuth, getRecommendations)
recommendationRouter.get("/contacts", isAuth, getContactRecommendations)
recommendationRouter.post("/refresh", isAuth, refreshRecommendations)

export default recommendationRouter
