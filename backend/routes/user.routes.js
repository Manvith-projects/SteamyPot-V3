import express from "express"
import { getCurrentUser, updateUserLocation, updateProfile, changePassword, uploadContacts, deleteAccount, addFavorite, removeFavorite } from "../controllers/user.controllers.js"
import { isAuth } from "../middlewares/isAuth.js"
import { upload } from "../middlewares/multer.js"


const userRouter=express.Router()

userRouter.get("/current",isAuth,getCurrentUser)
userRouter.post('/update-location',isAuth,updateUserLocation)
userRouter.put('/update-profile',isAuth,upload.single("profileImage"),updateProfile)
userRouter.put('/change-password',isAuth,changePassword)
userRouter.put('/contacts',isAuth,uploadContacts)
userRouter.delete('/delete-account',isAuth,deleteAccount)
userRouter.post('/favorites/add', isAuth, addFavorite);
userRouter.post('/favorites/remove', isAuth, removeFavorite);
export default userRouter