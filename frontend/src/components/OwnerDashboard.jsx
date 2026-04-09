import React from 'react'
import Nav from './Nav'
import { useSelector, useDispatch } from 'react-redux'
import { setMyShopData } from '../redux/ownerSlice'
import axios from 'axios'
import { serverUrl } from '../App'
import { FaChartBar, FaStar, FaMoneyBillWave, FaPlus, FaPen, FaReceipt } from 'react-icons/fa';
import { useNavigate } from 'react-router-dom';
import OwnerItemCard from './OwnerItemCard';
function OwnerDashboard() {
  const { myShopData } = useSelector(state => state.owner)
  const dispatch = useDispatch()

  const handleToggleAvailability = async (itemId) => {
    try {
      const result = await axios.get(`${serverUrl}/api/item/toggle-availability/${itemId}`, { withCredentials: true })
      dispatch(setMyShopData(result.data))
    } catch (error) {
      console.log(error)
    }
  }

  // Example insights (replace with real data as needed)
  const insights = myShopData ? {
    totalOrders: myShopData.orders?.length || 0,
    totalRevenue: myShopData.orders?.reduce((sum, o) => sum + (o.totalAmount || 0), 0),
    topItem: myShopData.items?.[0]?.name || 'N/A',
    avgRating: myShopData.avgRating || 4.5
  } : null;
  const navigate = useNavigate()

  
  return (
    <div className='w-full min-h-screen bg-gradient-to-br from-[#18181c] via-[#23232a] to-[#0b0b0f] flex flex-col items-center'>
      <Nav />
      {myShopData && (
        <div className='w-full max-w-6xl mt-8 mb-4 grid grid-cols-1 lg:grid-cols-3 gap-8'>
          {/* Analytics Card */}
          <div className='bg-[#18181c] rounded-2xl shadow-2xl p-8 border border-[#24242c] flex flex-col gap-4 hover:scale-[1.02] transition-transform'>
            <h2 className='text-xl font-bold text-[#ff4d2d] flex items-center gap-2 mb-2'><FaChartBar /> Analytics</h2>
            <div className='flex flex-col gap-3 text-gray-200'>
              <div className='flex justify-between items-center'>
                <span>Total Orders</span>
                <span className='font-bold text-white text-lg'>{insights.totalOrders}</span>
              </div>
              <div className='flex justify-between items-center'>
                <span>Total Revenue</span>
                <span className='font-bold text-white text-lg'>₹{insights.totalRevenue}</span>
              </div>
              <div className='flex justify-between items-center'>
                <span>Top Item</span>
                <span className='font-bold text-white text-lg'>{insights.topItem}</span>
              </div>
              <div className='flex justify-between items-center'>
                <span>Average Rating</span>
                <span className='font-bold text-white text-lg flex items-center gap-1'>{insights.avgRating} <FaStar className='text-yellow-400' /></span>
              </div>
            </div>
            {/* Placeholder for chart */}
            <div className='mt-4 h-24 bg-gradient-to-r from-[#ff4d2d]/30 to-[#fff]/5 rounded-lg flex items-center justify-center text-gray-400 text-sm'>
              [Chart Placeholder]
            </div>
          </div>
          {/* Shop Info Card */}
          <div className='bg-[#18181c] rounded-2xl shadow-2xl p-8 border border-[#24242c] flex flex-col gap-4 hover:scale-[1.02] transition-transform'>
            <h2 className='text-xl font-bold text-[#ff4d2d] mb-2'>Shop Details</h2>
            <img src={myShopData.image} alt={myShopData.name} className='w-full h-32 object-cover rounded-lg mb-2'/>
            <div className='text-2xl font-bold text-white'>{myShopData.name}</div>
            <div className='text-gray-400'>{myShopData.city}, {myShopData.state}</div>
            <div className='text-gray-400'>{myShopData.address}</div>
            <div className='flex gap-2 mt-2'>
              <button className='bg-[#ff4d2d] text-white px-4 py-2 rounded-full font-medium shadow-md hover:bg-orange-600 transition-colors duration-200 flex items-center gap-2' onClick={()=>navigate('/create-edit-shop')}><FaPen />Edit Shop</button>
              <button className='bg-[#23232a] text-white px-4 py-2 rounded-full font-medium shadow-md hover:bg-[#ff4d2d]/80 transition-colors duration-200 flex items-center gap-2' onClick={()=>navigate('/add-item')}><FaPlus />Add Item</button>
              <button className='bg-[#23232a] text-white px-4 py-2 rounded-full font-medium shadow-md hover:bg-[#ff4d2d]/80 transition-colors duration-200 flex items-center gap-2' onClick={()=>navigate('/my-orders')}><FaReceipt />Orders</button>
            </div>
          </div>
          {/* Quick Stats Card */}
          <div className='bg-[#18181c] rounded-2xl shadow-2xl p-8 border border-[#24242c] flex flex-col gap-4 hover:scale-[1.02] transition-transform'>
            <h2 className='text-xl font-bold text-[#ff4d2d] mb-2'>Quick Stats</h2>
            <div className='flex flex-col gap-3 text-gray-200'>
              <div className='flex justify-between items-center'>
                <span>Menu Items</span>
                <span className='font-bold text-white text-lg'>{myShopData.items.length}</span>
              </div>
              <div className='flex justify-between items-center'>
                <span>Active Since</span>
                <span className='font-bold text-white text-lg'>{new Date(myShopData.createdAt).toLocaleDateString()}</span>
              </div>
              <div className='flex justify-between items-center'>
                <span>Pending Orders</span>
                <span className='font-bold text-white text-lg'>{myShopData.orders?.filter(o => o.status === 'pending').length || 0}</span>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Menu Section */}
      {myShopData && (
        <div className='w-full max-w-6xl mt-8'>
          <h2 className='text-2xl font-bold text-[#ff4d2d] mb-6'>Menu</h2>
          {myShopData.items.length === 0 ? (
            <div className='flex justify-center items-center p-4 sm:p-6'>
              <div className='w-full max-w-md bg-[#14141a] shadow-lg rounded-2xl p-6 border border-[#24242c] hover:shadow-xl transition-shadow duration-300'>
                <div className='flex flex-col items-center text-center'>
                  <FaUtensils className='text-[#ff4d2d] w-16 h-16 sm:w-20 sm:h-20 mb-4' />
                  <h2 className='text-xl sm:text-2xl font-bold text-gray-100 mb-2'>Add Your Food Item</h2>
                  <p className='text-gray-400 mb-4 text-sm sm:text-base'>Share your delicious creations with our customers by adding them to the menu.</p>
                  <button className='bg-[#ff4d2d] text-white px-5 sm:px-6 py-2 rounded-full font-medium shadow-md hover:bg-orange-600 transition-colors duration-200' onClick={() => navigate('/add-item')}>
                    Add Food
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6'>
              {myShopData.items.map((item) => (
                <div className='bg-[#23232a] rounded-xl shadow-lg p-6 flex flex-col gap-2 hover:scale-[1.02] transition-transform' key={item._id}>
                  <OwnerItemCard data={item} />
                  <div className='flex justify-between items-center mt-2'>
                    <span className='text-gray-400 text-sm'>Sales: {item.sales || 0}</span>
                    <button onClick={() => handleToggleAvailability(item._id)} className={`px-2 py-1 rounded-full text-xs font-bold cursor-pointer transition hover:opacity-80 ${item.available !== false ? 'bg-green-600 text-white' : 'bg-red-600 text-white'}`}>{item.available !== false ? 'Available' : 'Out of Stock'}</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {!myShopData && (
        <div className='flex justify-center items-center p-4 sm:p-6'>
          <div className='w-full max-w-md bg-[#14141a] shadow-lg rounded-2xl p-6 border border-[#24242c] hover:shadow-xl transition-shadow duration-300'>
            <div className='flex flex-col items-center text-center'>
              <FaUtensils className='text-[#ff4d2d] w-16 h-16 sm:w-20 sm:h-20 mb-4' />
              <h2 className='text-xl sm:text-2xl font-bold text-gray-100 mb-2'>Add Your Restaurant</h2>
              <p className='text-gray-400 mb-4 text-sm sm:text-base'>Join our food delivery platform and reach thousands of hungry customers every day.</p>
              <button className='bg-[#ff4d2d] text-white px-5 sm:px-6 py-2 rounded-full font-medium shadow-md hover:bg-orange-600 transition-colors duration-200' onClick={() => navigate('/create-edit-shop')}>
                Get Started
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default OwnerDashboard
