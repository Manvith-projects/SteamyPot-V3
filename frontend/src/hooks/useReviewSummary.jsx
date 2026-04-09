import axios from 'axios'
import { useState } from 'react'
import { serverUrl } from '../App'

function useReviewSummary() {
    const [reviewSummary, setReviewSummary] = useState(null)
    const [reviewLoading, setReviewLoading] = useState(false)

    const summarizeReviews = async (restaurantId, maxReviews = 200) => {
        setReviewLoading(true)
        try {
            const result = await axios.post(
                `${serverUrl}/api/ai/review/summarize`,
                { restaurant_id: restaurantId, max_reviews: maxReviews },
                { withCredentials: true }
            )
            setReviewSummary(result.data)
            return result.data
        } catch (error) {
            console.log("Review summary error:", error)
            setReviewSummary(null)
            return null
        } finally {
            setReviewLoading(false)
        }
    }

    const clearSummary = () => setReviewSummary(null)

    return { reviewSummary, reviewLoading, summarizeReviews, clearSummary }
}

export default useReviewSummary
