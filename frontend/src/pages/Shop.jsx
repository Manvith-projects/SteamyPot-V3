import axios from 'axios'
import React, { useEffect, useState } from 'react'
import { serverUrl } from '../App'
import { useNavigate, useParams } from 'react-router-dom'
import { FaStore } from "react-icons/fa6";
import { FaLocationDot } from "react-icons/fa6";
import { FaUtensils } from "react-icons/fa";
import FoodCard from '../components/FoodCard';
import Nav from '../components/Nav';
import { FaArrowLeft } from "react-icons/fa";
import useReviewSummary from '../hooks/useReviewSummary';
function Shop() {
    const {shopId}=useParams()
    const [items,setItems]=useState([])
    const [shop,setShop]=useState([])
    const navigate=useNavigate()
    const { reviewSummary, reviewLoading, summarizeReviews } = useReviewSummary()

    const handleShop=async () => {
        try {
           const result=await axios.get(`${serverUrl}/api/item/get-by-shop/${shopId}`,{withCredentials:true}) 
           setShop(result.data.shop)
           setItems(result.data.items)
        } catch (error) {
            console.log(error)
        }
    }

    useEffect(()=>{
handleShop()
summarizeReviews(shopId)
    },[shopId])
    return (
        <>
        <Nav />
        <div className='min-h-screen' style={{background: 'var(--bg)', backgroundImage: 'radial-gradient(circle at 20% 30%, var(--accent-soft) 0%, transparent 60%), radial-gradient(circle at 80% 70%, var(--accent-soft) 0%, transparent 60%)', color: 'var(--text)'}}>
        <button className='absolute top-4 left-4 z-20 flex items-center gap-2 bg-black/50 hover:bg-black/70 text-white px-3 py-2 rounded-full shadow-md transition' onClick={()=>navigate("/")}> 
        <FaArrowLeft />
<span>Back</span>
        </button>
      {shop && <div className='relative w-full h-64 md:h-80 lg:h-96'>
          <img src={shop.image} alt="" className='w-full h-full object-cover'/>
          <div className='absolute inset-0 bg-gradient-to-b from-black/70 to-black/30 flex flex-col justify-center items-center text-center px-4'>
          <FaStore className='text-white text-4xl mb-3 drop-shadow-md'/>
          <h1 className='text-3xl md:text-5xl font-extrabold text-white drop-shadow-lg'>{shop.name}</h1>
          <div className='flex items-center  gap-[10px]'>
          <FaLocationDot size={22} color='red'/>
             <p className='text-lg font-medium text-gray-200 mt-[10px]'>{shop.address}</p>
             </div>
          </div>
       
        </div>}

<div className='max-w-7xl mx-auto px-6 py-10'>

{/* AI Review Summary */}
{reviewSummary && !reviewLoading && (
  <div className='mb-8 bg-[#14141a] rounded-2xl p-5 border border-[#24242c]'>
    <div className='flex items-center gap-2 mb-3'>
      <span className='text-xl'>📊</span>
      <h3 className='text-lg font-bold text-white'>AI Review Summary</h3>
      <span className='ml-2 px-2 py-0.5 rounded-full bg-[#ff2e2e]/15 text-[#ff2e2e] text-xs font-semibold uppercase'>AI Powered</span>
      {reviewSummary.summary_cache_status && (
        <span className='px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-300 text-[10px] font-semibold uppercase'>
          {reviewSummary.summary_cache_status === 'cached' ? 'Daily Summary' : 'Summary Refreshed'}
        </span>
      )}
      {reviewSummary.cache_status && (
        <span className='px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 text-[10px] font-semibold uppercase'>
          {reviewSummary.cache_status === 'cached' ? 'Daily Index' : 'Index Refreshed'}
        </span>
      )}
    </div>
    {reviewSummary.summary && <p className='text-gray-300 text-sm mb-3'>{reviewSummary.summary}</p>}
    {reviewSummary.cache_refreshed_at && (
      <p className='mb-3 text-[11px] text-gray-500'>
        Review vectors refreshed: {new Date(reviewSummary.cache_refreshed_at).toLocaleString()}
      </p>
    )}
    {reviewSummary.summary_cache_refreshed_at && (
      <p className='mb-3 text-[11px] text-gray-500'>
        Summary refreshed: {new Date(reviewSummary.summary_cache_refreshed_at).toLocaleString()}
      </p>
    )}
    {reviewSummary.overall_sentiment && (
      <div className='flex items-center gap-2 mb-2'>
        <span className='text-sm text-gray-400'>Sentiment:</span>
        <span className={`text-sm font-semibold px-2 py-0.5 rounded-full ${
          reviewSummary.overall_sentiment === 'positive' ? 'bg-green-900/30 text-green-400' :
          reviewSummary.overall_sentiment === 'negative' ? 'bg-red-900/30 text-red-400' :
          'bg-yellow-900/30 text-yellow-400'
        }`}>{reviewSummary.overall_sentiment}</span>
      </div>
    )}
    {reviewSummary.top_positive_points?.length > 0 && (
      <div className='mt-2'>
        <p className='text-xs text-gray-500 mb-1'>Highlights:</p>
        <div className='flex flex-wrap gap-1.5'>
          {reviewSummary.top_positive_points.slice(0, 5).map((p, i) => (
            <span key={i} className='text-[11px] bg-green-900/20 text-green-400 px-2 py-0.5 rounded-full'>✓ {p}</span>
          ))}
        </div>
      </div>
    )}
    {reviewSummary.common_complaints?.length > 0 && (
      <div className='mt-2'>
        <p className='text-xs text-gray-500 mb-1'>Could improve:</p>
        <div className='flex flex-wrap gap-1.5'>
          {reviewSummary.common_complaints.slice(0, 3).map((c, i) => (
            <span key={i} className='text-[11px] bg-red-900/20 text-red-400 px-2 py-0.5 rounded-full'>⚠ {c}</span>
          ))}
        </div>
      </div>
    )}
  </div>
)}
{reviewLoading && (
  <div className='mb-8 bg-[#14141a] rounded-2xl p-5 border border-[#24242c] text-center'>
    <p className='text-gray-400 text-sm animate-pulse'>Loading AI review summary...</p>
  </div>
)}

<h2 className='flex items-center justify-center gap-3 text-3xl font-bold mb-10 text-gray-100'><FaUtensils color='red'/> Our Menu</h2>

{items.length>0?(
    <div className='flex flex-wrap justify-center gap-8'>
        {items.map((item)=>(
            <FoodCard data={item}/>
        ))}
    </div>
):<p className='text-center text-gray-500 text-lg'>No Items Available</p>}
</div>



    </div>
    </>
  )
}

export default Shop
