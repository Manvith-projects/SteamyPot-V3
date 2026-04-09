import React, { useEffect, useMemo, useRef, useState } from 'react'
import Nav from './Nav'
import { categories } from '../category'
import CategoryCard from './CategoryCard'
import { FaCircleChevronLeft, FaCircleChevronRight } from "react-icons/fa6";
import { useSelector } from 'react-redux';
import FoodCard from './FoodCard';
import { useNavigate } from 'react-router-dom';
import FoodAssistant from './FoodAssistant';

function UserDashboard() {
  const { currentCity, shopInMyCity, itemsInMyCity, searchItems, recommendedItems, contactRecommendedItems, contactNames, churnData } = useSelector(state => state.user)
  const navigate = useNavigate()

  const cateScrollRef = useRef(null)
  const shopScrollRef = useRef(null)
  const heroTimerRef = useRef(null)

  const [showLeftCateButton, setShowLeftCateButton] = useState(false)
  const [showRightCateButton, setShowRightCateButton] = useState(false)
  const [showLeftShopButton, setShowLeftShopButton] = useState(false)
  const [showRightShopButton, setShowRightShopButton] = useState(false)
  const [activeHero, setActiveHero] = useState(0)
  const [filteredItems, setFilteredItems] = useState([])
  const [visibleCount, setVisibleCount] = useState(12)
  const [activeCategory, setActiveCategory] = useState('All')

  const heroSlides = useMemo(() => categories.slice(0, 5), [])

  useEffect(() => {
    setFilteredItems(itemsInMyCity)
    setVisibleCount(12)
  }, [itemsInMyCity])

  const handleFilterByCategory = (category) => {
    setActiveCategory(category)
    if (category === "All") {
      setFilteredItems(itemsInMyCity)
    } else {
      const filtered = itemsInMyCity?.filter((i) => i.category === category)
      setFilteredItems(filtered)
    }
    setVisibleCount(12)
  }

  const updateButtons = (ref, setLeft, setRight) => {
    const el = ref.current
    if (!el) return
    setLeft(el.scrollLeft > 0)
    setRight(el.scrollLeft + el.clientWidth < el.scrollWidth)
  }

  const scrollBy = (ref, direction) => {
    const el = ref.current
    if (!el) return
    const amount = direction === 'left' ? -el.clientWidth * 0.8 : el.clientWidth * 0.8
    el.scrollBy({ left: amount, behavior: 'smooth' })
  }

  useEffect(() => {
    const cateEl = cateScrollRef.current
    const shopEl = shopScrollRef.current
    const onCate = () => updateButtons(cateScrollRef, setShowLeftCateButton, setShowRightCateButton)
    const onShop = () => updateButtons(shopScrollRef, setShowLeftShopButton, setShowRightShopButton)
    onCate(); onShop()
    cateEl?.addEventListener('scroll', onCate)
    shopEl?.addEventListener('scroll', onShop)
    return () => {
      cateEl?.removeEventListener('scroll', onCate)
      shopEl?.removeEventListener('scroll', onShop)
    }
  }, [])

  useEffect(() => {
    if (!heroSlides.length) return
    heroTimerRef.current = setInterval(() => {
      setActiveHero((prev) => (prev + 1) % heroSlides.length)
    }, 4500)
    return () => clearInterval(heroTimerRef.current)
  }, [heroSlides.length])

  const goHero = (next) => {
    setActiveHero((prev) => (prev + next + heroSlides.length) % heroSlides.length)
    if (heroTimerRef.current) {
      clearInterval(heroTimerRef.current)
      heroTimerRef.current = setInterval(() => {
        setActiveHero((p) => (p + 1) % heroSlides.length)
      }, 4500)
    }
  }

  return (
    <div className="min-h-screen w-full max-w-[100vw] overflow-x-hidden bg-[#0b0b0a] text-white relative">
      {/* Decorative red splashes background */}
      <div className="pointer-events-none absolute inset-0 z-0">
        <div className="absolute top-[-80px] left-[-120px] w-[400px] h-[400px] bg-[#ff2e2d] opacity-30 blur-3xl rounded-full" />
        <div className="absolute bottom-[-100px] right-[-100px] w-[350px] h-[350px] bg-[#ff2e2d] opacity-25 blur-2xl rounded-full" />
        <div className="absolute top-[40%] left-[-60px] w-[180px] h-[180px] bg-[#ff4d2d] opacity-20 blur-2xl rounded-full" />
        <div className="absolute bottom-[20%] right-[10%] w-[120px] h-[120px] bg-[#ff2e2d] opacity-20 blur-2xl rounded-full" />
      </div>
      <Nav />

      {/* AI Churn Retention Banner */}
      {churnData && churnData.risk_level && churnData.risk_level !== 'low' && (
        <div className={`mx-4 sm:mx-6 mt-[70px] rounded-2xl p-4 border ${
          churnData.risk_level === 'high'
            ? 'bg-gradient-to-r from-red-900/30 to-orange-900/20 border-red-800/40'
            : 'bg-gradient-to-r from-yellow-900/20 to-orange-900/10 border-yellow-800/30'
        }`}>
          <div className='flex items-center justify-between flex-wrap gap-3'>
            <div className='flex items-center gap-3'>
              <span className='text-2xl'>{churnData.risk_level === 'high' ? '🔥' : '💛'}</span>
              <div>
                <h3 className='font-bold text-white text-sm'>
                  {churnData.risk_level === 'high' ? 'We miss you! Here\'s a special offer' : 'Welcome back! Check out what\'s new'}
                </h3>
                <p className='text-xs text-gray-400'>
                  {churnData.risk_level === 'high'
                    ? 'Get 20% off your next order — just for you!'
                    : 'Enjoy free delivery on your next order!'}
                </p>
              </div>
            </div>
            <button
              className={`px-4 py-2 rounded-full text-sm font-semibold transition ${
                churnData.risk_level === 'high'
                  ? 'bg-[#ff4d2d] text-white hover:bg-[#e64526]'
                  : 'bg-yellow-500 text-black hover:bg-yellow-400'
              }`}
              onClick={() => navigate('/')}
            >
              Order Now
            </button>
          </div>
        </div>
      )}

      <main className="w-full max-w-[100vw] overflow-x-hidden pt-[60px] pb-16 flex flex-col gap-10">
        {searchItems && searchItems.length > 0 && (
          <section className="mx-4 sm:mx-6">
            <div className="rounded-3xl border border-white/10 bg-[#161616] shadow-2xl p-6">
              <div className="flex items-center justify-between gap-3 mb-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-white/60">Found {searchItems.length} items</p>
                  <h2 className="text-2xl font-bold leading-tight">Search Results</h2>
                </div>
              </div>
              <div className="w-full flex flex-wrap gap-5 justify-center">
                {searchItems.map((item) => (
                  <FoodCard data={item} key={item._id} />
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Hero */}
        <section className="w-full overflow-hidden">
          <div className="px-4 sm:px-6 pt-1 pb-1">
            {/* Main banner */}
            <div className="w-full h-[260px] sm:h-[340px] rounded-2xl bg-[#c5dedf] relative overflow-hidden">
              {heroSlides[activeHero] && (
                <img
                  src={heroSlides[activeHero].image}
                  alt={heroSlides[activeHero].category}
                  className="absolute inset-0 w-full h-full object-cover transition-opacity duration-500"
                />
              )}
            </div>
          </div>
          {/* Dots + arrows */}
          <div className="flex items-center justify-center gap-2 py-3">
            <button onClick={() => goHero(-1)} className="text-[#ff2e2e] hover:text-[#cc2424] transition" aria-label="Previous slide">
              <FaCircleChevronLeft size={16} />
            </button>
            {heroSlides.map((slide, idx) => (
              <button
                key={slide.category + idx}
                onClick={() => setActiveHero(idx)}
                className={`h-[10px] w-[10px] rounded-full transition-all duration-300 ${idx === activeHero ? 'bg-[#ff2e2e]' : 'bg-[#ff2e2e]/40'}`}
                aria-label={`Go to ${slide.category} banner`}
              />
            ))}
            <button onClick={() => goHero(1)} className="text-[#ff2e2e] hover:text-[#cc2424] transition" aria-label="Next slide">
              <FaCircleChevronRight size={16} />
            </button>
          </div>
        </section>

        {/* Categories */}
        <section className="mx-4 sm:mx-6 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-2xl font-extrabold italic">What's on your mind?</h2>
          </div>
          <div className="relative">
            {showLeftCateButton && (
              <button
                className="absolute left-0 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-[#ff2e2e] text-white shadow-lg hover:bg-[#e64528] z-10"
                onClick={() => scrollBy(cateScrollRef, 'left')}
                aria-label="Scroll categories left"
              >
                <FaCircleChevronLeft />
              </button>
            )}
            <div
              ref={cateScrollRef}
              className="w-full flex gap-5 overflow-x-auto pb-2 no-scrollbar"
            >
              {categories.map((cate, index) => (
                <CategoryCard name={cate.category} image={cate.image} key={index} active={activeCategory === cate.category} onClick={() => handleFilterByCategory(cate.category)} />
              ))}
            </div>
            {showRightCateButton && (
              <button
                className="absolute right-0 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-[#ff2e2e] text-white shadow-lg hover:bg-[#e64528] z-10"
                onClick={() => scrollBy(cateScrollRef, 'right')}
                aria-label="Scroll categories right"
              >
                <FaCircleChevronRight />
              </button>
            )}
          </div>
        </section>

        {/* Shops */}
        <section className="mx-4 sm:mx-6 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-2xl font-extrabold">Restaurants</h2>
            <button className="px-4 py-2 rounded-full border border-[#333] bg-[#1a1a1a] text-sm text-gray-200 hover:border-[#ff2e2e] transition">Sort By : Rating</button>
          </div>
          <div className="relative">
            {showLeftShopButton && (
              <button
                className="absolute left-0 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-[#ff2e2e] text-white shadow-lg hover:bg-[#e64528] z-10"
                onClick={() => scrollBy(shopScrollRef, 'left')}
                aria-label="Scroll shops left"
              >
                <FaCircleChevronLeft />
              </button>
            )}
            <div
              ref={shopScrollRef}
              className="w-full flex gap-5 overflow-x-auto pb-2 no-scrollbar"
            >
              {shopInMyCity?.map((shop, index) => (
                <CategoryCard name={shop.name} image={shop.image} key={index} onClick={() => navigate(`/shop/${shop._id}`)} />
              ))}
            </div>
            {showRightShopButton && (
              <button
                className="absolute right-0 top-1/2 -translate-y-1/2 h-10 w-10 rounded-full bg-[#ff2e2e] text-white shadow-lg hover:bg-[#e64528] z-10"
                onClick={() => scrollBy(shopScrollRef, 'right')}
                aria-label="Scroll shops right"
              >
                <FaCircleChevronRight />
              </button>
            )}
          </div>
        </section>

        {/* Items grid */}
        <section className="mx-4 sm:mx-6 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-2xl font-extrabold">Suggested Food Items</h2>
          </div>

          {/* Recommended for You */}
          {recommendedItems && recommendedItems.length > 0 && (
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-[#ff2e2e] text-2xl">&#10024;</span>
                <h3 className="text-xl font-bold text-white">Recommended for You</h3>
                <span className="ml-2 px-2 py-0.5 rounded-full bg-[#ff2e2e]/15 text-[#ff2e2e] text-xs font-semibold tracking-wide uppercase">AI Picks</span>
              </div>
              <div className="w-full grid gap-6 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 justify-items-center">
                {recommendedItems.slice(0, 4).map((item) => (
                  <FoodCard key={item._id} data={item} />
                ))}
              </div>
              <hr className="mt-8 border-[#252525]" />
            </div>
          )}

          {/* From Your Contacts */}
          {contactRecommendedItems && contactRecommendedItems.length > 0 && (
            <div className="mb-8">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-blue-400 text-2xl">&#128101;</span>
                <h3 className="text-xl font-bold text-white">Popular with Your Contacts</h3>
                <span className="ml-2 px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 text-xs font-semibold tracking-wide uppercase">Friends</span>
              </div>
              {contactNames && contactNames.length > 0 && (
                <p className="text-xs text-gray-500 mb-3">Based on orders from {contactNames.slice(0, 3).join(', ')}{contactNames.length > 3 ? ` and ${contactNames.length - 3} more` : ''}</p>
              )}
              <div className="w-full grid gap-6 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 justify-items-center">
                {contactRecommendedItems.slice(0, 4).map((item) => (
                  <FoodCard key={item._id} data={item} />
                ))}
              </div>
              <hr className="mt-8 border-[#252525]" />
            </div>
          )}

          {filteredItems && filteredItems.length > 0 ? (
            <div className="w-full grid gap-6 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 justify-items-center">
              {filteredItems.slice(0, visibleCount).map((item, index) => (
                <FoodCard key={index} data={item} />
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-gray-500">
              <span className="text-5xl mb-4">🍽️</span>
              <p className="text-lg font-semibold">No items found in "{activeCategory}"</p>
              <p className="text-sm mt-1">Try a different category</p>
            </div>
          )}
          {filteredItems && visibleCount < filteredItems.length && (
            <div className="flex justify-center mt-6">
              <button
                onClick={() => setVisibleCount((prev) => prev + 12)}
                className="px-6 py-2.5 rounded-full bg-[#ff2e2e] text-white font-semibold hover:bg-[#cc2424] transition"
              >
                View More
              </button>
            </div>
          )}
        </section>
      </main>

      {/* AI Food Assistant floating widget */}
      <FoodAssistant />
    </div>
  )
}

export default UserDashboard
