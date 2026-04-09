import Coupon from "../models/coupon.model.js";
import User from "../models/user.model.js";

// Create a new coupon (admin/owner only)
export const createCoupon = async (req, res) => {
    try {
        const user = await User.findById(req.userId);
        if (!user || !["admin", "owner"].includes(user.role)) {
            return res.status(403).json({ message: "Only admins and owners can create coupons" });
        }

        const {
            code, description, discountType, discountValue,
            minOrderAmount, maxDiscount, validFrom, validUntil,
            usageLimit, perUserLimit, applicableShops, applicableCategories
        } = req.body;

        if (!code || !discountType || discountValue === undefined || !validUntil) {
            return res.status(400).json({ message: "code, discountType, discountValue, validUntil are required" });
        }

        const existing = await Coupon.findOne({ code: code.toUpperCase() });
        if (existing) {
            return res.status(400).json({ message: "Coupon code already exists" });
        }

        const coupon = await Coupon.create({
            code: code.toUpperCase(),
            description,
            discountType,
            discountValue,
            minOrderAmount: minOrderAmount || 0,
            maxDiscount: maxDiscount || null,
            validFrom: validFrom || new Date(),
            validUntil: new Date(validUntil),
            usageLimit: usageLimit || null,
            perUserLimit: perUserLimit || 1,
            applicableShops: applicableShops || [],
            applicableCategories: applicableCategories || [],
            createdBy: req.userId
        });

        return res.status(201).json(coupon);
    } catch (error) {
        return res.status(500).json({ message: `Create coupon error: ${error.message}` });
    }
};

// Get all active coupons (users see active ones; admin/owner see all)
export const getCoupons = async (req, res) => {
    try {
        const user = await User.findById(req.userId);
        let filter = {};

        if (!user || !["admin", "owner"].includes(user.role)) {
            filter = { isActive: true, validUntil: { $gte: new Date() } };
        }

        const coupons = await Coupon.find(filter)
            .populate("applicableShops", "name")
            .populate("createdBy", "fullName email")
            .sort({ createdAt: -1 });

        return res.status(200).json(coupons);
    } catch (error) {
        return res.status(500).json({ message: `Get coupons error: ${error.message}` });
    }
};

// Validate and apply a coupon
export const applyCoupon = async (req, res) => {
    try {
        const { code, orderAmount, shopId } = req.body;
        if (!code) return res.status(400).json({ message: "Coupon code is required" });

        const coupon = await Coupon.findOne({ code: code.toUpperCase(), isActive: true });
        if (!coupon) return res.status(404).json({ message: "Invalid coupon code" });

        const now = new Date();
        if (now < coupon.validFrom || now > coupon.validUntil) {
            return res.status(400).json({ message: "Coupon has expired or is not yet active" });
        }

        if (coupon.usageLimit && coupon.usedCount >= coupon.usageLimit) {
            return res.status(400).json({ message: "Coupon usage limit reached" });
        }

        const userUses = coupon.usedBy.filter(u => u.user.toString() === req.userId).length;
        if (userUses >= coupon.perUserLimit) {
            return res.status(400).json({ message: "You have already used this coupon" });
        }

        if (orderAmount && coupon.minOrderAmount > 0 && orderAmount < coupon.minOrderAmount) {
            return res.status(400).json({ message: `Minimum order amount is ₹${coupon.minOrderAmount}` });
        }

        if (shopId && coupon.applicableShops.length > 0) {
            const applicable = coupon.applicableShops.map(s => s.toString());
            if (!applicable.includes(shopId)) {
                return res.status(400).json({ message: "Coupon not valid for this shop" });
            }
        }

        let discount = 0;
        if (coupon.discountType === "percentage") {
            discount = (orderAmount || 0) * (coupon.discountValue / 100);
            if (coupon.maxDiscount && discount > coupon.maxDiscount) {
                discount = coupon.maxDiscount;
            }
        } else {
            discount = coupon.discountValue;
        }

        return res.status(200).json({
            valid: true,
            code: coupon.code,
            discount: Math.round(discount * 100) / 100,
            discountType: coupon.discountType,
            discountValue: coupon.discountValue,
            description: coupon.description
        });
    } catch (error) {
        return res.status(500).json({ message: `Apply coupon error: ${error.message}` });
    }
};

// Redeem a coupon (mark as used after order placement)
export const redeemCoupon = async (req, res) => {
    try {
        const { code } = req.body;
        if (!code) return res.status(400).json({ message: "Coupon code is required" });

        const coupon = await Coupon.findOne({ code: code.toUpperCase(), isActive: true });
        if (!coupon) return res.status(404).json({ message: "Invalid coupon code" });

        coupon.usedCount += 1;
        coupon.usedBy.push({ user: req.userId, usedAt: new Date() });
        await coupon.save();

        return res.status(200).json({ message: "Coupon redeemed successfully" });
    } catch (error) {
        return res.status(500).json({ message: `Redeem coupon error: ${error.message}` });
    }
};

// Update coupon (admin/owner)
export const updateCoupon = async (req, res) => {
    try {
        const user = await User.findById(req.userId);
        if (!user || !["admin", "owner"].includes(user.role)) {
            return res.status(403).json({ message: "Only admins and owners can update coupons" });
        }

        const coupon = await Coupon.findByIdAndUpdate(req.params.id, req.body, { new: true });
        if (!coupon) return res.status(404).json({ message: "Coupon not found" });

        return res.status(200).json(coupon);
    } catch (error) {
        return res.status(500).json({ message: `Update coupon error: ${error.message}` });
    }
};

// Delete coupon (admin only)
export const deleteCoupon = async (req, res) => {
    try {
        const user = await User.findById(req.userId);
        if (!user || user.role !== "admin") {
            return res.status(403).json({ message: "Only admins can delete coupons" });
        }

        const coupon = await Coupon.findByIdAndDelete(req.params.id);
        if (!coupon) return res.status(404).json({ message: "Coupon not found" });

        return res.status(200).json({ message: "Coupon deleted" });
    } catch (error) {
        return res.status(500).json({ message: `Delete coupon error: ${error.message}` });
    }
};
