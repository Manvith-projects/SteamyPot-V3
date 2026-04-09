import axios from 'axios'
import { useState } from 'react'
import { serverUrl } from '../App'

function useRouteOptimization() {
    const [route, setRoute] = useState(null)
    const [routeLoading, setRouteLoading] = useState(false)

    const optimiseRoute = async (riderLat, riderLon, deliveries) => {
        setRouteLoading(true)
        try {
            const result = await axios.post(
                `${serverUrl}/api/ai/eta/optimise-route`,
                { rider_lat: riderLat, rider_lon: riderLon, deliveries },
                { withCredentials: true }
            )
            setRoute(result.data)
            return result.data
        } catch (error) {
            console.log("Route optimization error:", error)
            setRoute(null)
            return null
        } finally {
            setRouteLoading(false)
        }
    }

    return { route, routeLoading, optimiseRoute }
}

export default useRouteOptimization
