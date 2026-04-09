import React, { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { IoIosArrowRoundBack } from "react-icons/io";
import { useNavigate } from 'react-router-dom';
import UserOrderCard from '../components/UserOrderCard';
import OwnerOrderCard from '../components/OwnerOrderCard';
import { setMyOrders, updateOrderStatus, updateRealtimeOrderStatus } from '../redux/userSlice';


function MyOrders() {
  const { userData, myOrders,socket} = useSelector(state => state.user)
  const navigate = useNavigate()
const dispatch=useDispatch()
  useEffect(()=>{
socket?.on('newOrder',(data)=>{
if(data.shopOrders?.owner._id==userData._id){
dispatch(setMyOrders([data,...myOrders]))
}
})

socket?.on('update-status',({orderId,shopId,status,userId})=>{
if(userId==userData._id){
  dispatch(updateRealtimeOrderStatus({orderId,shopId,status}))
}
})

return ()=>{
  socket?.off('newOrder')
  socket?.off('update-status')
}
  },[socket])



  
  return (
    <div className='w-full min-h-screen flex justify-center px-4' style={{background: 'var(--bg)', backgroundImage: 'radial-gradient(circle at 20% 30%, var(--accent-soft) 0%, transparent 60%), radial-gradient(circle at 80% 70%, var(--accent-soft) 0%, transparent 60%)'}}>
      <div className='w-full max-w-[800px] p-4' style={{background: 'var(--bg-card)', color: 'var(--text)', borderRadius: '1rem'}}>

        <div className='flex items-center gap-[20px] mb-6 '>
          <div className=' z-[10] ' onClick={() => navigate("/")}>
            <IoIosArrowRoundBack size={35} className='text-[#ff4d2d]' />
          </div>
          <h1 className='text-2xl font-bold text-start' style={{color: 'var(--accent)'}}>My Orders</h1>
        </div>
        <div className='space-y-6'>
          {myOrders?.map((order) => (
            userData.role === "user" ?
              <UserOrderCard data={order} key={order._id} />
            : userData.role === "owner" ?
              <OwnerOrderCard data={order} key={order._id} />
            : null
          ))}
        </div>
      </div>
    </div>
  )
}

export default MyOrders
