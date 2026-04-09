import { createSlice } from "@reduxjs/toolkit";

const adminSlice = createSlice({
    name: "admin",
    initialState: {
        stats: null,
        pendingShops: [],
        allShops: [],
        tickets: [],
        riders: [],
        unassignedOrders: [],
        activeTab: "dashboard"
    },
    reducers: {
        setStats: (state, action) => { state.stats = action.payload },
        setPendingShops: (state, action) => { state.pendingShops = action.payload },
        setAllShops: (state, action) => { state.allShops = action.payload },
        updateShopInList: (state, action) => {
            const updated = action.payload;
            state.pendingShops = state.pendingShops.filter(s => s._id !== updated._id);
            const idx = state.allShops.findIndex(s => s._id === updated._id);
            if (idx !== -1) state.allShops[idx] = updated;
        },
        setTickets: (state, action) => { state.tickets = action.payload },
        updateTicket: (state, action) => {
            const idx = state.tickets.findIndex(t => t._id === action.payload._id);
            if (idx !== -1) state.tickets[idx] = action.payload;
        },
        setRiders: (state, action) => { state.riders = action.payload },
        setUnassignedOrders: (state, action) => { state.unassignedOrders = action.payload },
        removeUnassignedOrder: (state, action) => {
            state.unassignedOrders = state.unassignedOrders.filter(a => a._id !== action.payload);
        },
        setActiveTab: (state, action) => { state.activeTab = action.payload }
    }
});

export const {
    setStats, setPendingShops, setAllShops, updateShopInList,
    setTickets, updateTicket, setRiders, setUnassignedOrders,
    removeUnassignedOrder, setActiveTab
} = adminSlice.actions;

export default adminSlice.reducer;
