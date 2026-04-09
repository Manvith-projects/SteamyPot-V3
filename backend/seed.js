/**
 * seed.js — Generate synthetic food-delivery data and push to MongoDB
 *
 * Creates: 3 admins, 25 owners, 25 shops, ~150 items, 35 users, 13 riders,
 *          ~400+ orders, ~200+ reviews, 10 coupons, delivery assignments
 * Locations: Hyderabad (20 shops) + Guntur (5 shops)
 * All AI modules get synthetic data for demo purposes.
 *
 * Run:  node seed.js
 */

import mongoose from "mongoose";
import dotenv from "dotenv";
dotenv.config();

// ── Import real models so all schema fields are seeded ───────────────
import User from "./models/user.model.js";
import Item from "./models/item.model.js";
import Shop from "./models/shop.model.js";
import Order from "./models/order.model.js";
import DeliveryAssignment from "./models/deliveryAssignment.model.js";
import Coupon from "./models/coupon.model.js";
import Review from "./models/review.model.js";

// ── Helpers ──────────────────────────────────────────────────────────

const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const randBetween = (a, b) => Math.round((a + Math.random() * (b - a)) * 100) / 100;
const jitter = (val, range = 0.008) => val + (Math.random() - 0.5) * 2 * range;
const bcryptHash = "$2b$10$T2FEUxANYMY/HOsU6mHZ4OMrnzY1OL5o0EGTC4nkOHZhqPlWM96Ba"; // password: Test@1234

// Hyderabad area centers (lat, lng)
const HYD_AREAS = [
  { name: "Jubilee Hills",    lat: 17.4319, lng: 78.4076 },
  { name: "Banjara Hills",    lat: 17.4156, lng: 78.4487 },
  { name: "Madhapur",         lat: 17.4484, lng: 78.3908 },
  { name: "Gachibowli",       lat: 17.4401, lng: 78.3489 },
  { name: "Kukatpally",       lat: 17.4948, lng: 78.3996 },
  { name: "Ameerpet",         lat: 17.4375, lng: 78.4483 },
  { name: "Secunderabad",     lat: 17.4399, lng: 78.4983 },
  { name: "HITEC City",       lat: 17.4435, lng: 78.3772 },
  { name: "Begumpet",         lat: 17.4440, lng: 78.4670 },
  { name: "Kondapur",         lat: 17.4590, lng: 78.3609 },
];

// Guntur area centers (lat, lng)
const GUNTUR_AREAS = [
  { name: "Brodipet",       lat: 16.3067, lng: 80.4365 },
  { name: "Arundelpet",     lat: 16.3030, lng: 80.4470 },
  { name: "Lakshmipuram",   lat: 16.3100, lng: 80.4400 },
  { name: "Kothapet",       lat: 16.3000, lng: 80.4500 },
  { name: "AT Agraharam",   lat: 16.3150, lng: 80.4350 },
];

// Guntur shop menus
const GUNTUR_SHOP_MENUS = [
  { shopName: "Guntur Spice Kitchen", items: [
    { name: "Guntur Chicken Biryani", category: "Main Course", price: 220, foodType: "non veg" },
    { name: "Guntur Chilli Chicken", category: "Main Course", price: 200, foodType: "non veg" },
    { name: "Ulavacharu", category: "Main Course", price: 150, foodType: "veg" },
    { name: "Natu Kodi Pulusu", category: "Main Course", price: 280, foodType: "non veg" },
    { name: "Pesarattu MLA", category: "South Indian", price: 100, foodType: "veg" },
    { name: "Gutti Vankaya Curry", category: "Main Course", price: 160, foodType: "veg" },
  ]},
  { shopName: "Amaravathi Meals", items: [
    { name: "Andhra Thali (Veg)", category: "South Indian", price: 140, foodType: "veg" },
    { name: "Andhra Thali (Non-Veg)", category: "South Indian", price: 200, foodType: "non veg" },
    { name: "Pappu Charu", category: "South Indian", price: 80, foodType: "veg" },
    { name: "Gongura Mutton", category: "Main Course", price: 300, foodType: "non veg" },
    { name: "Pulihora", category: "South Indian", price: 90, foodType: "veg" },
    { name: "Bobbatlu", category: "Desserts", price: 70, foodType: "veg" },
  ]},
  { shopName: "Mirchi Bites Guntur", items: [
    { name: "Mirchi Bajji", category: "Snacks", price: 60, foodType: "veg" },
    { name: "Punugulu", category: "Snacks", price: 50, foodType: "veg" },
    { name: "Dosa Varieties", category: "South Indian", price: 90, foodType: "veg" },
    { name: "Egg Dosa", category: "South Indian", price: 100, foodType: "non veg" },
    { name: "Idli with Podi", category: "South Indian", price: 60, foodType: "veg" },
    { name: "Filter Coffee", category: "Others", price: 40, foodType: "veg" },
  ]},
  { shopName: "Ruchulu Restaurant", items: [
    { name: "Royyala Iguru", category: "Main Course", price: 350, foodType: "non veg" },
    { name: "Chepala Pulusu", category: "Main Course", price: 280, foodType: "non veg" },
    { name: "Chicken Fry", category: "Main Course", price: 200, foodType: "non veg" },
    { name: "Avakai Biryani", category: "Main Course", price: 250, foodType: "non veg" },
    { name: "Bendakaya Fry", category: "Main Course", price: 120, foodType: "veg" },
    { name: "Junnu", category: "Desserts", price: 80, foodType: "veg" },
  ]},
  { shopName: "Chalo Chaats Guntur", items: [
    { name: "Pani Puri", category: "Snacks", price: 50, foodType: "veg" },
    { name: "Masala Puri", category: "Snacks", price: 60, foodType: "veg" },
    { name: "Ram Ladoo", category: "Snacks", price: 40, foodType: "veg" },
    { name: "Samosa", category: "Snacks", price: 30, foodType: "veg" },
    { name: "Aloo Tikki Chaat", category: "Snacks", price: 70, foodType: "veg" },
    { name: "Mango Lassi", category: "Others", price: 60, foodType: "veg" },
  ]},
];

const SHOP_IMAGES = [
  "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=400",
  "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=400",
  "https://images.unsplash.com/photo-1552566626-52f8b828add9?w=400",
  "https://images.unsplash.com/photo-1514933651103-005eec06c04b?w=400",
  "https://images.unsplash.com/photo-1559339352-11d035aa65de?w=400",
];

