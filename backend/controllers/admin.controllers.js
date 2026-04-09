import Shop from "../models/shop.model.js";
import User from "../models/user.model.js";
import Order from "../models/order.model.js";
import SupportTicket from "../models/supportTicket.model.js";
import DeliveryAssignment from "../models/deliveryAssignment.model.js";

// ─── Middleware: ensure user is admin ───
export const isAdmin = async (req, res, next) => {
    try {
        const user = await User.findById(req.userId);
        if (!user || user.role !== "admin") {
            return res.status(403).json({ message: "Admin access required" });
        }
        next();
    } catch (error) {
        return res.status(500).json({ message: `isAdmin error: ${error}` });
    }
};

// ─── Dashboard Stats ───
export const getDashboardStats = async (req, res) => {
    try {
        const [totalUsers, totalOwners, totalRiders, totalShops, pendingShops, totalOrders, openTickets] = await Promise.all([
            User.countDocuments({ role: "user" }),
            User.countDocuments({ role: "owner" }),
            User.countDocuments({ role: "deliveryBoy" }),
            Shop.countDocuments(),
            Shop.countDocuments({ isApproved: "pending" }),
            Order.countDocuments(),
            SupportTicket.countDocuments({ status: { $in: ["open", "in-progress"] } })
        ]);
        return res.status(200).json({ totalUsers, totalOwners, totalRiders, totalShops, pendingShops, totalOrders, openTickets });
    } catch (error) {
        return res.status(500).json({ message: `getDashboardStats error: ${error}` });
    }
};

// ─── Shop Approval ───
export const getPendingShops = async (req, res) => {
    try {
        const shops = await Shop.find({ isApproved: "pending" }).populate("owner", "fullName email mobile");
        return res.status(200).json(shops);
    } catch (error) {
        return res.status(500).json({ message: `getPendingShops error: ${error}` });
    }
};

export const getAllShops = async (req, res) => {
    try {
        const shops = await Shop.find().populate("owner", "fullName email mobile");
        return res.status(200).json(shops);
    } catch (error) {
        return res.status(500).json({ message: `getAllShops error: ${error}` });
    }
};

export const approveShop = async (req, res) => {
    try {
        const shop = await Shop.findByIdAndUpdate(req.params.shopId, { isApproved: "approved", rejectionReason: "" }, { new: true }).populate("owner", "fullName email mobile");
        if (!shop) return res.status(404).json({ message: "Shop not found" });
        return res.status(200).json(shop);
    } catch (error) {
        return res.status(500).json({ message: `approveShop error: ${error}` });
    }
};

export const rejectShop = async (req, res) => {
    try {
        const { reason } = req.body;
        const shop = await Shop.findByIdAndUpdate(req.params.shopId, { isApproved: "rejected", rejectionReason: reason || "Rejected by admin" }, { new: true }).populate("owner", "fullName email mobile");
        if (!shop) return res.status(404).json({ message: "Shop not found" });
        return res.status(200).json(shop);
    } catch (error) {
        return res.status(500).json({ message: `rejectShop error: ${error}` });
    }
};

// ─── Support Tickets ───
export const getAllTickets = async (req, res) => {
    try {
        const tickets = await SupportTicket.find().populate("raisedBy", "fullName email mobile role").populate("shop", "name city").populate("resolvedBy", "fullName").sort({ createdAt: -1 });
        return res.status(200).json(tickets);
    } catch (error) {
        return res.status(500).json({ message: `getAllTickets error: ${error}` });
    }
};

export const updateTicketStatus = async (req, res) => {
    try {
        const { status, adminNote } = req.body;
        const update = { status };
        if (adminNote) update.adminNote = adminNote;
        if (status === "resolved" || status === "closed") update.resolvedBy = req.userId;
        const ticket = await SupportTicket.findByIdAndUpdate(req.params.ticketId, update, { new: true }).populate("raisedBy", "fullName email mobile role").populate("shop", "name city").populate("resolvedBy", "fullName");
        if (!ticket) return res.status(404).json({ message: "Ticket not found" });
        return res.status(200).json(ticket);
    } catch (error) {
        return res.status(500).json({ message: `updateTicketStatus error: ${error}` });
    }
};

// Create ticket (for owners/riders)
export const createTicket = async (req, res) => {
    try {
        const user = await User.findById(req.userId);
        if (!user || !["owner", "deliveryBoy"].includes(user.role)) {
            return res.status(403).json({ message: "Only owners and riders can create tickets" });
        }
        const { subject, description, shopId } = req.body;
        const ticket = await SupportTicket.create({
            raisedBy: req.userId,
            role: user.role,
            shop: shopId || null,
            subject,
            description
        });
        await ticket.populate("raisedBy", "fullName email mobile role");
        return res.status(201).json(ticket);
    } catch (error) {
        return res.status(500).json({ message: `createTicket error: ${error}` });
    }
};

// ─── Rider Management / Mapping ───
export const getAllRiders = async (req, res) => {
    try {
        const riders = await User.find({ role: "deliveryBoy" }).select("fullName email mobile isOnline location");
        return res.status(200).json(riders);
    } catch (error) {
        return res.status(500).json({ message: `getAllRiders error: ${error}` });
    }
};

export const getRiderAssignments = async (req, res) => {
    try {
        const assignments = await DeliveryAssignment.find({ assignedTo: req.params.riderId }).populate("order").populate("shop", "name city address").sort({ createdAt: -1 }).limit(20);
        return res.status(200).json(assignments);
    } catch (error) {
        return res.status(500).json({ message: `getRiderAssignments error: ${error}` });
    }
};

export const assignRiderToOrder = async (req, res) => {
    try {
        const { assignmentId, riderId } = req.body;
        const assignment = await DeliveryAssignment.findByIdAndUpdate(assignmentId, { assignedTo: riderId, status: "assigned", acceptedAt: new Date() }, { new: true }).populate("order").populate("shop", "name city address");
        if (!assignment) return res.status(404).json({ message: "Assignment not found" });
        return res.status(200).json(assignment);
    } catch (error) {
        return res.status(500).json({ message: `assignRiderToOrder error: ${error}` });
    }
};

export const getUnassignedOrders = async (req, res) => {
    try {
        const assignments = await DeliveryAssignment.find({ status: "brodcasted" }).populate("order").populate("shop", "name city address").sort({ createdAt: -1 });
        return res.status(200).json(assignments);
    } catch (error) {
        return res.status(500).json({ message: `getUnassignedOrders error: ${error}` });
    }
};
