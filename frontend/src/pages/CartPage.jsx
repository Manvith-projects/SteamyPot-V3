import React from 'react'
import { IoIosArrowRoundBack } from "react-icons/io";
import { useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import CartItemCard from '../components/CartItemCard';
import Nav from '../components/Nav';

function CartPage() {
    const navigate = useNavigate()
    const { cartItems, totalAmount } = useSelector(state => state.user)

    return (
        <div
            className='min-h-screen pt-[100px] px-4 pb-8 md:px-6'
            style={{
                background: 'var(--bg)',
                backgroundImage: 'radial-gradient(circle at 20% 30%, var(--accent-soft) 0%, transparent 60%), radial-gradient(circle at 80% 70%, var(--accent-soft) 0%, transparent 60%)'
            }}
        >
            <Nav />
            <div className='mx-auto w-full max-w-[860px] rounded-2xl p-5 md:p-6 shadow-xl' style={{ background: 'var(--bg-card)', color: 'var(--text)', border: '1px solid var(--border)' }}>
                <div className='mb-6 flex items-center gap-3'>
                    <button className='z-[10] rounded-full p-1 transition hover:bg-black/5' onClick={() => navigate("/")}>
                        <IoIosArrowRoundBack size={35} className='text-[#ff4d2d]' />
                    </button>
                    <div>
                        <h1 className='text-2xl font-bold'>Your Cart</h1>
                        <p className='text-sm' style={{ color: 'var(--muted)' }}>Review your items before checkout.</p>
                    </div>
                </div>
                {cartItems?.length == 0 ? (
                    <div className='rounded-2xl border px-6 py-14 text-center' style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)' }}>
                        <p className='text-lg font-medium'>Your cart is empty</p>
                        <p className='mt-2 text-sm' style={{ color: 'var(--muted)' }}>Add a few dishes and come back here to place an order.</p>
                    </div>
                ) : (<>
                    <div className='space-y-4'>
                        {cartItems?.map((item, index) => (
                            <CartItemCard data={item} key={item.id || index} />
                        ))}
                    </div>
                    <div className='mt-6 flex items-center justify-between rounded-xl border p-4 shadow' style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)' }}>

                        <h1 className='text-lg font-semibold'>Total Amount</h1>
                        <span className='text-xl font-bold text-[#ff4d2d]'>₹{totalAmount}</span>
                    </div>
                    <div className='mt-4 flex justify-end' > 
                        <button className='bg-[#ff4d2d] text-white px-6 py-3 rounded-lg text-lg font-medium hover:bg-[#e64526] transition cursor-pointer' onClick={()=>navigate("/checkout")}>Proceed to CheckOut</button>
                    </div>
                </>
                )}
            </div>
        </div>
    )
}

export default CartPage