const ITEM_IMAGES = {
  "South Indian": "https://images.unsplash.com/photo-1630383249896-424e482df921?w=300",
  "North Indian": "https://images.unsplash.com/photo-1585937421612-70a008356fbe?w=300",
  "Chinese":      "https://images.unsplash.com/photo-1563245372-f21724e3856d?w=300",
  "Pizza":        "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=300",
  "Burgers":      "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=300",
  "Sandwiches":   "https://images.unsplash.com/photo-1528735602780-2552fd46c7af?w=300",
  "Snacks":       "https://images.unsplash.com/photo-1604908176997-125f25cc6f3d?w=300",
  "Main Course":  "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=300",
  "Desserts":     "https://images.unsplash.com/photo-1551024601-bec78aea704b?w=300",
  "Fast Food":    "https://images.unsplash.com/photo-1561758033-d89a9ad46330?w=300",
  "Others":       "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=300",
};

// Menu items per shop type
const SHOP_MENUS = [
  { shopName: "Hyderabadi Biryani House", items: [
    { name: "Chicken Biryani", category: "Main Course", price: 250, foodType: "non veg" },
    { name: "Mutton Biryani", category: "Main Course", price: 350, foodType: "non veg" },
    { name: "Veg Biryani", category: "Main Course", price: 180, foodType: "veg" },
    { name: "Double Ka Meetha", category: "Desserts", price: 120, foodType: "veg" },
    { name: "Mirchi Ka Salan", category: "Main Course", price: 100, foodType: "veg" },
    { name: "Chicken 65", category: "Snacks", price: 200, foodType: "non veg" },
  ]},
  { shopName: "Chutneys South Indian", items: [
    { name: "Masala Dosa", category: "South Indian", price: 120, foodType: "veg" },
    { name: "Idli Sambar", category: "South Indian", price: 80, foodType: "veg" },
    { name: "Pesarattu", category: "South Indian", price: 100, foodType: "veg" },
    { name: "Uttapam", category: "South Indian", price: 110, foodType: "veg" },
    { name: "Filter Coffee", category: "Others", price: 50, foodType: "veg" },
    { name: "Mysore Bonda", category: "Snacks", price: 90, foodType: "veg" },
  ]},
  { shopName: "Paradise Restaurant", items: [
    { name: "Special Biryani", category: "Main Course", price: 300, foodType: "non veg" },
    { name: "Kebab Platter", category: "Snacks", price: 280, foodType: "non veg" },
    { name: "Rumali Roti", category: "North Indian", price: 40, foodType: "veg" },
    { name: "Butter Chicken", category: "North Indian", price: 260, foodType: "non veg" },
    { name: "Paneer Tikka", category: "North Indian", price: 220, foodType: "veg" },
    { name: "Qubani Ka Meetha", category: "Desserts", price: 130, foodType: "veg" },
  ]},
  { shopName: "Dragon Bowl Chinese", items: [
    { name: "Schezwan Noodles", category: "Chinese", price: 180, foodType: "veg" },
    { name: "Chilli Chicken", category: "Chinese", price: 220, foodType: "non veg" },
    { name: "Manchurian", category: "Chinese", price: 160, foodType: "veg" },
    { name: "Fried Rice", category: "Chinese", price: 150, foodType: "veg" },
    { name: "Spring Rolls", category: "Snacks", price: 140, foodType: "veg" },
    { name: "Dragon Chicken", category: "Chinese", price: 240, foodType: "non veg" },
  ]},
  { shopName: "Pizza Junction", items: [
    { name: "Margherita Pizza", category: "Pizza", price: 199, foodType: "veg" },
    { name: "Pepperoni Pizza", category: "Pizza", price: 299, foodType: "non veg" },
    { name: "Farmhouse Pizza", category: "Pizza", price: 249, foodType: "veg" },
    { name: "BBQ Chicken Pizza", category: "Pizza", price: 329, foodType: "non veg" },
    { name: "Garlic Bread", category: "Snacks", price: 99, foodType: "veg" },
    { name: "Pasta Alfredo", category: "Others", price: 189, foodType: "veg" },
  ]},
  { shopName: "Burger Barn", items: [
    { name: "Classic Veggie Burger", category: "Burgers", price: 129, foodType: "veg" },
    { name: "Chicken Zinger", category: "Burgers", price: 179, foodType: "non veg" },
    { name: "Double Patty Burger", category: "Burgers", price: 219, foodType: "non veg" },
    { name: "Paneer Burger", category: "Burgers", price: 149, foodType: "veg" },
    { name: "French Fries", category: "Fast Food", price: 89, foodType: "veg" },
    { name: "Chocolate Shake", category: "Desserts", price: 129, foodType: "veg" },
  ]},
  { shopName: "Roti & Rice", items: [
    { name: "Dal Makhani", category: "North Indian", price: 180, foodType: "veg" },
    { name: "Rajma Chawal", category: "North Indian", price: 160, foodType: "veg" },
    { name: "Chole Bhature", category: "North Indian", price: 140, foodType: "veg" },
    { name: "Palak Paneer", category: "North Indian", price: 200, foodType: "veg" },
    { name: "Tandoori Roti", category: "North Indian", price: 30, foodType: "veg" },
    { name: "Gulab Jamun", category: "Desserts", price: 80, foodType: "veg" },
  ]},
  { shopName: "Street Food Adda", items: [
    { name: "Pani Puri", category: "Snacks", price: 60, foodType: "veg" },
    { name: "Samosa Chaat", category: "Snacks", price: 80, foodType: "veg" },
    { name: "Dahi Puri", category: "Snacks", price: 70, foodType: "veg" },
    { name: "Vada Pav", category: "Fast Food", price: 50, foodType: "veg" },
    { name: "Bhel Puri", category: "Snacks", price: 60, foodType: "veg" },
    { name: "Pav Bhaji", category: "Fast Food", price: 120, foodType: "veg" },
  ]},
  { shopName: "Sandwich Studio", items: [
    { name: "Club Sandwich", category: "Sandwiches", price: 159, foodType: "non veg" },
    { name: "Grilled Veg Sandwich", category: "Sandwiches", price: 119, foodType: "veg" },
    { name: "Paneer Tikka Sandwich", category: "Sandwiches", price: 139, foodType: "veg" },
    { name: "Chicken Mayo Sandwich", category: "Sandwiches", price: 149, foodType: "non veg" },
    { name: "Cheese Corn Sandwich", category: "Sandwiches", price: 129, foodType: "veg" },
    { name: "Cold Coffee", category: "Others", price: 89, foodType: "veg" },
  ]},
  { shopName: "Sweet Tooth Bakery", items: [
    { name: "Chocolate Truffle Cake", category: "Desserts", price: 350, foodType: "veg" },
    { name: "Red Velvet Pastry", category: "Desserts", price: 120, foodType: "veg" },
    { name: "Brownie", category: "Desserts", price: 90, foodType: "veg" },
    { name: "Cheesecake Slice", category: "Desserts", price: 180, foodType: "veg" },
    { name: "Cookie Box", category: "Snacks", price: 150, foodType: "veg" },
    { name: "Mango Mousse", category: "Desserts", price: 140, foodType: "veg" },
  ]},
  { shopName: "Spice Route", items: [
    { name: "Egg Biryani", category: "Main Course", price: 180, foodType: "non veg" },
    { name: "Haleem", category: "Main Course", price: 200, foodType: "non veg" },
    { name: "Shawarma", category: "Fast Food", price: 120, foodType: "non veg" },
    { name: "Falafel Wrap", category: "Fast Food", price: 130, foodType: "veg" },
    { name: "Hummus Platter", category: "Snacks", price: 160, foodType: "veg" },
    { name: "Baklava", category: "Desserts", price: 110, foodType: "veg" },
  ]},
  { shopName: "Madhapur Meals", items: [
    { name: "Thali Meals (Veg)", category: "South Indian", price: 150, foodType: "veg" },
    { name: "Thali Meals (Non-Veg)", category: "South Indian", price: 220, foodType: "non veg" },
    { name: "Curd Rice", category: "South Indian", price: 80, foodType: "veg" },
    { name: "Rasam Rice", category: "South Indian", price: 90, foodType: "veg" },
    { name: "Chicken Curry", category: "Main Course", price: 200, foodType: "non veg" },
    { name: "Payasam", category: "Desserts", price: 70, foodType: "veg" },
  ]},
  { shopName: "Tandoori Express", items: [
    { name: "Tandoori Chicken", category: "North Indian", price: 280, foodType: "non veg" },
    { name: "Seekh Kebab", category: "North Indian", price: 240, foodType: "non veg" },
    { name: "Paneer Tikka Masala", category: "North Indian", price: 220, foodType: "veg" },
    { name: "Naan", category: "North Indian", price: 40, foodType: "veg" },
    { name: "Raita", category: "Others", price: 50, foodType: "veg" },
    { name: "Lassi", category: "Others", price: 70, foodType: "veg" },
  ]},
  { shopName: "Wok This Way", items: [
    { name: "Hakka Noodles", category: "Chinese", price: 160, foodType: "veg" },
    { name: "Paneer Chilli", category: "Chinese", price: 190, foodType: "veg" },
    { name: "Prawn Fried Rice", category: "Chinese", price: 250, foodType: "non veg" },
    { name: "Chicken Lollipop", category: "Chinese", price: 200, foodType: "non veg" },
    { name: "Sweet Corn Soup", category: "Others", price: 100, foodType: "veg" },
    { name: "Dim Sum", category: "Chinese", price: 180, foodType: "veg" },
  ]},
  { shopName: "Dosa Factory", items: [
    { name: "Paper Dosa", category: "South Indian", price: 90, foodType: "veg" },
    { name: "Onion Rava Dosa", category: "South Indian", price: 120, foodType: "veg" },
    { name: "Set Dosa", category: "South Indian", price: 100, foodType: "veg" },
    { name: "Medu Vada", category: "South Indian", price: 70, foodType: "veg" },
    { name: "Pongal", category: "South Indian", price: 90, foodType: "veg" },
    { name: "Kesari Bath", category: "Desserts", price: 60, foodType: "veg" },
  ]},
  { shopName: "Nawabi Kitchen", items: [
    { name: "Mutton Korma", category: "Main Course", price: 320, foodType: "non veg" },
    { name: "Chicken Dum Biryani", category: "Main Course", price: 280, foodType: "non veg" },
    { name: "Lukhmi", category: "Snacks", price: 100, foodType: "non veg" },
    { name: "Osmania Biscuits", category: "Snacks", price: 80, foodType: "veg" },
    { name: "Sheer Khurma", category: "Desserts", price: 120, foodType: "veg" },
    { name: "Pathar Ka Gosht", category: "Main Course", price: 400, foodType: "non veg" },
  ]},
  { shopName: "Chaat Chowk", items: [
    { name: "Aloo Tikki", category: "Snacks", price: 60, foodType: "veg" },
    { name: "Ragda Pattice", category: "Snacks", price: 80, foodType: "veg" },
    { name: "Sev Puri", category: "Snacks", price: 70, foodType: "veg" },
    { name: "Kachori", category: "Snacks", price: 50, foodType: "veg" },
    { name: "Jalebi", category: "Desserts", price: 60, foodType: "veg" },
    { name: "Lassi", category: "Others", price: 70, foodType: "veg" },
  ]},
  { shopName: "Grill House", items: [
    { name: "Grilled Chicken Breast", category: "Main Course", price: 260, foodType: "non veg" },
    { name: "Grilled Fish", category: "Main Course", price: 300, foodType: "non veg" },
    { name: "Grilled Paneer Steak", category: "Main Course", price: 220, foodType: "veg" },
    { name: "Caesar Salad", category: "Others", price: 180, foodType: "veg" },
    { name: "Mushroom Soup", category: "Others", price: 120, foodType: "veg" },
    { name: "Tiramisu", category: "Desserts", price: 190, foodType: "veg" },
  ]},
  { shopName: "Irani Chai Point", items: [
    { name: "Irani Chai", category: "Others", price: 30, foodType: "veg" },
    { name: "Bun Maska", category: "Snacks", price: 40, foodType: "veg" },
    { name: "Keema Samosa", category: "Snacks", price: 50, foodType: "non veg" },
    { name: "Egg Puff", category: "Snacks", price: 40, foodType: "non veg" },
    { name: "Veg Puff", category: "Snacks", price: 35, foodType: "veg" },
    { name: "Mawa Toast", category: "Snacks", price: 45, foodType: "veg" },
  ]},
  { shopName: "Fresh Bowl Salads", items: [
    { name: "Greek Salad", category: "Others", price: 180, foodType: "veg" },
    { name: "Chicken Caesar Wrap", category: "Sandwiches", price: 200, foodType: "non veg" },
    { name: "Quinoa Bowl", category: "Others", price: 220, foodType: "veg" },
    { name: "Smoothie Bowl", category: "Desserts", price: 190, foodType: "veg" },
    { name: "Fruit Juice", category: "Others", price: 100, foodType: "veg" },
    { name: "Protein Shake", category: "Others", price: 150, foodType: "veg" },
  ]},
];

