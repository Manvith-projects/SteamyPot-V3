import Item from "../models/item.model.js"
import Shop from "../models/shop.model.js"
import User from "../models/user.model.js"
import Order from "../models/order.model.js"

const AI_LAYER_URL = process.env.AI_LAYER_URL || "http://localhost:9001"

export const getRecommendations = async (req, res) => {
    try {
        // AI-Layer recommendation uses integer user_ids from its CSV dataset;
        // MongoDB ObjectIds are not valid — use popularity strategy as fallback.
        const aiResponse = await fetch(
            `${AI_LAYER_URL}/api/recommend/0?strategy=popularity&k=10`
        )

        if (!aiResponse.ok) {
            throw new Error(`AI-Layer responded with ${aiResponse.status}`)
        }

        const { recommendations: shopIds, strategy } = await aiResponse.json()

        if (!shopIds || shopIds.length === 0) {
            return res.status(200).json({ items: [], strategy: "none" })
        }

        // Fetch top-rated items from the recommended shops
        const items = await Item.find({ shop: { $in: shopIds } })
            .sort({ "rating.average": -1, "rating.count": -1 })
            .limit(20)
            .populate("shop", "name image")

        return res.status(200).json({ items, strategy })
    } catch (error) {
        console.log("Recommendation error:", error.message)
        // Graceful fallback: return empty instead of 500
        return res.status(200).json({ items: [], strategy: "error" })
    }
}

export const getContactRecommendations = async (req, res) => {
    try {
        const user = await User.findById(req.userId)
        if (!user || !user.contacts || user.contacts.length === 0) {
            return res.status(200).json({ items: [], contactsUsed: 0 })
        }

        // Find users whose phone matches the current user's contacts
        const contactPhones = user.contacts.map(c => c.phone)
        const contactUsers = await User.find({
            mobile: { $in: contactPhones },
            _id: { $ne: req.userId }
        }).select("_id fullName")

        if (contactUsers.length === 0) {
            return res.status(200).json({ items: [], contactsUsed: 0 })
        }

        const contactUserIds = contactUsers.map(u => u._id)

        // Get recent orders from contacts
        const contactOrders = await Order.find({
            user: { $in: contactUserIds }
        }).sort({ createdAt: -1 }).limit(50)

        // Collect item IDs ordered by contacts
        const itemIdSet = new Set()
        for (const order of contactOrders) {
            for (const so of order.shopOrders || []) {
                for (const si of so.shopOrderItems || []) {
                    itemIdSet.add(si.item.toString())
                }
            }
        }

        if (itemIdSet.size === 0) {
            return res.status(200).json({ items: [], contactsUsed: contactUsers.length })
        }

        const items = await Item.find({ _id: { $in: [...itemIdSet] } })
            .sort({ "rating.average": -1 })
            .limit(12)
            .populate("shop", "name image")

        return res.status(200).json({
            items,
            contactsUsed: contactUsers.length,
            contactNames: contactUsers.map(u => u.fullName)
        })
    } catch (error) {
        console.log("Contact recommendation error:", error.message)
        return res.status(200).json({ items: [], contactsUsed: 0 })
    }
}

export const refreshRecommendations = async (req, res) => {
    try {
        const aiResponse = await fetch(`${AI_LAYER_URL}/api/recommend/refresh`, {
            method: "POST",
        })
        const data = await aiResponse.json()
        return res.status(200).json(data)
    } catch (error) {
        console.log("Refresh recommendations error:", error.message)
        return res.status(500).json({ message: "Failed to refresh recommendations" })
    }
}
