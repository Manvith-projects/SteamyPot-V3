import axios from 'axios'
import React, { useEffect } from 'react'
import { serverUrl } from '../App'
import { useDispatch } from 'react-redux'
import { setUserData } from '../redux/userSlice'


function useGetCurrentUser() {
  const dispatch = useDispatch();
  const [loading, setLoading] = React.useState(true);
  useEffect(() => {
    const fetchUser = async () => {
      try {
        const result = await axios.get(`${serverUrl}/api/user/current`, { withCredentials: true });
        dispatch(setUserData(result.data));
        console.log('✓ Current user fetched successfully');
      } catch (error) {
        console.warn('Failed to fetch current user (might be expected if just logged in):', error.message);
        // Don't clear userData - let redux-persist handle it
      }
      setLoading(false);
    };
    fetchUser();
  }, [dispatch]);
  return loading;
}

export default useGetCurrentUser