const FIRST_NAMES = [
  "Aarav","Vivaan","Aditya","Vihaan","Arjun","Reyansh","Ayaan","Krishna","Ishaan","Sai",
  "Ananya","Aadhya","Myra","Aanya","Isha","Sara","Diya","Priya","Sneha","Kavya",
  "Rahul","Rohit","Manish","Suresh","Rajesh","Pooja","Neha","Swathi","Lakshmi","Meena",
];

// ── Review templates for synthetic data ──────────────────────────────
const POSITIVE_REVIEWS = [
  "Amazing food! Delivery was super fast. Will order again.",
  "Best biryani in Hyderabad. Hot and fresh, loved every bite.",
  "Great taste and generous portions. Highly recommended!",
  "Perfectly cooked, well-packaged. Driver was polite too.",
  "Exceeded expectations! Quality is consistently excellent.",
  "Ordered for a party, everyone loved it. 10/10!",
  "Fresh ingredients, authentic flavors. My go-to place now.",
  "Fast delivery even during peak hours. Food was still hot.",
  "Value for money. Large portions and great seasoning.",
  "The best I've had in a long time. Definitely a repeat customer.",
];
const NEUTRAL_REVIEWS = [
  "Food was okay. Nothing special but decent for the price.",
  "Average taste, packaging could be better.",
  "Delivery was on time but food was lukewarm.",
  "Portion size is fair. Taste is acceptable.",
  "Not bad, but I've had better. Might try again.",
];
const NEGATIVE_REVIEWS = [
  "Too spicy for my liking. Took too long to deliver.",
  "Food arrived cold. Packaging was leaking.",
  "Overpriced for the quantity. Disappointing experience.",
  "Order was wrong — got different items than what I ordered.",
  "Very oily and salty. Would not recommend.",
];

