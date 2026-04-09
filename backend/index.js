import express from "express"
import dotenv from "dotenv"
import path from "path"
import { fileURLToPath } from "url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
dotenv.config({ path: path.join(__dirname, ".env") })

import connectDb from "./config/db.js"
import cookieParser from "cookie-parser"
import authRouter from "./routes/auth.routes.js"
import cors from "cors"
import userRouter from "./routes/user.routes.js"

import itemRouter from "./routes/item.routes.js"
import shopRouter from "./routes/shop.routes.js"
import orderRouter from "./routes/order.routes.js"
import recommendationRouter from "./routes/recommendation.routes.js"
import aiRouter from "./routes/ai.routes.js"
import couponRouter from "./routes/coupon.routes.js"
import adminRouter from "./routes/admin.routes.js"
import http from "http"
import { Server } from "socket.io"
import { socketHandler } from "./socket.js"

const app=express()
const server=http.createServer(app)

const enableNgrokTesting = process.env.ENABLE_NGROK_TESTING === "true"
const defaultOrigins = ["http://localhost:5173", "http://localhost:5174"]
const configuredOrigins = (process.env.CORS_ORIGINS || "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean)

const allowedOrigins = configuredOrigins.length > 0 ? configuredOrigins : defaultOrigins
const ngrokOriginRegex = /^https:\/\/[a-zA-Z0-9-]+\.(ngrok-free\.(app|dev)|ngrok\.io)$/

const allowOrigin = (origin, callback) => {
    if (!origin) {
        callback(null, true)
        return
    }

    if (allowedOrigins.includes(origin)) {
        callback(null, true)
        return
    }

    if (enableNgrokTesting && ngrokOriginRegex.test(origin)) {
        callback(null, true)
        return
    }

    callback(new Error(`CORS blocked for origin: ${origin}`), false)
}

const io=new Server(server,{
   cors:{
        origin: allowOrigin,
    credentials:true,
    methods:['POST','GET']
}
})
app.set("io",io)



const port=process.env.PORT || 5000
app.use(cors({
    origin: allowOrigin,
    credentials: true
}))
app.use(express.json())
app.use(cookieParser())
app.use("/api/auth",authRouter)
app.use("/api/user",userRouter)
app.use("/api/shop",shopRouter)
app.use("/api/item",itemRouter)
app.use("/api/order",orderRouter)
app.use("/api/recommendations",recommendationRouter)
app.use("/api/ai",aiRouter)
app.use("/api/coupon",couponRouter)
app.use("/api/admin",adminRouter)

app.get("/", (req, res) => {
    res.status(200).json({
        service: "fd-backend",
        status: "ok",
        docs_hint: "Use /api/* routes",
    })
})

app.get("/health", (req, res) => {
    res.status(200).json({ status: "ok" })
})

socketHandler(io)
server.listen(port,()=>{
    connectDb()
    console.log(`server started at ${port}`)
})

