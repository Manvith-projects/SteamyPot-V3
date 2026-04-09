import express from "express";
import { isAuth } from "../middlewares/isAuth.js";
import {
    isAdmin,
    getDashboardStats,
    getPendingShops,
    getAllShops,
    approveShop,
    rejectShop,
    getAllTickets,
    updateTicketStatus,
    createTicket,
    getAllRiders,
    getRiderAssignments,
    assignRiderToOrder,
    getUnassignedOrders
} from "../controllers/admin.controllers.js";

const adminRouter = express.Router();

// Dashboard
adminRouter.get("/stats", isAuth, isAdmin, getDashboardStats);

// Shop approval
adminRouter.get("/shops/pending", isAuth, isAdmin, getPendingShops);
adminRouter.get("/shops/all", isAuth, isAdmin, getAllShops);
adminRouter.put("/shops/approve/:shopId", isAuth, isAdmin, approveShop);
adminRouter.put("/shops/reject/:shopId", isAuth, isAdmin, rejectShop);

// Support tickets
adminRouter.get("/tickets", isAuth, isAdmin, getAllTickets);
adminRouter.put("/tickets/:ticketId", isAuth, isAdmin, updateTicketStatus);
adminRouter.post("/tickets", isAuth, createTicket); // owners/riders create tickets

// Rider management
adminRouter.get("/riders", isAuth, isAdmin, getAllRiders);
adminRouter.get("/riders/:riderId/assignments", isAuth, isAdmin, getRiderAssignments);
adminRouter.post("/riders/assign", isAuth, isAdmin, assignRiderToOrder);
adminRouter.get("/orders/unassigned", isAuth, isAdmin, getUnassignedOrders);

export default adminRouter;
