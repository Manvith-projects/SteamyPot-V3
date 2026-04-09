import axios from 'axios'
import React, { useEffect } from 'react'
import { serverUrl } from '../App'
import { useDispatch, useSelector } from 'react-redux'
import {  setCurrentAddress, setCurrentCity, setCurrentState, setUserData } from '../redux/userSlice'
import { setAddress, setLocation } from '../redux/mapSlice'

function useGetCity() {
    const dispatch=useDispatch()
    const {userData}=useSelector(state=>state.user)
    const apiKey=import.meta.env.VITE_GEOAPIKEY
    useEffect(()=>{
        const applyDefaultCity = () => {
            dispatch(setCurrentCity("Guntur"))
            dispatch(setCurrentState("Andhra Pradesh"))
        }

        const resolveCityByLatLon = async (latitude, longitude) => {
            try {
                dispatch(setLocation({lat: latitude, lon: longitude}))
                const result = await axios.get(`https://api.geoapify.com/v1/geocode/reverse?lat=${latitude}&lon=${longitude}&format=json&apiKey=${apiKey}`)
                const city = result?.data?.results?.[0]?.city || result?.data?.results?.[0]?.county
                const state = result?.data?.results?.[0]?.state
                const addr = result?.data?.results?.[0]?.address_line2 || result?.data?.results?.[0]?.address_line1

                if (city) {
                    dispatch(setCurrentCity(city))
                } else {
                    applyDefaultCity()
                }
                if (state) dispatch(setCurrentState(state))
                if (addr) {
                    dispatch(setCurrentAddress(addr))
                    dispatch(setAddress(addr))
                }
            } catch (error) {
                console.log("Geo reverse lookup failed:", error)
                applyDefaultCity()
            }
        }

        // 1) Try browser geolocation
        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const latitude = position.coords.latitude
                const longitude = position.coords.longitude
                await resolveCityByLatLon(latitude, longitude)
            },
            async () => {
                // 2) Fallback to stored user coordinates
                const latitude = userData?.location?.coordinates?.[1]
                const longitude = userData?.location?.coordinates?.[0]
                if (latitude && longitude) {
                    await resolveCityByLatLon(latitude, longitude)
                    return
                }
                // 3) Last-resort fallback to keep landing page populated
                applyDefaultCity()
            }
        )
    },[userData])
}

export default useGetCity
