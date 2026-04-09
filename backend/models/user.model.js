import mongoose from "mongoose";
import { type } from "os";

const userSchema = new mongoose.Schema({
    fullName: {
        type: String,
        required: true
    },
    email: {
        type: String,
        required: true,
        unique:true
    },
    password:{
        type: String,
    },
    mobile:{
        type: String,
        required: true, 
    },
    role:{
        type:String,
        enum:["user","owner","deliveryBoy","admin"],
        required:true
    },
    profileImage:{
        type: String,
        default: ""
    },
    contacts:[{
        name: { type: String, required: true },
        phone: { type: String, required: true }
    }],
    resetOtp:{
        type:String
    },
    isOtpVerified:{
        type:Boolean,
        default:false
    },
    otpExpires:{
        type:Date
    },
    socketId:{
     type:String,
     
    },
    isOnline:{
        type:Boolean,
        default:false
    },
   location:{
type:{type:String,enum:['Point'],default:'Point'},
coordinates:{type:[Number],default:[0,0]}
   },
    favorites: [{ type: mongoose.Schema.Types.ObjectId, ref: 'Item' }],
    // ── AI-Layer: Churn Prediction fields ──
   ordersLast30d: { type: Number, default: 0 },
   ordersLast90d: { type: Number, default: 0 },
   avgOrderValue: { type: Number, default: 0 },
   daysSinceLastOrder: { type: Number, default: 0 },
   orderFrequency: { type: Number, default: 0 },
   cancellationRate: { type: Number, default: 0 },
   avgDeliveryDelayMin: { type: Number, default: 0 },
   avgUserRating: { type: Number, default: 4.0 },
   numComplaints: { type: Number, default: 0 },
   discountUsageRate: { type: Number, default: 0 },
   appSessionsPerWeek: { type: Number, default: 0 },
   preferredOrderHour: { type: Number, default: 12 },
   // ── AI-Layer: Churn result cache ──
   churnRisk: { type: String, enum: ["low", "medium", "high", null], default: null },
   churnProbability: { type: Number, default: 0 },
   lastChurnCheck: { type: Date, default: null }
  
}, { timestamps: true })

userSchema.index({location:'2dsphere'})


const User=mongoose.model("User",userSchema)
export default User