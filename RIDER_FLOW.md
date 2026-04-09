# Rider (Delivery Boy) Flow - Complete Guide

## Overview
The rider flow encompasses the complete delivery lifecycle from receiving order assignments to completing deliveries with OTP verification.

---

## 1. Authentication
**Entry Point:** User login with role `deliveryBoy`

**Seed Credentials:**
```
Email: seed_rider_0@test.com
Password: Test@1234
Role: deliveryBoy
Mobile: 6000010010
```

**Available Riders (Hyderabad):**
- `seed_rider_0@test.com` - Online ✓
- `seed_rider_1@test.com` - Online ✓
- `seed_rider_2@test.com` - Online ✓
- ... (10 total)

---

## 2. Dashboard Components

### A. Available Assignments (Pending Orders)
- **Endpoint:** `GET /api/order/get-assignments`
- **Purpose:** Fetch all broadcasted delivery assignments for the rider
- **Response Format:**
```json
[
  {
    "assignmentId": "ObjectId",
    "orderId": "ObjectId",
    "shopName": "Restaurant Name",
    "deliveryAddress": {
      "text": "Address",
      "latitude": 17.44,
      "longitude": 78.35
    },
    "items": [...],
    "subtotal": 500
  }
]
```

---

## 3. Accepting an Order

### Step 1: View Available Assignments
1. Rider opens the dashboard
2. Sees list of available orders via `get-assignments` endpoint
3. Each assignment shows:
   - Shop name
   - Delivery address
   - Items to be delivered
   - Order subtotal

### Step 2: Accept Order
- **Endpoint:** `GET /api/order/accept-order/:assignmentId`
- **Validation:**
  - Assignment status must be "brodcasted"
  - Rider cannot have another active assignment
- **Changes on Backend:**
  - Sets `assignedTo` = current rider ID
  - Sets status from "brodcasted" → "assigned"
  - Records `acceptedAt` timestamp

### Step 3: Get Current Order
- **Endpoint:** `GET /api/order/get-current-order`
- **Returns:** Current active order details including:
  - Complete order object
  - Shop details
  - Delivery address
  - Associated items

---

## 4. Real-Time Location Tracking

### Frontend Implementation (DeliveryBoy.jsx)
```javascript
// Watches rider's GPS location continuously
navigator.geolocation.watchPosition((position) => {
  const { latitude, longitude } = position.coords
  socket.emit('updateLocation', {
    latitude,
    longitude,
    userId: userData._id
  })
}, ...)
```

### Socket Events
- **Event:** `updateLocation`
- **Frequency:** Continuous (every position change)
- **Data Sent:** { latitude, longitude, userId }
- **Purpose:** Real-time tracking for users and admins

---

## 5. Route Optimization (AI Integration)

### Hook: `useRouteOptimization()`
- **Purpose:** Optimize delivery route using AI-Layer
- **Debounced:** Updates only when location changes significantly
- **Returns:**
  - `route`: Optimized waypoints
  - `routeLoading`: Loading state
  - `optimiseRoute()`: Function to trigger optimization

### AI-Layer Integration
- **Service:** ETA-Predictor module
- **Inputs:** Current location, destination, traffic conditions
- **Outputs:** Optimized route with waypoints

---

## 6. Order Delivery Process

### Step 1: Arrive at Delivery Location
- Rider navigates to customer address
- Real-time location tracking continuously updates

### Step 2: Send OTP to Customer
- **Endpoint:** `POST /api/order/send-delivery-otp`
- **Request Body:**
```json
{
  "orderId": "ObjectId",
  "shopOrderId": "ObjectId"
}
```
- **Backend Actions:**
  - Generates random 4-digit OTP
  - Sets OTP validity to 5 minutes
  - Sends OTP via email to customer
  - Stores OTP in order document

### Step 3: Verify OTP & Complete Delivery
- **Endpoint:** `POST /api/order/verify-delivery-otp`
- **Request Body:**
```json
{
  "orderId": "ObjectId",
  "shopOrderId": "ObjectId",
  "otp": "1234"
}
```
- **Validation:**
  - OTP must match (case-sensitive)
  - OTP must not be expired (5 min window)
- **On Success:**
  - Sets shop order status → "delivered"
  - Records `deliveredAt` timestamp
  - Deletes delivery assignment record
  - Returns confirmation message
- **Response:**
```json
{
  "message": "Order Delivered Successfully!"
}
```

---

## 7. Analytics & Earnings

### Today's Deliveries
- **Endpoint:** `GET /api/order/get-today-deliveries`
- **Returns:** Hourly delivery statistics
- **Response Format:**
```json
[
  { "hour": 10, "count": 2 },
  { "hour": 11, "count": 3 },
  { "hour": 12, "count": 5 }
]
```

### Earnings Calculation
- **Rate:** ₹50 per delivery
- **Formula:** `totalEarning = todayDeliveries.reduce((sum, d) => sum + d.count * 50, 0)`
- **Display:** Bar chart showing deliveries per hour + total earnings

