import axios from 'axios'
import React, { useEffect } from 'react'
import { serverUrl } from '../App'
import { useDispatch, useSelector } from 'react-redux'
import { setItemsInMyCity, setShopsInMyCity, setUserData } from '../redux/userSlice'

function useGetItemsByCity() {
    const dispatch=useDispatch()
    const {currentCity}=useSelector(state=>state.user)
    const {location}=useSelector(state=>state.map)
  useEffect(()=>{
  const fetchItems=async () => {
    if(!currentCity) return
    try {
           let url=`${serverUrl}/api/item/get-by-city/${currentCity}`
           if(location?.lat && location?.lon){
               url+=`?lat=${location.lat}&lng=${location.lon}`
           }
           const result=await axios.get(url,{withCredentials:true})
            dispatch(setItemsInMyCity(result.data))
           console.log(result.data)
    } catch (error) {
        console.log(error)
      dispatch(setItemsInMyCity([]))
    }
}
fetchItems()
 
  },[currentCity, location])
}

export default useGetItemsByCity
