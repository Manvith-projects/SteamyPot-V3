import express from "express";
import { isAuth } from "../middlewares/isAuth.js";
import {
    createCoupon,
    getCoupons,
    applyCoupon,
    redeemCoupon,
    updateCoupon,
    deleteCoupon
} from "../controllers/coupon.controllers.js";

const couponRouter = express.Router();

couponRouter.post("/create", isAuth, createCoupon);
couponRouter.get("/all", isAuth, getCoupons);
couponRouter.post("/apply", isAuth, applyCoupon);
couponRouter.post("/redeem", isAuth, redeemCoupon);
couponRouter.put("/update/:id", isAuth, updateCoupon);
couponRouter.delete("/delete/:id", isAuth, deleteCoupon);

export default couponRouter;