// ── Coupon definitions ───────────────────────────────────────────────
const COUPON_DEFS = [
  { code: "WELCOME50",  desc: "50% off on first order",          type: "percentage", value: 50,  min: 200,  max: 150, limit: 1000, perUser: 1 },
  { code: "FLAT100",    desc: "Flat ₹100 off on orders above ₹500", type: "flat",   value: 100, min: 500,  max: null, limit: 500,  perUser: 3 },
  { code: "BIRYANI20",  desc: "20% off on Biryani orders",       type: "percentage", value: 20,  min: 300,  max: 100, limit: 200,  perUser: 2 },
  { code: "FREEDELIVERY", desc: "Free delivery on orders above ₹250", type: "flat", value: 40,  min: 250,  max: null, limit: null, perUser: 5 },
  { code: "WEEKEND30",  desc: "30% off weekend special",         type: "percentage", value: 30,  min: 400,  max: 200, limit: 300,  perUser: 2 },
  { code: "NEWUSER25",  desc: "25% off for new users",           type: "percentage", value: 25,  min: 150,  max: 120, limit: 500,  perUser: 1 },
  { code: "DESSERT15",  desc: "15% off on desserts",             type: "percentage", value: 15,  min: 100,  max: 80,  limit: 200,  perUser: 3 },
  { code: "FLAT50",     desc: "Flat ₹50 off",                    type: "flat",       value: 50,  min: 200,  max: null, limit: 1000, perUser: 5 },
  { code: "MEGA200",    desc: "Flat ₹200 off on orders above ₹1000", type: "flat",  value: 200, min: 1000, max: null, limit: 100,  perUser: 1 },
  { code: "SPICY10",    desc: "10% off on Chinese & North Indian", type: "percentage", value: 10, min: 200, max: 60,  limit: 400, perUser: 3 },
];

// ── Main seed function ───────────────────────────────────────────────

