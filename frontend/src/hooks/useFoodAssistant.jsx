import axios from 'axios'
import { useDispatch, useSelector } from 'react-redux'
import { setFoodAssistantResults, setFoodAssistantLoading } from '../redux/userSlice'
import { serverUrl } from '../App'

function useFoodAssistant() {
    const dispatch = useDispatch()
    const { foodAssistantResults, foodAssistantLoading } = useSelector(state => state.user)

    const askAssistant = async (query, userLat, userLon) => {
        dispatch(setFoodAssistantLoading(true))
        try {
            const result = await axios.post(
                `${serverUrl}/api/ai/food/assistant`,
                { query, user_lat: userLat, user_lon: userLon },
                { withCredentials: true }
            )
            dispatch(setFoodAssistantResults(result.data))
        } catch (error) {
            console.log("Food assistant error:", error)
            dispatch(setFoodAssistantResults({
                message: "Sorry, the AI assistant is temporarily unavailable.",
                intent: "error",
                results: [],
                total_candidates: 0
            }))
        } finally {
            dispatch(setFoodAssistantLoading(false))
        }
    }

    const clearResults = () => {
        dispatch(setFoodAssistantResults(null))
    }

    return { askAssistant, clearResults, foodAssistantResults, foodAssistantLoading }
}

export default useFoodAssistant
