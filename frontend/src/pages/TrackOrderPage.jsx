import axios from 'axios'
import React from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { serverUrl } from '../App'
import { useEffect } from 'react'
import { useState } from 'react'
import { IoIosArrowRoundBack } from "react-icons/io";
import DeliveryBoyTracking from '../components/DeliveryBoyTracking'
import { useSelector } from 'react-redux'
import { useSocket } from '../context/SocketContext'
function TrackOrderPage() {
    const { orderId } = useParams()
    const [currentOrder, setCurrentOrder] = useState() 
    const navigate = useNavigate()
    const socket = useSocket()
    const {location}=useSelector(state=>state.map)
    const [liveLocations,setLiveLocations]=useState({})
    // Per-shopOrder ETA map
    const [etaMap, setEtaMap] = useState({})

    const handleGetOrder = async () => {
        try {
            const result = await axios.get(`${serverUrl}/api/order/get-order-by-id/${orderId}`, { withCredentials: true })
            setCurrentOrder(result.data)
        } catch (error) {
            console.log(error)
        }
    }

    useEffect(() => {
      if (!socket) return;
      const handler = ({ deliveryBoyId, latitude, longitude }) => {
        setLiveLocations(prev => ({
          ...prev,
          [deliveryBoyId]: { lat: latitude, lon: longitude }
        }))
      }
      socket.on('updateDeliveryLocation', handler)
      return () => {
        socket.off('updateDeliveryLocation', handler)
      }
    }, [socket])

    useEffect(() => {
        handleGetOrder()
    }, [orderId])

    // Predict ETA for each shopOrder and store in etaMap
    useEffect(() => {
        if (!currentOrder?.deliveryAddress) return
        const now = new Date()
        currentOrder.shopOrders?.forEach(shopOrder => {
            if (shopOrder.status !== 'delivered' && shopOrder.assignedDeliveryBoy) {
                const dbLoc = liveLocations[shopOrder.assignedDeliveryBoy._id] || {
                    lat: shopOrder.assignedDeliveryBoy.location?.coordinates?.[1],
                    lon: shopOrder.assignedDeliveryBoy.location?.coordinates?.[0]
                }
                if (dbLoc?.lat) {
                    axios.post(`${serverUrl}/api/ai/eta/predict`, {
                        restaurant_lat: dbLoc.lat,
                        restaurant_lon: dbLoc.lon,
                        customer_lat: currentOrder.deliveryAddress.latitude,
                        customer_lon: currentOrder.deliveryAddress.longitude,
                        order_hour: now.getHours(),
                        day_of_week: now.getDay(),
                        weather: "clear",
                        traffic_level: "medium",
                        prep_time_min: 0,
                        rider_availability: "high",
                        order_size: "medium",
                        historical_avg_delivery_min: 30
                    }).then(res => {
                        setEtaMap(prev => ({ ...prev, [shopOrder._id]: res.data }))
                    }).catch(() => {})
                }
            }
        })
    }, [currentOrder?._id, Object.keys(liveLocations).length])

    return (
        <div className='max-w-4xl mx-auto p-4 flex flex-col gap-6'>
            <div className='relative flex items-center gap-4 top-[20px] left-[20px] z-[10] mb-[10px]' onClick={() => navigate("/")}> 
                <IoIosArrowRoundBack size={35} className='text-[#ff4d2d]' />
                <h1 className='text-2xl font-bold md:text-center'>Track Order</h1>
            </div>
      {currentOrder?.shopOrders?.map((shopOrder,index)=>(
        <div className='bg-white p-4 rounded-2xl shadow-md border border-orange-100 space-y-4' key={index}>
         <div>
            <p className='text-lg font-bold mb-2 text-[#ff4d2d]'>{shopOrder.shop.name}</p>
            <p className='font-semibold'><span>Items:</span> {shopOrder.shopOrderItems?.map(i=>i.name).join(",")}</p>
            <p><span className='font-semibold'>Subtotal:</span> {shopOrder.subtotal}</p>
            <p className='mt-6'><span className='font-semibold'>Delivery address:</span> {currentOrder.deliveryAddress?.text}</p>
         </div>
         {shopOrder.status!="delivered"?<>
{/* AI ETA Prediction */}
{etaMap[shopOrder._id] && shopOrder.assignedDeliveryBoy && shopOrder.status !== "delivered" && (
  <div className='flex items-center gap-2 p-2 bg-blue-50 rounded-lg border border-blue-100'>
    <span className='text-blue-500 text-lg'>🕐</span>
    <span className='text-sm text-gray-700'>
      Estimated arrival: <strong className='text-gray-900'>{Math.round(etaMap[shopOrder._id].predicted_time)} min</strong>
    </span>
    {etaMap[shopOrder._id].confidence_score && <span className='text-xs text-gray-400'>({Math.round(etaMap[shopOrder._id].confidence_score * 100)}% confidence)</span>}
  </div>
)}
{shopOrder.assignedDeliveryBoy?
<div className='text-sm text-gray-700'>
<p className='font-semibold'><span>Delivery Boy Name:</span> {shopOrder.assignedDeliveryBoy.fullName}</p>
<p className='font-semibold'><span>Delivery Boy contact No.:</span> {shopOrder.assignedDeliveryBoy.mobile}</p>
</div>:<p className='font-semibold'>Delivery Boy is not assigned yet.</p>}
         </>:<p className='text-green-600 font-semibold text-lg'>Delivered</p>}

{(shopOrder.assignedDeliveryBoy && shopOrder.status !== "delivered") && (
  <div className="h-[400px] w-full rounded-2xl overflow-hidden shadow-md">
    <DeliveryBoyTracking data={{
      deliveryBoyLocation:liveLocations[shopOrder.assignedDeliveryBoy._id] || {
        lat: shopOrder.assignedDeliveryBoy.location.coordinates[1],
        lon: shopOrder.assignedDeliveryBoy.location.coordinates[0]
      },
      customerLocation: {
        lat: currentOrder.deliveryAddress.latitude,
        lon: currentOrder.deliveryAddress.longitude
      }
    }} />
  </div>
)}



        </div>
      ))}



        </div>
    )
}

export default TrackOrderPage
