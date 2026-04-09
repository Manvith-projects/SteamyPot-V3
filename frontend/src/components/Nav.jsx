import React, { useEffect, useState } from 'react'
import { FaLocationDot } from "react-icons/fa6";
import { IoIosSearch } from "react-icons/io";
import { FiShoppingCart } from "react-icons/fi";
import { FaRegHeart } from "react-icons/fa";
import { TbPhoneCall } from "react-icons/tb";
import { useDispatch, useSelector } from 'react-redux';
import { RxCross2 } from "react-icons/rx";
import axios from 'axios';
import { serverUrl } from '../App';
import { clearUserData, setSearchItems } from '../redux/userSlice';
import { FaPlus } from "react-icons/fa6";
import { TbReceipt2 } from "react-icons/tb";
import { MdAdminPanelSettings } from "react-icons/md";
import { useNavigate } from 'react-router-dom';
function Nav() {
    const { userData, favorites, itemsInMyCity, cartItems, currentCity } = useSelector(state => state.user)
    const { myShopData } = useSelector(state => state.owner)
    const [showInfo, setShowInfo] = useState(false)
    const profileRef = React.useRef(null)
    const [dropdownPos, setDropdownPos] = useState({ top: 78, left: 10 })
    const [showSearch, setShowSearch] = useState(false)
    const [query,setQuery]=useState("")
    const dispatch = useDispatch()
    const navigate=useNavigate()
    const handleLogOut = async () => {
        try {
            await axios.get(`${serverUrl}/api/auth/signout`, { withCredentials: true })
            dispatch(clearUserData())
            if (window.localStorage) {
                window.localStorage.removeItem('persist:user')
            }
            navigate('/signin')
        } catch (error) {
            console.log(error)
        }
    }

    const handleSearchItems=async () => {
      try {
        const result=await axios.get(`${serverUrl}/api/item/search-items?query=${query}&city=${currentCity}`,{withCredentials:true})
    dispatch(setSearchItems(result.data))
      } catch (error) {
        console.log(error)
      }
    }

    useEffect(()=>{
        if(query){
handleSearchItems()
        }else{
              dispatch(setSearchItems(null))
        }

    },[query])
    React.useEffect(() => {
        if (showInfo && profileRef.current) {
            const rect = profileRef.current.getBoundingClientRect()
            const dropdownWidth = 190;
            setDropdownPos({
                top: rect.bottom + window.scrollY + 3, // minimal gap below navbar/profile icon
                left: rect.left + window.scrollX + rect.width / 2 - dropdownWidth / 2
            })
        }
        const handleClick = (e) => {
            if (showInfo && profileRef.current && !profileRef.current.contains(e.target)) {
                const dropdown = document.getElementById('profile-dropdown')
                if (dropdown && !dropdown.contains(e.target)) {
                    setShowInfo(false)
                }
            }
        }
        document.addEventListener('mousedown', handleClick)
        return () => document.removeEventListener('mousedown', handleClick)
    }, [showInfo])

    return (
        <div className='w-full max-w-[100vw] box-border h-[72px] flex items-center justify-between gap-4 px-4 md:px-6 fixed top-0 z-[9999] bg-[#ff2e2e] text-white'>

            {showSearch && userData.role == "user" && <div className='w-[92%] h-[64px] bg-white shadow-2xl rounded-xl items-center gap-3 flex fixed top-[76px] left-[4%] md:hidden px-4'>
                <div className='flex items-center w-[32%] overflow-hidden gap-2 pr-3 border-r border-[#e5e5e5] text-gray-600'>
                        <FaLocationDot size={20} className=" text-[#ff2e2e]" />
                        <div className='w-[80%] truncate text-sm'>{currentCity}</div>
                </div>
                <div className='w-[68%] flex items-center gap-2'>
                    <IoIosSearch size={22} className='text-[#ff2e2e]' />
                        <input type="text" placeholder='Search' className='px-2 text-gray-800 placeholder:text-gray-500 outline-0 w-full bg-transparent' onChange={(e)=>setQuery(e.target.value)} value={query}/>
                </div>
            </div>}


            <div className='flex items-center gap-2 cursor-pointer' onClick={()=>navigate("/")}>
              <div className='w-9 h-9 rounded-md bg-white/15 border border-white/25 flex items-center justify-center text-lg font-bold tracking-tight'>🥘</div>
              <h1 className='text-2xl font-black uppercase tracking-[0.08em]'>SteamyPot</h1>
            </div>

            {userData.role == "user" && <div className='hidden md:flex items-center h-[48px] w-[44%] lg:w-[46%] rounded-full bg-white/95 px-4 text-gray-800 shadow-lg border border-white/40'>
                <IoIosSearch size={22} className='text-[#ff2e2e] mr-2' />
                <input type="text" placeholder='Search' className='flex-1 text-sm bg-transparent outline-0' onChange={(e)=>setQuery(e.target.value)} value={query}/>
                <div className='hidden lg:flex items-center gap-1 text-xs font-semibold text-gray-600 pl-3 border-l border-[#f0f0f0] truncate'>
                  <FaLocationDot size={16} className='text-[#ff2e2e]' />
                  <span className='truncate max-w-[120px]'>{currentCity}</span>
                </div>
            </div>}

            <div className='flex items-center gap-3'>
                {userData.role == "user" && (showSearch ? <RxCross2 size={24} className='text-white md:hidden' onClick={() => setShowSearch(false)} /> : <IoIosSearch size={24} className='text-white md:hidden' onClick={() => setShowSearch(true)} />)
                }
                {userData.role == "admin" ? <>
                    <div className='hidden md:flex items-center gap-2 cursor-pointer px-3 py-2 rounded-full text-white text-sm font-semibold bg-white/10 hover:bg-white/20 transition' onClick={()=>navigate("/")}>
                      <MdAdminPanelSettings size={18}/>
                      <span>Admin Panel</span>
                    </div>
                </> : userData.role == "owner"? <>
                                 {myShopData && <> <button className='hidden md:flex items-center gap-1 px-3 py-2 cursor-pointer rounded-full text-white text-sm font-semibold bg-white/15 hover:bg-white/25 transition' onClick={()=>navigate("/add-item")}>
                        <FaPlus size={16} />
                        <span>Add Item</span>
                    </button>
                                            <button className='md:hidden flex items-center px-2 py-2 cursor-pointer rounded-full text-white bg-white/15' onClick={()=>navigate("/add-item")}>
                        <FaPlus size={16} />
                    </button></>}
                   
                                        <div className='hidden md:flex items-center gap-2 cursor-pointer px-3 py-2 rounded-full text-white text-sm font-semibold bg-white/10 hover:bg-white/20 transition' onClick={()=>navigate("/my-orders")}>
                      <TbReceipt2 size={18}/>
                      <span>My Orders</span>
                      
                    </div>
                                         <div className='md:hidden flex items-center gap-2 cursor-pointer px-3 py-2 rounded-full text-white bg-white/10' onClick={()=>navigate("/my-orders")}>
                      <TbReceipt2 size={18}/>
                      
                    </div>
                </>: (
                    <>
                 {userData.role=="user" &&    <div className='relative cursor-pointer w-10 h-10 rounded-full bg-white/15 flex items-center justify-center hover:bg-white/25 transition' onClick={()=>navigate("/cart")}>
                    <FiShoppingCart size={20} className='text-white' />
                    <span className='absolute right-[-6px] top-[-6px] text-[11px] bg-white text-[#ff2e2e] rounded-full px-1.5 py-[2px] leading-none font-bold'>{cartItems.length}</span>
                </div>}   
           


                <button className='hidden md:block px-3 py-2 rounded-full text-white text-sm font-semibold bg-white/15 hover:bg-white/25 transition' onClick={()=>navigate("/my-orders")}>
                    My Orders
                </button>
                    </>
                )}

                                <div className='hidden md:flex items-center gap-2 text-white/90'>
                                    <button className='relative' title='Favorites' onClick={() => navigate('/favorites')}>
                                        <FaRegHeart className='text-lg' />
                                        {favorites.length > 0 && <span className='absolute -top-2 -right-2 bg-[#ff2e2e] text-white text-xs rounded-full px-1'>{favorites.length}</span>}
                                    </button>
                                </div>

                <div ref={profileRef} className='w-[40px] h-[40px] rounded-full flex items-center justify-center bg-white text-[#ff2e2e] text-[18px] shadow-xl font-semibold cursor-pointer' onClick={() => setShowInfo(prev => !prev)}>
                    {userData?.fullName.slice(0, 1)}
                </div>
                {showInfo === true && (
                    <div
                        id='profile-dropdown'
                        style={{ position: 'absolute', top: dropdownPos.top, left: dropdownPos.left, width: 190, zIndex: 9999 }}
                        className='bg-[#14141a] border border-[#24242c] shadow-2xl rounded-xl p-[16px] flex flex-col gap-3'
                    >
                        <div className='text-[17px] font-semibold text-white'>{userData.fullName}</div>
                        <div className='text-gray-300 font-semibold cursor-pointer hover:text-white transition' onClick={() => { navigate("/profile"); setShowInfo(false) }}>My Profile</div>
                        {userData.role == "user" && <div className='md:hidden text-[#ff4d2d] font-semibold cursor-pointer' onClick={() => navigate("/my-orders")}>My Orders</div>}
                        <div className='text-[#ff4d2d] font-semibold cursor-pointer' onClick={handleLogOut}>Log Out</div>
                    </div>
                )}
                {/* Favorites dropdown removed, now handled by /favorites page */}

            </div>
        </div>
    )
}


export default Nav