async function seed() {
  await mongoose.connect(process.env.MONGODB_URL);
  console.log("Connected to MongoDB");

  // Cleanup old seed data
  const existingSeedUsers = await User.countDocuments({ email: /^seed_/ });
  if (existingSeedUsers > 0) {
    console.log(`Found ${existingSeedUsers} existing seed users. Cleaning up old seed data...`);
    const oldSeedUsers = await User.find({ email: /^seed_/ });
    const oldUserIds = oldSeedUsers.map(u => u._id);
    const oldOwnerIds = oldSeedUsers.filter(u => u.role === "owner").map(u => u._id);

    const oldShops = await Shop.find({ owner: { $in: oldOwnerIds } });
    const oldShopIds = oldShops.map(s => s._id);

    await Review.deleteMany({ user: { $in: oldUserIds } });
    await DeliveryAssignment.deleteMany({ order: { $exists: true } });
    await Coupon.deleteMany({ code: { $in: COUPON_DEFS.map(c => c.code) } });
    const SupportTicketClean = (await import("./models/supportTicket.model.js")).default;
    await SupportTicketClean.deleteMany({ raisedBy: { $in: oldUserIds } });
    await Item.deleteMany({ shop: { $in: oldShopIds } });
    await Shop.deleteMany({ _id: { $in: oldShopIds } });
    await Order.deleteMany({ user: { $in: oldUserIds } });
    await User.deleteMany({ _id: { $in: oldUserIds } });
    console.log("Old seed data cleaned.");
  }

  // ── 1. Create admins ──────────────────────────────────────────────
  console.log("Creating admins...");
  const admins = [];
  for (let i = 0; i < 3; i++) {
    const area = HYD_AREAS[i];
    const admin = await User.create({
      fullName: `Admin ${pick(FIRST_NAMES)}`,
      email: `seed_admin_${i}@test.com`,
      password: bcryptHash,
      mobile: `70000${String(10000 + i).slice(-5)}`,
      role: "admin",
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      appSessionsPerWeek: 20,
      preferredOrderHour: 10,
    });
    admins.push(admin);
  }
  console.log(`  Created ${admins.length} admins`);

  // ── 2. Create owners ──────────────────────────────────────────────
  console.log("Creating owners...");
  const owners = [];
  for (let i = 0; i < SHOP_MENUS.length; i++) {
    const area = HYD_AREAS[i % HYD_AREAS.length];
    const owner = await User.create({
      fullName: `${pick(FIRST_NAMES)} (Owner)`,
      email: `seed_owner_${i}@test.com`,
      password: bcryptHash,
      mobile: `90000${String(10000 + i).slice(-5)}`,
      role: "owner",
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      appSessionsPerWeek: randBetween(10, 25),
      preferredOrderHour: pick([9, 10, 11, 12]),
    });
    owners.push(owner);
  }
  console.log(`  Created ${owners.length} owners`);

  // ── 2b. Create Guntur owners ───────────────────────────────────────
  console.log("Creating Guntur owners...");
  const gunturOwners = [];
  for (let i = 0; i < GUNTUR_SHOP_MENUS.length; i++) {
    const area = GUNTUR_AREAS[i % GUNTUR_AREAS.length];
    const idx = 20 + i; // continue numbering after Hyderabad owners
    const owner = await User.create({
      fullName: `${pick(FIRST_NAMES)} (Owner)`,
      email: `seed_owner_${idx}@test.com`,
      password: bcryptHash,
      mobile: `90000${String(10000 + idx).slice(-5)}`,
      role: "owner",
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      appSessionsPerWeek: randBetween(10, 25),
      preferredOrderHour: pick([9, 10, 11, 12]),
    });
    gunturOwners.push(owner);
    owners.push(owner);
  }
  console.log(`  Created ${gunturOwners.length} Guntur owners`);

  // ── 3. Create shops & items ────────────────────────────────────────
  console.log("Creating shops and items...");
  const allShops = [];
  const allItems = [];
  const CUISINES = ["Indian", "South Indian", "North Indian", "Chinese", "Italian", "Continental", "Street Food"];
  const ZONES = ["Jubilee Hills", "Banjara Hills", "Madhapur", "Gachibowli", "Kukatpally",
                  "Ameerpet", "Secunderabad", "HITEC City", "Begumpet", "Kondapur"];

  for (let i = 0; i < SHOP_MENUS.length; i++) {
    const menu = SHOP_MENUS[i];
    const area = HYD_AREAS[i % HYD_AREAS.length];
    const owner = owners[i];

    const shop = await Shop.create({
      name: menu.shopName,
      image: SHOP_IMAGES[i % SHOP_IMAGES.length],
      owner: owner._id,
      city: "Hyderabad",
      state: "Telangana",
      address: `${area.name}, Hyderabad, Telangana`,
      items: [],
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      cuisine: CUISINES[i % CUISINES.length],
      avgPrepTime: randBetween(10, 30),
      avgRating: randBetween(3.5, 4.9),
      reviewCount: Math.floor(Math.random() * 300) + 20,
      zone: ZONES[i % ZONES.length],
      isApproved: i < 18 ? "approved" : "pending",   // last 2 shops stay pending for demo
    });

    const shopItems = [];
    for (const mi of menu.items) {
      const item = await Item.create({
        name: mi.name,
        image: ITEM_IMAGES[mi.category] || ITEM_IMAGES["Others"],
        shop: shop._id,
        category: mi.category,
        price: mi.price,
        foodType: mi.foodType,
        rating: {
          average: randBetween(3.2, 4.9),
          count: Math.floor(Math.random() * 200) + 10,
        },
        tags: [mi.category.toLowerCase(), mi.foodType, "popular"],
        cuisine: CUISINES[i % CUISINES.length],
      });
      shopItems.push(item);
      allItems.push(item);
    }

    shop.items = shopItems.map(it => it._id);
    await shop.save();
    allShops.push(shop);
  }
  console.log(`  Created ${allShops.length} shops, ${allItems.length} items`);

  // ── 3b. Create Guntur shops & items ────────────────────────────────
  console.log("Creating Guntur shops and items...");
  const GUNTUR_ZONES = ["Brodipet", "Arundelpet", "Lakshmipuram", "Kothapet", "AT Agraharam"];

  for (let i = 0; i < GUNTUR_SHOP_MENUS.length; i++) {
    const menu = GUNTUR_SHOP_MENUS[i];
    const area = GUNTUR_AREAS[i % GUNTUR_AREAS.length];
    const owner = gunturOwners[i];

    const shop = await Shop.create({
      name: menu.shopName,
      image: SHOP_IMAGES[i % SHOP_IMAGES.length],
      owner: owner._id,
      city: "Guntur",
      state: "Andhra Pradesh",
      address: `${area.name}, Guntur, Andhra Pradesh`,
      items: [],
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      cuisine: CUISINES[i % CUISINES.length],
      avgPrepTime: randBetween(10, 30),
      avgRating: randBetween(3.5, 4.9),
      reviewCount: Math.floor(Math.random() * 200) + 10,
      zone: GUNTUR_ZONES[i % GUNTUR_ZONES.length],
      isApproved: "approved",
    });

    const shopItems = [];
    for (const mi of menu.items) {
      const item = await Item.create({
        name: mi.name,
        image: ITEM_IMAGES[mi.category] || ITEM_IMAGES["Others"],
        shop: shop._id,
        category: mi.category,
        price: mi.price,
        foodType: mi.foodType,
        rating: {
          average: randBetween(3.2, 4.9),
          count: Math.floor(Math.random() * 200) + 10,
        },
        tags: [mi.category.toLowerCase(), mi.foodType, "popular"],
        cuisine: CUISINES[i % CUISINES.length],
      });
      shopItems.push(item);
      allItems.push(item);
    }

    shop.items = shopItems.map(it => it._id);
    await shop.save();
    allShops.push(shop);
  }
  console.log(`  Created ${GUNTUR_SHOP_MENUS.length} Guntur shops, ${GUNTUR_SHOP_MENUS.length * 6} items`);

  // ── 4. Create riders (deliveryBoys) ────────────────────────────────
  console.log("Creating riders...");
  const riders = [];
  for (let i = 0; i < 10; i++) {
    const area = pick(HYD_AREAS);
    const rider = await User.create({
      fullName: `${pick(FIRST_NAMES)} (Rider)`,
      email: `seed_rider_${i}@test.com`,
      password: bcryptHash,
      mobile: `60000${String(10000 + i).slice(-5)}`,
      role: "deliveryBoy",
      isOnline: i < 7, // 7 of 10 riders online
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      appSessionsPerWeek: randBetween(15, 40),
      preferredOrderHour: pick([8, 9, 10, 18, 19, 20]),
    });
    riders.push(rider);
  }
  console.log(`  Created ${riders.length} riders`);

  // ── 4b. Create Guntur riders ───────────────────────────────────────
  console.log("Creating Guntur riders...");
  for (let i = 0; i < 3; i++) {
    const area = pick(GUNTUR_AREAS);
    const idx = 10 + i; // continue numbering after Hyderabad riders
    const rider = await User.create({
      fullName: `${pick(FIRST_NAMES)} (Rider)`,
      email: `seed_rider_${idx}@test.com`,
      password: bcryptHash,
      mobile: `60000${String(10000 + idx).slice(-5)}`,
      role: "deliveryBoy",
      isOnline: true,
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      appSessionsPerWeek: randBetween(15, 40),
      preferredOrderHour: pick([8, 9, 10, 18, 19, 20]),
    });
    riders.push(rider);
  }
  console.log(`  Created 3 Guntur riders`);

  // ── 5. Create users with AI churn-prediction fields ────────────────
  console.log("Creating users...");
  const users = [];
  for (let i = 0; i < 30; i++) {
    const area = pick(HYD_AREAS);
    // Vary churn risk: first 10 = low risk, next 10 = medium, last 10 = high
    const isHighRisk = i >= 20;
    const isMedRisk = i >= 10 && i < 20;

    const u = await User.create({
      fullName: pick(FIRST_NAMES) + " " + pick(FIRST_NAMES) + "i",
      email: `seed_user_${i}@test.com`,
      password: bcryptHash,
      mobile: `80000${String(10000 + i).slice(-5)}`,
      role: "user",
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      // AI churn prediction fields
      ordersLast30d: isHighRisk ? randBetween(0, 1) : isMedRisk ? randBetween(1, 3) : randBetween(3, 8),
      ordersLast90d: isHighRisk ? randBetween(1, 3) : isMedRisk ? randBetween(3, 8) : randBetween(8, 20),
      avgOrderValue: randBetween(150, 600),
      daysSinceLastOrder: isHighRisk ? randBetween(30, 90) : isMedRisk ? randBetween(10, 30) : randBetween(0, 10),
      orderFrequency: isHighRisk ? randBetween(0.1, 0.5) : isMedRisk ? randBetween(0.5, 1.5) : randBetween(1.5, 4),
      cancellationRate: isHighRisk ? randBetween(0.2, 0.5) : isMedRisk ? randBetween(0.05, 0.2) : randBetween(0, 0.05),
      avgDeliveryDelayMin: isHighRisk ? randBetween(10, 25) : isMedRisk ? randBetween(5, 10) : randBetween(0, 5),
      avgUserRating: isHighRisk ? randBetween(2.5, 3.5) : isMedRisk ? randBetween(3.5, 4.2) : randBetween(4.2, 5.0),
      numComplaints: isHighRisk ? Math.floor(Math.random() * 8) + 3 : isMedRisk ? Math.floor(Math.random() * 3) : 0,
      discountUsageRate: isHighRisk ? randBetween(0.6, 0.9) : randBetween(0.1, 0.5),
      appSessionsPerWeek: isHighRisk ? randBetween(1, 3) : isMedRisk ? randBetween(3, 7) : randBetween(7, 15),
      preferredOrderHour: pick([12, 13, 18, 19, 20, 21]),
      churnRisk: isHighRisk ? "high" : isMedRisk ? "medium" : "low",
      churnProbability: isHighRisk ? randBetween(0.7, 0.95) : isMedRisk ? randBetween(0.3, 0.7) : randBetween(0.01, 0.3),
      lastChurnCheck: new Date(),
    });
    users.push(u);
  }
  console.log(`  Created ${users.length} users`);

  // ── 5b. Create Guntur users ────────────────────────────────────────
  console.log("Creating Guntur users...");
  for (let i = 0; i < 5; i++) {
    const area = pick(GUNTUR_AREAS);
    const idx = 30 + i; // continue numbering after Hyderabad users
    const u = await User.create({
      fullName: pick(FIRST_NAMES) + " " + pick(FIRST_NAMES) + "i",
      email: `seed_user_${idx}@test.com`,
      password: bcryptHash,
      mobile: `80000${String(10000 + idx).slice(-5)}`,
      role: "user",
      location: { type: "Point", coordinates: [jitter(area.lng), jitter(area.lat)] },
      ordersLast30d: randBetween(3, 8),
      ordersLast90d: randBetween(8, 20),
      avgOrderValue: randBetween(150, 500),
      daysSinceLastOrder: randBetween(0, 10),
      orderFrequency: randBetween(1.5, 4),
      cancellationRate: randBetween(0, 0.05),
      avgDeliveryDelayMin: randBetween(0, 5),
      avgUserRating: randBetween(4.2, 5.0),
      numComplaints: 0,
      discountUsageRate: randBetween(0.1, 0.5),
      appSessionsPerWeek: randBetween(7, 15),
      preferredOrderHour: pick([12, 13, 18, 19, 20, 21]),
      churnRisk: "low",
      churnProbability: randBetween(0.01, 0.3),
      lastChurnCheck: new Date(),
    });
    users.push(u);
  }
  console.log(`  Created 5 Guntur users`);

  // ── 6. Create orders with AI fields ────────────────────────────────
  console.log("Creating orders...");
  let orderCount = 0;
  const allOrders = [];
  const STATUSES = ["pending", "preparing", "out of delivery", "delivered"];
  const WEATHER = ["Clear", "Cloudy", "Rain", "Drizzle", "Thunderstorm"];

  for (const user of users) {
    const numShops = 3 + Math.floor(Math.random() * 6);
    const shuffledShops = [...allShops].sort(() => Math.random() - 0.5).slice(0, numShops);

    for (const shop of shuffledShops) {
      const repeats = 1 + Math.floor(Math.random() * 3);

      for (let r = 0; r < repeats; r++) {
        const shopItemDocs = allItems.filter(it => it.shop.toString() === shop._id.toString());
        const numItems = 1 + Math.floor(Math.random() * Math.min(4, shopItemDocs.length));
        const orderItems = [...shopItemDocs].sort(() => Math.random() - 0.5).slice(0, numItems);

        const shopOrderItems = orderItems.map(it => ({
          item: it._id,
          name: it.name,
          price: it.price,
          quantity: 1 + Math.floor(Math.random() * 3),
        }));

        const subtotal = shopOrderItems.reduce((s, i) => s + i.price * i.quantity, 0);
        const isGunturShop = shop.city === "Guntur";
        const area = isGunturShop ? pick(GUNTUR_AREAS) : pick(HYD_AREAS);
        const cityName = isGunturShop ? "Guntur" : "Hyderabad";
        const daysAgo = Math.floor(Math.random() * 60);
        const orderDate = new Date(Date.now() - daysAgo * 86400000);
        const status = daysAgo === 0 ? pick(STATUSES) : "delivered";
        const assignedRider = pick(riders);
        const surgeMultiplier = randBetween(1.0, 2.0);
        const deliveryFee = Math.round(30 + subtotal * 0.05 * surgeMultiplier);

        const order = await Order.create({
          user: user._id,
          paymentMethod: pick(["cod", "online"]),
          deliveryAddress: {
            text: `${area.name}, ${cityName}`,
            latitude: jitter(area.lat),
            longitude: jitter(area.lng),
          },
          totalAmount: subtotal + deliveryFee,
          shopOrders: [{
            shop: shop._id,
            owner: shop.owner,
            subtotal,
            shopOrderItems,
            status,
            assignedDeliveryBoy: status !== "pending" ? assignedRider._id : undefined,
            deliveredAt: status === "delivered" ? orderDate : undefined,
          }],
          payment: true,
          // AI-Layer fields
          predictedEta: randBetween(20, 55),
          etaConfidence: randBetween(0.7, 0.98),
          surgeMultiplier,
          dynamicDeliveryFee: deliveryFee,
          pricingReason: surgeMultiplier > 1.4 ? "High demand, limited riders" : "Standard pricing",
          isPeakHour: [12, 13, 19, 20, 21].includes(orderDate.getHours()),
          aiDriverId: assignedRider._id.toString(),
          aiDriverScore: randBetween(0.6, 0.99),
          createdAt: orderDate,
          updatedAt: orderDate,
        });
        allOrders.push(order);
        orderCount++;
      }
    }
  }
  console.log(`  Created ${orderCount} orders`);

  // ── 7. Create delivery assignments ─────────────────────────────────
  console.log("Creating delivery assignments...");
  let assignmentCount = 0;
  const recentOrders = allOrders.slice(-50); // last 50 orders
  for (const order of recentOrders) {
    for (const so of order.shopOrders) {
      if (so.assignedDeliveryBoy) {
        const rider = riders.find(r => r._id.toString() === so.assignedDeliveryBoy.toString()) || pick(riders);
        const rArea = pick(HYD_AREAS);
        await DeliveryAssignment.create({
          order: order._id,
          shop: so.shop,
          shopOrderId: so._id,
          brodcastedTo: riders.slice(0, 5).map(r => r._id),
          assignedTo: rider._id,
          status: so.status === "delivered" ? "completed" : "assigned",
          acceptedAt: order.createdAt,
          aiAllocatedDriver: rider._id.toString(),
          aiOptimizationScore: randBetween(0.7, 0.99),
          aiAllocationReason: pick([
            "Closest available rider with high rating",
            "Optimal route efficiency",
            "Lowest current workload",
            "Highest historical success rate in zone",
          ]),
          predictedDeliveryTime: `${Math.floor(randBetween(15, 45))} mins`,
          optimisedRoute: [
            { lat: jitter(rArea.lat), lon: jitter(rArea.lng) },
            { lat: jitter(rArea.lat, 0.01), lon: jitter(rArea.lng, 0.01) },
          ],
          routeSavingsPct: randBetween(5, 25),
        });
        assignmentCount++;
      }
    }
  }
  console.log(`  Created ${assignmentCount} delivery assignments`);

  // ── 8. Create reviews ──────────────────────────────────────────────
  console.log("Creating reviews...");
  let reviewCount = 0;
  for (const user of users) {
    const numReviews = 2 + Math.floor(Math.random() * 6); // 2-7 reviews per user
    const reviewShops = [...allShops].sort(() => Math.random() - 0.5).slice(0, numReviews);

    for (const shop of reviewShops) {
      const rating = Math.floor(Math.random() * 5) + 1;
      let reviewText, sentiment;
      if (rating >= 4) {
        reviewText = pick(POSITIVE_REVIEWS);
        sentiment = "positive";
      } else if (rating === 3) {
        reviewText = pick(NEUTRAL_REVIEWS);
        sentiment = "neutral";
      } else {
        reviewText = pick(NEGATIVE_REVIEWS);
        sentiment = "negative";
      }

      const daysAgo = Math.floor(Math.random() * 60);
      const reviewDate = new Date(Date.now() - daysAgo * 86400000);

      await Review.create({
        user: user._id,
        shop: shop._id,
        rating,
        reviewText,
        sentiment,
        createdAt: reviewDate,
        updatedAt: reviewDate,
      });
      reviewCount++;
    }
  }
  console.log(`  Created ${reviewCount} reviews`);

  // ── 8b. Extra reviews for Guntur shops ─────────────────────────────
  console.log("Adding extra reviews for Guntur shops...");
  const gunturShops = allShops.filter(s => s.city === "Guntur");
  let gunturReviewCount = 0;
  const GUNTUR_POSITIVE = [
    "Authentic Andhra flavors! The spice level is just perfect.",
    "Best biryani in Guntur. Quantity is very generous.",
    "Amazing taste, reminds me of home-cooked food. Love it!",
    "Super fresh ingredients and quick delivery. Highly recommend!",
    "The chicken 65 here is legendary. Crispy and flavorful.",
    "Value for money. Large portions and great seasoning.",
    "Tried their special thali — every dish was outstanding.",
    "Fast delivery even during peak hours. Food was still hot.",
    "The mirchi bajji is the best I've ever had. So crunchy!",
    "Wonderful taste, proper Guntur spice level. Will order again!",
    "Their gongura chicken is a must-try. So authentic!",
    "Great packaging, food arrived fresh and hot. Excellent quality.",
  ];
  const GUNTUR_NEUTRAL = [
    "Food was decent. Average Guntur restaurant quality.",
    "Delivery was on time but food was slightly lukewarm.",
    "Taste is okay. Expected more spice for a Guntur restaurant.",
    "Portion size could be better for the price.",
    "Not bad. The rice was good but the curry lacked depth.",
  ];
  const GUNTUR_NEGATIVE = [
    "Too oily for my taste. Need to reduce the oil content.",
    "Food arrived cold. Very disappointing for such a short distance.",
    "Overpriced compared to other restaurants in Guntur.",
    "Order was incomplete — missing one item. Frustrating!",
    "Taste has gone down recently. Used to be much better.",
  ];
  for (const shop of gunturShops) {
    const reviewUsers = [...users].sort(() => Math.random() - 0.5).slice(0, 15);
    for (const user of reviewUsers) {
      const rating = Math.floor(Math.random() * 5) + 1;
      let reviewText, sentiment;
      if (rating >= 4) {
        reviewText = pick(GUNTUR_POSITIVE);
        sentiment = "positive";
      } else if (rating === 3) {
        reviewText = pick(GUNTUR_NEUTRAL);
        sentiment = "neutral";
      } else {
        reviewText = pick(GUNTUR_NEGATIVE);
        sentiment = "negative";
      }
      const daysAgo = Math.floor(Math.random() * 90);
      const reviewDate = new Date(Date.now() - daysAgo * 86400000);
      await Review.create({
        user: user._id,
        shop: shop._id,
        rating,
        reviewText,
        sentiment,
        createdAt: reviewDate,
        updatedAt: reviewDate,
      });
      gunturReviewCount++;
    }
  }
  console.log(`  Created ${gunturReviewCount} extra Guntur reviews`);

  // ── 9. Create coupons ──────────────────────────────────────────────
  console.log("Creating coupons...");
  const adminCreator = admins[0];
  for (const c of COUPON_DEFS) {
    const validFrom = new Date();
    const validUntil = new Date(Date.now() + 90 * 86400000); // 90 days from now

    await Coupon.create({
      code: c.code,
      description: c.desc,
      discountType: c.type,
      discountValue: c.value,
      minOrderAmount: c.min,
      maxDiscount: c.max,
      validFrom,
      validUntil,
      usageLimit: c.limit,
      perUserLimit: c.perUser,
      applicableShops: [],
      applicableCategories: [],
      createdBy: adminCreator._id,
      isActive: true,
    });
  }
  console.log(`  Created ${COUPON_DEFS.length} coupons`);

  // ── 9. Create support tickets ──────────────────────────────────────
  const SupportTicket = (await import("./models/supportTicket.model.js")).default;
  const TICKET_SUBJECTS = [
    { subject: "Payment not received for last 3 orders", description: "I have completed 3 deliveries but payment is pending in my wallet.", role: "deliveryBoy" },
    { subject: "Menu not updating on customer app", description: "I updated my menu items 2 days ago but customers still see old prices.", role: "owner" },
    { subject: "Wrong customer address causing failed deliveries", description: "Multiple orders have wrong pin locations. Need GPS fix support.", role: "deliveryBoy" },
    { subject: "Restaurant listing shows wrong cuisine type", description: "My restaurant is listed as Chinese but we serve South Indian food.", role: "owner" },
    { subject: "Unable to go online for deliveries", description: "App shows error when I try to toggle online status.", role: "deliveryBoy" },
    { subject: "Customer complaint on food quality", description: "A customer complained about cold food but it was dispatched hot. Need delivery time investigation.", role: "owner" },
  ];
  for (let i = 0; i < TICKET_SUBJECTS.length; i++) {
    const t = TICKET_SUBJECTS[i];
    const raiser = t.role === "owner" ? owners[i % owners.length] : riders[i % riders.length];
    const shopRef = t.role === "owner" ? allShops[i % allShops.length]._id : null;
    await SupportTicket.create({
      raisedBy: raiser._id,
      role: t.role,
      shop: shopRef,
      subject: t.subject,
      description: t.description,
      status: i < 2 ? "resolved" : i < 4 ? "in-progress" : "open",
      adminNote: i < 2 ? "Issue resolved and credited." : i < 4 ? "Looking into it." : "",
      resolvedBy: i < 2 ? admins[0]._id : null,
    });
  }
  console.log(`  Created ${TICKET_SUBJECTS.length} support tickets`);

  // ── Summary ────────────────────────────────────────────────────────
  const totalUsers = await User.countDocuments();
  const totalShops = await Shop.countDocuments();
  const totalItems = await Item.countDocuments();
  const totalOrders = await Order.countDocuments();
  const totalReviews = await Review.countDocuments();
  const totalCoupons = await Coupon.countDocuments();
  const totalAssignments = await DeliveryAssignment.countDocuments();
  const totalTickets = await SupportTicket.countDocuments();

  console.log("\n=== Database Summary ===");
  console.log(`  Admins:       ${admins.length}`);
  console.log(`  Owners:       ${owners.length} (${owners.length - gunturOwners.length} Hyd + ${gunturOwners.length} Guntur)`);
  console.log(`  Users:        ${users.length}`);
  console.log(`  Riders:       ${riders.length}`);
  console.log(`  Shops:        ${totalShops}`);
  console.log(`  Items:        ${totalItems}`);
  console.log(`  Orders:       ${totalOrders}`);
  console.log(`  Reviews:      ${totalReviews}`);
  console.log(`  Coupons:      ${totalCoupons}`);
  console.log(`  Assignments:  ${totalAssignments}`);
  console.log(`  Tickets:      ${totalTickets}`);
  console.log("Done! Seed data pushed to MongoDB.");

  await mongoose.disconnect();
}

seed().catch((err) => {
  console.error("Seed error:", err);
  process.exit(1);
});
