import axios from 'axios'
import { useState } from 'react'
import { serverUrl } from '../App'

function useEtaPrediction() {
    const [eta, setEta] = useState(null)
    const [etaLoading, setEtaLoading] = useState(false)

    const predictETA = async (params) => {
        setEtaLoading(true)
        try {
            const result = await axios.post(
                `${serverUrl}/api/ai/eta/predict`,
                params,
                { withCredentials: true }
            )
            setEta(result.data)
            return result.data
        } catch (error) {
            console.log("ETA prediction error:", error)
            const fallback = { predicted_time: 35, confidence_score: 0.5, unit: "minutes", model_used: "fallback" }
            setEta(fallback)
            return fallback
        } finally {
            setEtaLoading(false)
        }
    }

    return { eta, etaLoading, predictETA }
}

export default useEtaPrediction
