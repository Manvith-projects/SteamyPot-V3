import axios from 'axios'
import { useEffect } from 'react'
import { serverUrl } from '../App'
import { useDispatch, useSelector } from 'react-redux'
import { setContactRecommendedItems } from '../redux/userSlice'

function useGetContactRecommendations() {
    const dispatch = useDispatch()
    const { userData } = useSelector(state => state.user)

    useEffect(() => {
        if (!userData || userData.role !== "user") return
        if (!userData.contacts || userData.contacts.length === 0) return

        const fetchContactRecs = async () => {
            try {
                const result = await axios.get(
                    `${serverUrl}/api/recommendations/contacts`,
                    { withCredentials: true }
                )
                dispatch(setContactRecommendedItems(result.data))
            } catch (error) {
                console.log("Contact recommendations error:", error)
            }
        }
        fetchContactRecs()
    }, [userData?._id, userData?.contacts?.length])
}

export default useGetContactRecommendations
