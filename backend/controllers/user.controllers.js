import User from "../models/user.model.js"
import uploadOnCloudinary from "../utils/cloudinary.js"
import bcrypt from "bcryptjs"

export const getCurrentUser=async (req,res) => {
    try {
        const userId=req.userId
        if(!userId){
            return res.status(400).json({message:"userId is not found"})
        }
        const user=await User.findById(userId)
        if(!user){
               return res.status(400).json({message:"user is not found"})
        }
        return res.status(200).json(user)
    } catch (error) {
        return res.status(500).json({message:`get current user error ${error}`})
    }
}

export const updateUserLocation=async (req,res) => {
    try {
        const {lat,lon}=req.body
        const user=await User.findByIdAndUpdate(req.userId,{
            location:{
                type:'Point',
                coordinates:[lon,lat]
            }
        },{new:true})
         if(!user){
               return res.status(400).json({message:"user is not found"})
        }
        
        return res.status(200).json({message:'location updated'})
    } catch (error) {
           return res.status(500).json({message:`update location user error ${error}`})
    }
}

export const updateProfile = async (req, res) => {
    try {
        const { fullName, mobile } = req.body
        const updates = {}
        if (fullName) updates.fullName = fullName
        if (mobile) updates.mobile = mobile

        if (req.file) {
            const imageUrl = await uploadOnCloudinary(req.file.path)
            if (imageUrl) updates.profileImage = imageUrl
        }

        const user = await User.findByIdAndUpdate(req.userId, updates, { new: true }).select("-password")
        if (!user) return res.status(400).json({ message: "user not found" })

        return res.status(200).json(user)
    } catch (error) {
        return res.status(500).json({ message: `update profile error ${error}` })
    }
}

export const changePassword = async (req, res) => {
    try {
        const { currentPassword, newPassword } = req.body
        if (!currentPassword || !newPassword) {
            return res.status(400).json({ message: "current and new password required" })
        }
        const user = await User.findById(req.userId)
        if (!user) return res.status(400).json({ message: "user not found" })

        const isMatch = await bcrypt.compare(currentPassword, user.password)
        if (!isMatch) return res.status(400).json({ message: "current password is incorrect" })

        const hashed = await bcrypt.hash(newPassword, 10)
        user.password = hashed
        await user.save()

        return res.status(200).json({ message: "password changed successfully" })
    } catch (error) {
        return res.status(500).json({ message: `change password error ${error}` })
    }
}

export const uploadContacts = async (req, res) => {
    try {
        const { contacts } = req.body
        if (!contacts || !Array.isArray(contacts)) {
            return res.status(400).json({ message: "contacts array required" })
        }

        const user = await User.findByIdAndUpdate(
            req.userId,
            { contacts },
            { new: true }
        ).select("-password")

        if (!user) return res.status(400).json({ message: "user not found" })
        return res.status(200).json(user)
    } catch (error) {
        return res.status(500).json({ message: `upload contacts error ${error}` })
    }
}

export const deleteAccount = async (req, res) => {
    try {
        await User.findByIdAndDelete(req.userId)
        res.clearCookie("token")
        return res.status(200).json({ message: "account deleted" })
    } catch (error) {
        return res.status(500).json({ message: `delete account error ${error}` })
    }
}

export const addFavorite = async (req, res) => {
  try {
    const userId = req.userId;
    const { itemId } = req.body;
    if (!itemId) return res.status(400).json({ message: 'itemId required' });
    const user = await User.findById(userId);
    if (!user) return res.status(404).json({ message: 'User not found' });
    if (!user.favorites.includes(itemId)) {
      user.favorites.push(itemId);
      await user.save();
    }
    return res.status(200).json({ favorites: user.favorites });
  } catch (error) {
    return res.status(500).json({ message: `add favorite error ${error}` });
  }
};

export const removeFavorite = async (req, res) => {
  try {
    const userId = req.userId;
    const { itemId } = req.body;
    if (!itemId) return res.status(400).json({ message: 'itemId required' });
    const user = await User.findById(userId);
    if (!user) return res.status(404).json({ message: 'User not found' });
    user.favorites = user.favorites.filter(id => id.toString() !== itemId);
    await user.save();
    return res.status(200).json({ favorites: user.favorites });
  } catch (error) {
    return res.status(500).json({ message: `remove favorite error ${error}` });
  }
};
