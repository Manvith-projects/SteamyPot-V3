import mongoose from "mongoose";

const deliveryAssignmentSchema = new mongoose.Schema({
    order: {
        type: mongoose.Schema.Types.ObjectId,
        ref: "Order"
    },
    shop: {
        type: mongoose.Schema.Types.ObjectId,
        ref: "Shop"
    },
    shopOrderId:{
         type: mongoose.Schema.Types.ObjectId,
         required:true
    },
    brodcastedTo:[
        {
         type: mongoose.Schema.Types.ObjectId,
         ref:"User"
    }
    ],
    assignedTo:{
        type: mongoose.Schema.Types.ObjectId,
         ref:"User",
         default:null
    },
    status:{
        type:String,
        enum:["brodcasted","assigned","completed"],
        default:"brodcasted"
    },
    acceptedAt:Date,
    // ── AI-Layer: Driver Allocation fields ──
    aiAllocatedDriver: { type: String, default: null },
    aiOptimizationScore: { type: Number, default: null },
    aiAllocationReason: { type: String, default: null },
    predictedDeliveryTime: { type: String, default: null },
    // ── AI-Layer: Route Optimization ──
    optimisedRoute: [{ lat: Number, lon: Number }],
    routeSavingsPct: { type: Number, default: null }
}, { timestamps: true })

const DeliveryAssignment=mongoose.model("DeliveryAssignment",deliveryAssignmentSchema)
export default DeliveryAssignment