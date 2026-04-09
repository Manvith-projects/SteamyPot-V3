import React, { useEffect, useState } from 'react'
import { IoIosArrowRoundBack } from "react-icons/io";
import { IoSearchOutline } from "react-icons/io5";
import { TbCurrentLocation } from "react-icons/tb";
import { IoLocationSharp } from "react-icons/io5";
import { MapContainer, Marker, TileLayer, useMap } from 'react-leaflet';
import { useDispatch, useSelector } from 'react-redux';
import "leaflet/dist/leaflet.css"
import { setAddress, setLocation } from '../redux/mapSlice';
import { MdDeliveryDining } from "react-icons/md";
import { FaCreditCard } from "react-icons/fa";
import axios from 'axios';
import { FaMobileScreenButton } from "react-icons/fa6";
import { useNavigate } from 'react-router-dom';
import { serverUrl } from '../App';
import { addMyOrder, clearCart } from '../redux/userSlice';
import { persistor } from '../redux/store';
import useDynamicPricing from '../hooks/useDynamicPricing';
import useEtaPrediction from '../hooks/useEtaPrediction';
import Nav from '../components/Nav';
import { RiCoupon3Line } from "react-icons/ri";
function RecenterMap({ location }) {
  if (location.lat && location.lon) {
    const map = useMap()
    map.setView([location.lat, location.lon], 16, { animate: true })
  }
  return null

}

