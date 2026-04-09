import axios from 'axios'
import { useState } from 'react'
import { serverUrl } from '../App'

function useDynamicPricing() {
    const [pricing, setPricing] = useState(null)
    const [pricingLoading, setPricingLoading] = useState(false)

    const calculatePricing = async (params) => {
        setPricingLoading(true)
        try {
            const result = await axios.post(
                `${serverUrl}/api/ai/pricing/calculate`,
                params,
                { withCredentials: true }
            )
            setPricing(result.data)
            return result.data
        } catch (error) {
            console.log("Dynamic pricing error:", error)
            const fallback = {
                surge_multiplier: 1.0,
                final_delivery_fee: 40,
                recommended_discount: 0,
                pricing_reason: "Standard delivery fee",
                is_peak_hour: false
            }
            setPricing(fallback)
            return fallback
        } finally {
            setPricingLoading(false)
        }
    }

    return { pricing, pricingLoading, calculatePricing }
}

export default useDynamicPricing