---

## 8. Order Status Flow

### Delivery Assignment States
```
brodcasted  →  assigned  →  completed
  (Open)       (Accepted)   (Delivered)
```

### Shop Order States (Relevant to Rider)
```
pending  →  cooking  →  ready  →  out_for_delivery  →  delivered
                                        ↑
                              Rider picks up and delivers
```

---

## 9. Socket Events

### Incoming Events (for Rider)
- **`newAssignment`**: New order broadcasted to rider
  - Triggered when owner marks order as "ready"
  - Automatically updates available assignments list

### Outgoing Events (from Rider)
- **`updateLocation`**: Send current GPS coordinates
  - Emitted continuously via `watchPosition`
  - Used for real-time tracking display

---

## 10. Testing the Rider Flow

### Quick Test Steps:

1. **Login as Rider**
   ```
   Email: seed_rider_0@test.com
   Password: Test@1234
   ```

2. **Check Available Assignments**
   - Should see orders marked "ready" by shop owners
   - Or create new orders via user account

3. **Accept an Order**
   - Click accept button on assignment
   - Verify status changes to assigned

4. **Send OTP**
   - Navigate to customer address (or simulate)
   - Click "Send OTP" button
   - Check email for OTP

5. **Verify OTP & Complete**
   - Enter received OTP
   - Confirm delivery
   - See earnings update

---

## 11. Database Models

### User Model (deliveryBoy role)
```javascript
{
  fullName: String,
  email: String,
  role: "deliveryBoy",
  mobile: String,
  isOnline: Boolean,
  location: { type: GeoJSON Point, coordinates: [lon, lat] },
  socketId: String  // For WebSocket tracking
}
```

### DeliveryAssignment Model
```javascript
{
  order: ObjectId (ref: Order),
  shop: ObjectId (ref: Shop),
  shopOrderId: ObjectId,
  brodcastedTo: [ObjectId],  // Riders who can see this
  assignedTo: ObjectId,      // Rider who accepted it
  status: "brodcasted|assigned|completed",
  acceptedAt: Date,
  
  // AI-Layer fields
  aiAllocatedDriver: String,
  aiOptimizationScore: Number,
  predictedDeliveryTime: String,
  optimisedRoute: [{ lat, lon }]
}
```

---

## 12. AI-Layer Integration

### Modules Involved
- **ETA-Predictor:** Predicts delivery time
- **Driver-Allocation:** Allocates optimal rider for order
- **Route-Optimization:** Optimizes delivery route

### Data Passed to AI
- Current location coordinates
- Destination coordinates
- Weather conditions (mocked: "Clear")
- Traffic level (mocked: medium = 3)
- Order size (Small/Medium/Large)
- Time of day
- Day of week

---

## 13. Error Handling

### Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| "assignment is expired" | Someone else accepted it | Fetch new assignments |
| "You are already assigned to another order" | Rider has active order | Complete current order first |
| "Invalid/Expired Otp" | Wrong OTP or 5+ min passed | Ask customer for new OTP |
| "MongoDB timeout" | Connection issue | Check MongoDB Atlas status |
| "assignment not found" | Deleted or invalid ID | Refresh assignments |

---

## 14. Performance Metrics

### For Admin Dashboard
- **Deliveries Completed Today:** Count of "delivered" orders
- **Earnings:** ₹50 × deliveries count
- **Active Riders:** Count of riders with `isOnline: true`
- **Average Delivery Time:** From accepted to delivered
- **Completion Rate:** Delivered / Assigned orders

---

## 15. Frontend Components

### DeliveryBoy.jsx
Main rider dashboard component with:
- Available assignments list
- Current order details
- Real-time location tracking
- OTP sending & verification
- Today's delivery analytics
- Earnings display
- Route optimization integration

### DeliveryBoyTracking.jsx
Maps component showing:
- Rider's current location
- Customer's delivery address
- Optimized route (if available)
- Live tracking updates

---

## Summary

**Rider Flow Steps:**
1. ✅ Login as deliveryBoy
2. ✅ View available assignments (broadcasted orders)
3. ✅ Accept an order (set as assigned)
4. ✅ Track location in real-time
5. ✅ Navigate to customer (with optimized route)
6. ✅ Send OTP to customer
7. ✅ Verify OTP & confirm delivery
8. ✅ View today's earnings & statistics
9. ✅ Repeat for next assignment

**Key Endpoints:**
- `GET /api/order/get-assignments` - List available orders
- `GET /api/order/accept-order/:assignmentId` - Accept order
- `GET /api/order/get-current-order` - Get active order
- `POST /api/order/send-delivery-otp` - Send OTP
- `POST /api/order/verify-delivery-otp` - Verify & complete
- `GET /api/order/get-today-deliveries` - Earnings data

---

**Last Updated:** April 6, 2026