function CheckOut() {
  const { location, address } = useSelector(state => state.map)
    const { cartItems ,totalAmount,userData} = useSelector(state => state.user)
  const [addressInput, setAddressInput] = useState("")
  const [paymentMethod, setPaymentMethod] = useState("cod")
  const [couponCode, setCouponCode] = useState("")
  const [couponDiscount, setCouponDiscount] = useState(0)
  const [couponMessage, setCouponMessage] = useState("")
  const [couponApplied, setCouponApplied] = useState(false)
  const navigate=useNavigate()
  const dispatch = useDispatch()
  const apiKey = import.meta.env.VITE_GEOAPIKEY

  // AI Dynamic Pricing & ETA
  const { pricing, pricingLoading, calculatePricing } = useDynamicPricing()
  const { eta, etaLoading, predictETA } = useEtaPrediction()

  const defaultDeliveryFee = totalAmount > 500 ? 0 : 40
  const deliveryFee = pricing ? pricing.final_delivery_fee : defaultDeliveryFee
  const surgeMultiplier = pricing?.surge_multiplier || 1.0
  const discount = pricing?.recommended_discount || 0
  const AmountWithDeliveryFee = Math.max(0, totalAmount + deliveryFee - discount - couponDiscount)

  const finalizeSuccessfulOrder = async (orderData) => {
    dispatch(clearCart())
    await persistor.flush()

    if (couponApplied) {
      axios.post(`${serverUrl}/api/coupon/redeem`, { code: couponCode }, { withCredentials: true }).catch(() => { })
    }

    dispatch(addMyOrder(orderData))
    navigate("/order-placed")
  }






  const onDragEnd = (e) => {
    const { lat, lng } = e.target._latlng
    dispatch(setLocation({ lat, lon: lng }))
    getAddressByLatLng(lat, lng)
  }
  const getCurrentLocation = () => {
      const latitude=userData.location.coordinates[1]
      const longitude=userData.location.coordinates[0]
      dispatch(setLocation({ lat: latitude, lon: longitude }))
      getAddressByLatLng(latitude, longitude)
   

  }

  const getAddressByLatLng = async (lat, lng) => {
    try {

      const result = await axios.get(`https://api.geoapify.com/v1/geocode/reverse?lat=${lat}&lon=${lng}&format=json&apiKey=${apiKey}`)
      dispatch(setAddress(result?.data?.results[0].address_line2))
    } catch (error) {
      console.log(error)
    }
  }

  const getLatLngByAddress = async () => {
    try {
      const result = await axios.get(`https://api.geoapify.com/v1/geocode/search?text=${encodeURIComponent(addressInput)}&apiKey=${apiKey}`)
      const { lat, lon } = result.data.features[0].properties
      dispatch(setLocation({ lat, lon }))
    } catch (error) {
      console.log(error)
    }
  }

  const handlePlaceOrder=async () => {
    try {
      const result=await axios.post(`${serverUrl}/api/order/place-order`,{
        paymentMethod,
        deliveryAddress:{
          text:addressInput,
          latitude:location.lat,
          longitude:location.lon
        },
        totalAmount:AmountWithDeliveryFee,
        cartItems,
        couponCode: couponApplied ? couponCode : undefined
      },{withCredentials:true})

      if(paymentMethod=="cod"){
      await finalizeSuccessfulOrder(result.data)
      }else{
        const orderId=result.data.orderId
        const razorOrder=result.data.razorOrder
          openRazorpayWindow(orderId,razorOrder)
       }
    
    } catch (error) {
      console.log(error)
    }
  }

  const handleApplyCoupon = async () => {
    if(!couponCode.trim()) return
    try {
      const result = await axios.post(`${serverUrl}/api/coupon/apply`,{
        code: couponCode,
        orderAmount: totalAmount
      },{withCredentials:true})
      setCouponDiscount(result.data.discount)
      setCouponMessage(`${result.data.description} (-₹${result.data.discount})`)
      setCouponApplied(true)
    } catch (error) {
      setCouponDiscount(0)
      setCouponApplied(false)
      setCouponMessage(error.response?.data?.message || "Invalid coupon")
    }
  }

  const handleRemoveCoupon = () => {
    setCouponCode("")
    setCouponDiscount(0)
    setCouponMessage("")
    setCouponApplied(false)
  }

const openRazorpayWindow=(orderId,razorOrder)=>{

  const options={
 key:import.meta.env.VITE_RAZORPAY_KEY_ID,
 amount:razorOrder.amount,
 currency:'INR',
 name:"SteamyPot",
 description:"Food Delivery Website",
 order_id:razorOrder.id,
 handler:async function (response) {
  try {
    const result=await axios.post(`${serverUrl}/api/order/verify-payment`,{
      razorpay_payment_id:response.razorpay_payment_id,
      orderId
    },{withCredentials:true})
        await finalizeSuccessfulOrder(result.data)
  } catch (error) {
    console.log(error)
  }
 }
  }

  const rzp=new window.Razorpay(options)
  rzp.open()


}


  useEffect(() => {
    setAddressInput(address)
  }, [address])

  // Fetch AI dynamic pricing and ETA when location or cart changes
  useEffect(() => {
    if (!location?.lat || !location?.lon || !cartItems?.length) return
    const now = new Date()
    calculatePricing({
      hour: now.getHours(),
      day_of_week: now.getDay(),
      is_holiday: 0,
      weather: "Clear",
      traffic_level: 3,
      active_orders: 10,
      available_riders: 5,
      avg_prep_time_min: 15,
      zone_id: 1,
      distance_km: 5,
      hist_demand_trend: 1.0,
      hist_cancel_rate: 0.05,
      base_delivery_fee: defaultDeliveryFee
    })
    // Note: real restaurant coordinates are resolved server-side in placeOrder;
    // here we use a slight offset for the preview ETA.
    predictETA({
      restaurant_lat: location.lat + 0.01,
      restaurant_lon: location.lon + 0.01,
      customer_lat: location.lat,
      customer_lon: location.lon,
      order_hour: now.getHours(),
      day_of_week: now.getDay(),
      weather: "Clear",
      traffic_level: "Medium",
      prep_time_min: 15,
      rider_availability: "medium",
      order_size: cartItems.length > 3 ? "large" : cartItems.length > 1 ? "medium" : "small",
      historical_avg_delivery_min: 35
    })
  }, [location?.lat, location?.lon, cartItems?.length])

  return (
    <div className='min-h-screen pt-[100px] flex flex-col items-center p-6' style={{background: 'var(--bg)', backgroundImage: 'radial-gradient(circle at 20% 30%, var(--accent-soft) 0%, transparent 60%), radial-gradient(circle at 80% 70%, var(--accent-soft) 0%, transparent 60%)'}}>
      <Nav />
      <div className='w-full max-w-[900px] rounded-2xl shadow-xl p-6 space-y-6' style={{background: 'var(--bg-card)', color: 'var(--text)', border: '1px solid var(--border)'}}>
        <h1 className='text-2xl font-bold' style={{color: 'var(--accent)'}}>Checkout</h1>

        <section>
          <h2 className='text-lg font-semibold mb-2 flex items-center gap-2' style={{color: 'var(--accent)'}}><IoLocationSharp className='text-[#ff2e43]' /> Delivery Location</h2>
          <div className='flex gap-2 mb-3'>
            <input type="text" className='flex-1 border rounded-lg p-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#ff2e43]' placeholder='Enter Your Delivery Address..' value={addressInput} onChange={(e) => setAddressInput(e.target.value)} style={{background: 'var(--bg-elevated)', color: 'var(--text)', borderColor: 'var(--border)'}} />
            <button className='bg-[#ff2e43] hover:bg-[#ff455a] text-white px-3 py-2 rounded-lg flex items-center justify-center' onClick={getLatLngByAddress}><IoSearchOutline size={17} /></button>
            <button className='bg-[#ff2e43] hover:bg-[#ff455a] text-white px-3 py-2 rounded-lg flex items-center justify-center' onClick={getCurrentLocation}><TbCurrentLocation size={17} /></button>
          </div>
          <div className='rounded-xl border overflow-hidden' style={{borderColor: 'var(--border)'}}>
            <div className='h-64 w-full flex items-center justify-center'>
              <MapContainer
                className={"w-full h-full"}
                center={[location?.lat, location?.lon]}
                zoom={16}
              >
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                <RecenterMap location={location} />
                <Marker position={[location?.lat, location?.lon]} draggable eventHandlers={{ dragend: onDragEnd }} />


              </MapContainer>
            </div>
          </div>
        </section>

        <section>
          <h2 className='text-lg font-semibold mb-3' style={{color: 'var(--accent)'}}>Payment Method</h2>
          <div className='grid grid-cols-1 sm:grid-cols-2 gap-4'>
            <div className={`flex items-center gap-3 rounded-xl border p-4 text-left transition ${paymentMethod === "cod" ? "border-[#ff2e43] bg-[var(--accent-soft)] shadow" : "border-gray-200 hover:border-gray-300"}`} onClick={() => setPaymentMethod("cod")}> 
              <span className='inline-flex h-10 w-10 items-center justify-center rounded-full' style={{background: 'var(--accent-soft)'}}>
                <MdDeliveryDining className='text-[#ff2e43] text-xl' />
              </span>
              <div >
                <p className='font-medium'>Cash On Delivery</p>
                <p className='text-xs' style={{color: 'var(--muted)'}}>Pay when your food arrives</p>
              </div>
            </div>
            <div className={`flex items-center gap-3 rounded-xl border p-4 text-left transition ${paymentMethod === "online" ? "border-[#ff2e43] bg-[var(--accent-soft)] shadow" : "border-gray-200 hover:border-gray-300"}`} onClick={() => setPaymentMethod("online")}> 
              <span className='inline-flex h-10 w-10 items-center justify-center rounded-full' style={{background: 'var(--accent-soft)'}}>
                <FaMobileScreenButton className='text-[#ff2e43] text-lg' />
              </span>
              <span className='inline-flex h-10 w-10 items-center justify-center rounded-full' style={{background: 'var(--accent-soft)'}}>
                <FaCreditCard className='text-[#ff2e43] text-lg' />
              </span>
              <div>
                <p className='font-medium'>UPI / Credit / Debit Card</p>
                <p className='text-xs' style={{color: 'var(--muted)'}}>Pay Securely Online</p>
              </div>
            </div>
          </div>
        </section>

        <section>
          <h2 className='text-lg font-semibold mb-3' style={{color: 'var(--accent)'}}>Order Summary</h2>
<div className='rounded-xl border p-4 space-y-2' style={{background: 'var(--bg-elevated)', borderColor: 'var(--border)'}}>
{cartItems.map((item,index)=>(
  <div key={index} className='flex justify-between text-sm' style={{color: 'var(--muted)'}}>
<span>{item.name} x {item.quantity}</span>
<span>₹{item.price*item.quantity}</span>
  </div>
 
))}
 <hr className='border-gray-200 my-2'/>
<div className='flex justify-between font-medium' style={{color: 'var(--text)'}}>
  <span>Subtotal</span>
  <span>₹{totalAmount}</span>
</div>
<div className='flex justify-between' style={{color: 'var(--muted)'}}>
  <span className='flex items-center gap-1'>
    Delivery Fee
    {surgeMultiplier > 1.0 && <span className='text-[10px] bg-orange-100 text-orange-600 px-1.5 py-0.5 rounded-full font-semibold'>{surgeMultiplier.toFixed(1)}x surge</span>}
  </span>
  <span>{pricingLoading ? "..." : deliveryFee === 0 ? "Free" : `₹${Math.round(deliveryFee)}`}</span>
</div>
{discount > 0 && (
  <div className='flex justify-between text-sm' style={{color: '#ff2e43'}}>
    <span>AI Discount</span>
    <span>-₹{Math.round(discount)}</span>
  </div>
)}
{couponDiscount > 0 && (
  <div className='flex justify-between text-sm' style={{color: '#ff2e43'}}>
    <span>Coupon Discount</span>
    <span>-₹{Math.round(couponDiscount)}</span>
  </div>
)}
{pricing?.pricing_reason && (
  <p className='text-xs italic' style={{color: 'var(--muted-2)'}}>{pricing.pricing_reason}</p>
)}
<div className='flex justify-between text-lg font-bold pt-2' style={{color: 'var(--accent)'}}>
    <span>Total</span>
  <span>₹{Math.round(AmountWithDeliveryFee)}</span>
</div>
{eta && (
  <div className='flex items-center gap-2 pt-2 text-sm rounded-lg p-2 mt-1' style={{background: 'var(--accent-soft)', color: 'var(--accent)'}}>
    <span className='font-bold text-lg'>🕐</span>
    <span>Estimated delivery: <strong>{Math.round(eta.predicted_time)} min</strong></span>
    {eta.confidence_score && <span className='text-xs' style={{color: 'var(--muted-2)'}}>({Math.round(eta.confidence_score * 100)}% confidence)</span>}
  </div>
)}
</div>
        </section>

        <section>
          <h2 className='text-lg font-semibold mb-3 flex items-center gap-2' style={{color: 'var(--accent)'}}><RiCoupon3Line className='text-[#ff2e43]' /> Coupon Code</h2>
          <div className='rounded-xl border p-4' style={{background: 'var(--bg-elevated)', borderColor: 'var(--border)'}}>
            {couponApplied ? (
              <div className='flex items-center justify-between'>
                <div>
                  <span className='font-medium text-green-600'>✓ {couponCode.toUpperCase()}</span>
                  <p className='text-xs' style={{color: 'var(--muted)'}}>{couponMessage}</p>
                </div>
                <button className='text-sm text-red-500 hover:underline' onClick={handleRemoveCoupon}>Remove</button>
              </div>
            ) : (
              <>
                <div className='flex gap-2'>
                  <input type="text" className='flex-1 border rounded-lg p-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#ff2e43] uppercase' placeholder='Enter coupon code' value={couponCode} onChange={(e) => setCouponCode(e.target.value)} style={{background: 'var(--bg)', color: 'var(--text)', borderColor: 'var(--border)'}} />
                  <button className='bg-[#ff2e43] hover:bg-[#ff455a] text-white px-4 py-2 rounded-lg text-sm font-medium' onClick={handleApplyCoupon}>Apply</button>
                </div>
                {couponMessage && <p className='text-xs mt-2 text-red-500'>{couponMessage}</p>}
              </>
            )}
          </div>
        </section>

        <button className='w-full bg-[#ff4d2d] hover:bg-[#e64526] text-white py-3 rounded-xl font-semibold' onClick={handlePlaceOrder}> {paymentMethod=="cod"?"Place Order":"Pay & Place Order"}</button>

      </div>
    </div>
  )
}

export default CheckOut
