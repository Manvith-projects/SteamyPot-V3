import mongoose from "mongoose"

const connectDb=async () => {
    try {
        await mongoose.connect(process.env.MONGODB_URL, {
            serverSelectionTimeoutMS: 15000,
            socketTimeoutMS: 30000,
            connectTimeoutMS: 15000,
            maxPoolSize: 10,
            minPoolSize: 2,
        })
        console.log("db connected")
    } catch (error) {
        console.log("db error:", error.message)
    }
}

export default connectDb