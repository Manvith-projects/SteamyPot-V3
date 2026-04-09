import axios from 'axios'
import { useEffect } from 'react'
import { serverUrl } from '../App'
import { useDispatch, useSelector } from 'react-redux'
import { setRecommendedItems } from '../redux/userSlice'

function useGetRecommendations() {
    const dispatch = useDispatch()
    const { userData } = useSelector(state => state.user)

    useEffect(() => {
        if (!userData || userData.role !== "user") return

        const fetchRecommendations = async () => {
            try {
                const result = await axios.get(
                    `${serverUrl}/api/recommendations`,
                    { withCredentials: true }
                )
                dispatch(setRecommendedItems(result.data.items || []))
            } catch (error) {
                console.log("Recommendations fetch error:", error)
                dispatch(setRecommendedItems([]))
            }
        }

        fetchRecommendations()
    }, [userData])
}

export default useGetRecommendations
