import React from 'react'
import { useSelector } from 'react-redux'
import UserDashboard from '../components/UserDashboard'
import OwnerDashboard from '../components/OwnerDashboard'
import DeliveryBoy from '../components/DeliveryBoy'
import AdminDashboard from '../components/AdminDashboard'

function Home() {
    const {userData}=useSelector(state=>state.user)
    
    if (!userData) {
      return (
        <div className='w-[100vw] min-h-[100vh] pt-[100px] flex flex-col items-center justify-center' style={{background: 'var(--bg)', backgroundImage: 'radial-gradient(circle at 20% 30%, var(--accent-soft) 0%, transparent 60%), radial-gradient(circle at 80% 70%, var(--accent-soft) 0%, transparent 60%)'}}>
          <div className='text-red-500 text-center'>
            <p className='text-xl font-bold mb-4'>Error: No user data found</p>
            <p className='text-gray-300 mb-4'>Please log in again</p>
            <p className='text-sm text-gray-400'>Check localStorage: {localStorage.getItem('persist:user') ? 'Found' : 'Not found'}</p>
            <button 
              onClick={() => window.location.href = '/signin'}
              className='mt-4 px-6 py-2 bg-red-600 rounded-lg hover:bg-red-700'
            >
              Go to Login
            </button>
          </div>
        </div>
      )
    }
    
  return (
    <div className='w-[100vw] min-h-[100vh] pt-[100px] flex flex-col items-center' style={{background: 'var(--bg)', backgroundImage: 'radial-gradient(circle at 20% 30%, var(--accent-soft) 0%, transparent 60%), radial-gradient(circle at 80% 70%, var(--accent-soft) 0%, transparent 60%)'}}>
      {userData.role=="user" && <UserDashboard/>}
      {userData.role=="owner" && <OwnerDashboard/>}
      {userData.role=="deliveryBoy" && <DeliveryBoy/>}
      {userData.role=="admin" && <AdminDashboard/>}
      {!userData.role && (
        <div className='text-yellow-500 text-center'>
          <p>Invalid user role: {userData.role}</p>
        </div>
      )}
    </div>
  )
}

export default Home
