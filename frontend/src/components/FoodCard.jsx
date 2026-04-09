import React, { useState, useEffect } from 'react'
import { FaLeaf } from "react-icons/fa";
import { FaDrumstickBite } from "react-icons/fa";
import { FaStar } from "react-icons/fa";
import { FaRegStar, FaRegHeart } from "react-icons/fa6";
import { FaMinus } from "react-icons/fa";
import { FaPlus } from "react-icons/fa";
import { FaShoppingCart } from "react-icons/fa";
import { useDispatch, useSelector } from 'react-redux';
import { addToCart } from '../redux/userSlice';

function FoodCard({data}) {
const {favorites} = useSelector(state=>state.user)
const isFavorite = favorites.includes(data._id)
const handleFavorite = () => {
    if (isFavorite) {
        dispatch({ type: 'user/removeFavorite', payload: data._id })
    } else {
        dispatch({ type: 'user/addFavorite', payload: data._id })
    }
}
const [quantity,setQuantity]=useState(0)
const dispatch=useDispatch()
const {cartItems}=useSelector(state=>state.user)

// Static ETA estimate from shop's avgPrepTime (avoids per-card API calls)
const prepMin = data.shop?.avgPrepTime || 15
const estimatedEta = `${prepMin + 15} - ${prepMin + 25} min`
    const renderStars=(rating)=>{   //r=3
        const stars=[];
        for (let i = 1; i <= 5; i++) {
           stars.push(
            (i<=rating)?(
                <FaStar className='text-yellow-500 text-lg'/>
            ):(
                <FaRegStar className='text-yellow-500 text-lg'/>
            )
           )
            
        }
return stars
    }

const handleIncrease=()=>{
    const newQty=quantity+1
    setQuantity(newQty)
}
const handleDecrease=()=>{
    if(quantity>0){
const newQty=quantity-1
    setQuantity(newQty)
    }
    
}

  return (
                <div className='w-full max-w-[260px] rounded-2xl bg-[#1b1b1b] shadow-lg overflow-hidden hover:shadow-2xl transition-all duration-300 flex flex-col border border-[#252525]'>
                        <div className='relative w-full h-[170px] bg-[#0f0f0f]'>
                                <img src={data.image} alt={data.name} className='w-full h-full object-cover' />
                                <div className='absolute bottom-3 left-3 px-2 py-1 rounded-md bg-[#1c1c1c] border border-[#2b2b2b] flex items-center gap-1 text-[12px] font-semibold text-white shadow'>
                                    <FaStar className='text-[#2dd36f]' />
                                    <span>{Number(data.rating?.average || 0).toFixed(1)}</span>
                                </div>
                                <div className='absolute top-3 right-3 flex flex-col gap-2 items-end'>
                                    <button className={`bg-[#14141a] rounded-full p-2 shadow border border-[#252525] ${isFavorite ? 'text-[#ff2e2e]' : 'text-gray-400'}`} onClick={handleFavorite} title={isFavorite ? 'Remove from Favorites' : 'Add to Favorites'}>
                                        {isFavorite ? <FaRegHeart className='text-[#ff2e2e] text-lg'/> : <FaRegHeart className='text-gray-400 text-lg'/>}
                                    </button>
                                    <div className='bg-[#14141a] rounded-full p-1 shadow'>{data.foodType=="veg"?<FaLeaf className='text-green-500 text-lg'/>:<FaDrumstickBite className='text-red-500 text-lg'/>}</div>
                                </div>
                        </div>

            <div className="flex-1 flex flex-col p-4 gap-2">
                <h1 className='font-bold text-gray-100 text-lg leading-tight truncate'>{data.name}</h1>
                {data.shop?.name && <p className='text-xs text-[#ff2e2e]/80 truncate'>{data.shop.name}</p>}
                <p className='text-sm text-gray-400'>{estimatedEta}</p>
            </div>

            <div className='flex items-center justify-between mt-auto p-4 pt-0'>
                <span className='text-lg font-semibold text-gray-100'>₹{data.price}</span>
                <div className='flex items-center border rounded-full overflow-hidden shadow-sm border-[#2d2d2d] bg-[#1f1f1f]'>
                    <button className='px-2 py-1 hover:bg-[#272727] transition' onClick={handleDecrease}>
                        <FaMinus size={12}/>
                    </button>
                    <span className='px-2 text-gray-100'>{quantity}</span>
                    <button className='px-2 py-1 hover:bg-[#272727] transition' onClick={handleIncrease}>
                        <FaPlus size={12}/>
                    </button>
                    <button className={`${cartItems.some(i=>i.id==data._id)?"bg-gray-800":"bg-[#ff2e2e]"} text-white px-3 py-2 transition-colors`}  onClick={()=>{
                            quantity>0?dispatch(addToCart({
                                id:data._id,
                                name:data.name,
                                price:data.price,
                                image:data.image,
                                shop:data.shop?._id || data.shop,
                                quantity,
                                foodType:data.foodType
                            })):null}}>
                        <FaShoppingCart size={16}/>
                    </button>
                </div>
            </div>

        </div>
  )
}

export default FoodCard
