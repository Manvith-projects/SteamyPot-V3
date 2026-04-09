import { configureStore } from "@reduxjs/toolkit";
import userSlice from "./userSlice"
import ownerSlice from "./ownerSlice"
import adminSlice from "./adminSlice"
import mapSlice from "./mapSlice"
import {
    persistStore,
    persistReducer,
    FLUSH,
    REHYDRATE,
    PAUSE,
    PERSIST,
    PURGE,
    REGISTER,
} from 'redux-persist';
import storage from 'redux-persist/lib/storage';

const userPersistConfig = {
    key: 'user',
    storage,
    whitelist: ['userData', 'currentCity', 'currentState', 'currentAddress', 'shopInMyCity', 'itemsInMyCity', 'myOrders', 'cartItems', 'totalAmount', 'favorites'] // DO NOT include 'socket'
};
const ownerPersistConfig = {
    key: 'owner',
    storage,
    whitelist: ['myShopData']
};

export const store = configureStore({
    reducer: {
        user: persistReducer(userPersistConfig, userSlice),
        owner: persistReducer(ownerPersistConfig, ownerSlice),
        admin: adminSlice,
        map: mapSlice
    },
    middleware: (getDefaultMiddleware) =>
        getDefaultMiddleware({
            serializableCheck: {
                ignoredActions: [FLUSH, REHYDRATE, PAUSE, PERSIST, PURGE, REGISTER],
            },
        }),
});

export const persistor = persistStore(store);