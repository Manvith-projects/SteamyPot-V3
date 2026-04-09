import axios from 'axios'
import { useEffect } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { setChurnData } from '../redux/userSlice'
import { serverUrl } from '../App'

function useChurnPrediction() {
    const dispatch = useDispatch()
    const { userData, churnData } = useSelector(state => state.user)

    useEffect(() => {
        if (!userData || userData.role !== "user") return
        // Only check once per session
        if (churnData) return

        const fetchChurn = async () => {
            try {
                const result = await axios.get(
                    `${serverUrl}/api/ai/churn/predict`,
                    { withCredentials: true }
                )
                dispatch(setChurnData(result.data))
            } catch (error) {
                console.log("Churn prediction error:", error)
            }
        }
        fetchChurn()
    }, [userData?._id])

    return churnData
}

export default useChurnPrediction
