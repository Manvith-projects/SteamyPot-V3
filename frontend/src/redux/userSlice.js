import { createSlice, current } from "@reduxjs/toolkit";

const userSlice = createSlice({
  name: "user",
  initialState: {
    userData: null,
    currentCity: null,
    currentState: null,
    currentAddress: null,
    shopInMyCity: null,
    itemsInMyCity: null,
    cartItems: [],
    totalAmount: 0,
    myOrders: [],
    searchItems: null,
    recommendedItems: [],
    contactRecommendedItems: [],
    contactNames: [],
    // socket: null, // removed from state
    favorites: [],
    // ── AI-Layer state ──
    foodAssistantResults: null,
    foodAssistantLoading: false,
    etaPrediction: null,
    dynamicPricing: null,
    churnData: null,
    reviewSummary: null,
    aiHealthStatus: null,
    optimisedRoute: null
  },
  reducers: {
            addFavorite: (state, action) => {
              if (!state.favorites.includes(action.payload)) {
                state.favorites.push(action.payload)
              }
            },
            removeFavorite: (state, action) => {
              state.favorites = state.favorites.filter(id => id !== action.payload)
            },
        hideMyOrder: (state, action) => {
          state.myOrders = state.myOrders.filter(o => o._id !== action.payload)
        },
    setUserData: (state, action) => {
      state.userData = action.payload
    },
    clearUserData: (state) => {
      state.userData = null;
      state.currentCity = null;
      state.currentState = null;
      state.currentAddress = null;
      state.shopInMyCity = null;
      state.itemsInMyCity = null;
      state.cartItems = [];
      state.totalAmount = 0;
      state.myOrders = [];
      state.searchItems = null;
      state.recommendedItems = [];
      state.contactRecommendedItems = [];
      state.contactNames = [];
      state.socket = null;
      state.foodAssistantResults = null;
      state.foodAssistantLoading = false;
      state.etaPrediction = null;
      state.dynamicPricing = null;
      state.churnData = null;
      state.reviewSummary = null;
      state.aiHealthStatus = null;
      state.optimisedRoute = null;
    },
    setCurrentCity: (state, action) => {
      state.currentCity = action.payload
    },
    setCurrentState: (state, action) => {
      state.currentState = action.payload
    },
    setCurrentAddress: (state, action) => {
      state.currentAddress = action.payload
    },
    setShopsInMyCity: (state, action) => {
      state.shopInMyCity = action.payload
    },
    setItemsInMyCity: (state, action) => {
      state.itemsInMyCity = action.payload
    },
    addToCart: (state, action) => {
      const cartItem = action.payload
      const existingItem = state.cartItems.find(i => i.id == cartItem.id)
      if (existingItem) {
        existingItem.quantity += cartItem.quantity
      } else {
        state.cartItems.push(cartItem)
      }

      state.totalAmount = state.cartItems.reduce((sum, i) => sum + i.price * i.quantity, 0)

    },

    setTotalAmount: (state, action) => {
      state.totalAmount = action.payload
    }

    ,

    updateQuantity: (state, action) => {
      const { id, quantity } = action.payload
      const item = state.cartItems.find(i => i.id == id)
      if (item) {
        item.quantity = quantity
      }
      state.totalAmount = state.cartItems.reduce((sum, i) => sum + i.price * i.quantity, 0)
    },

    removeCartItem: (state, action) => {
      state.cartItems = state.cartItems.filter(i => i.id !== action.payload)
      state.totalAmount = state.cartItems.reduce((sum, i) => sum + i.price * i.quantity, 0)
    },
    clearCart: (state) => {
      state.cartItems = []
      state.totalAmount = 0
    },

    setMyOrders: (state, action) => {
      state.myOrders = action.payload
    },
    addMyOrder: (state, action) => {
      state.myOrders = [action.payload, ...state.myOrders]
    }

    ,
    updateOrderStatus: (state, action) => {
      const { orderId, shopId, status } = action.payload
      const order = state.myOrders.find(o => o._id == orderId)
      if (order) {
        if (order.shopOrders && order.shopOrders.shop._id == shopId) {
          order.shopOrders.status = status
        }
      }
    },

    updateRealtimeOrderStatus: (state, action) => {
      const { orderId, shopId, status } = action.payload
      const order = state.myOrders.find(o => o._id == orderId)
      if (order) {
        const shopOrder = order.shopOrders.find(so => so.shop._id == shopId)
        if (shopOrder) {
          shopOrder.status = status
        }
      }
    },

    setSearchItems: (state, action) => {
      state.searchItems = action.payload
    },
    setRecommendedItems: (state, action) => {
      state.recommendedItems = action.payload
    },
    setContactRecommendedItems: (state, action) => {
      state.contactRecommendedItems = action.payload.items || []
      state.contactNames = action.payload.contactNames || []
    },
    // ── AI-Layer reducers ──
    setFoodAssistantResults: (state, action) => {
      state.foodAssistantResults = action.payload
    },
    setFoodAssistantLoading: (state, action) => {
      state.foodAssistantLoading = action.payload
    },
    setEtaPrediction: (state, action) => {
      state.etaPrediction = action.payload
    },
    setDynamicPricing: (state, action) => {
      state.dynamicPricing = action.payload
    },
    setChurnData: (state, action) => {
      state.churnData = action.payload
    },
    setReviewSummary: (state, action) => {
      state.reviewSummary = action.payload
    },
    setAiHealthStatus: (state, action) => {
      state.aiHealthStatus = action.payload
    },
    setOptimisedRoute: (state, action) => {
      state.optimisedRoute = action.payload
    }
  }
})

export const { setUserData, clearUserData, setCurrentAddress, setCurrentCity, setCurrentState, setShopsInMyCity, setItemsInMyCity, addToCart, updateQuantity, removeCartItem, clearCart, setMyOrders, addMyOrder, updateOrderStatus, setSearchItems, setRecommendedItems, setContactRecommendedItems, setTotalAmount, setSocket, updateRealtimeOrderStatus, setFoodAssistantResults, setFoodAssistantLoading, setEtaPrediction, setDynamicPricing, setChurnData, setReviewSummary, setAiHealthStatus, setOptimisedRoute } = userSlice.actions
export default userSlice.reducer