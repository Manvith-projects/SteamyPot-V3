import React, { useState } from 'react'
import { IoSend, IoClose, IoChatbubbleEllipses } from 'react-icons/io5'
import { FaStar, FaLeaf, FaDrumstickBite } from 'react-icons/fa'
import { useSelector } from 'react-redux'
import useFoodAssistant from '../hooks/useFoodAssistant'
import { useNavigate } from 'react-router-dom'

function FoodAssistant() {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [chatHistory, setChatHistory] = useState([])
  const { askAssistant, foodAssistantResults, foodAssistantLoading } = useFoodAssistant()
  const { userData } = useSelector(state => state.user)
  const { location } = useSelector(state => state.map)
  const navigate = useNavigate()

  const handleSend = async () => {
    if (!query.trim() || foodAssistantLoading) return
    const userMsg = query.trim()
    setChatHistory(prev => [...prev, { role: "user", text: userMsg }])
    setQuery("")

    const userLat = location?.lat || userData?.location?.coordinates?.[1] || 17.385
    const userLon = location?.lon || userData?.location?.coordinates?.[0] || 78.4867

    await askAssistant(userMsg, userLat, userLon)
  }

  // keep chat history in sync with latest result
  const lastResultRef = React.useRef(null)
  React.useEffect(() => {
    if (foodAssistantResults && !foodAssistantLoading && foodAssistantResults !== lastResultRef.current) {
      lastResultRef.current = foodAssistantResults
      setChatHistory(prev => [...prev, { role: "ai", data: foodAssistantResults }])
    }
  }, [foodAssistantResults, foodAssistantLoading])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') handleSend()
  }

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className='fixed bottom-6 right-6 z-50 bg-[#ff4d2d] hover:bg-[#e64526] text-white rounded-full w-14 h-14 flex items-center justify-center shadow-2xl transition-all hover:scale-110'
      >
        <IoChatbubbleEllipses size={26} />
      </button>
    )
  }

  return (
    <div className='fixed bottom-6 right-6 z-50 w-[380px] max-w-[calc(100vw-2rem)] h-[520px] bg-[#14141a] rounded-2xl shadow-2xl border border-[#24242c] flex flex-col overflow-hidden'>
      {/* Header */}
      <div className='flex items-center justify-between px-4 py-3 bg-[#1b1b23] border-b border-[#24242c]'>
        <div className='flex items-center gap-2'>
          <span className='text-xl'>🤖</span>
          <div>
            <h3 className='text-white font-semibold text-sm'>AI Food Assistant</h3>
            <p className='text-[10px] text-gray-400'>Ask me about food, restaurants, or dietary needs</p>
          </div>
        </div>
        <button onClick={() => setIsOpen(false)} className='text-gray-400 hover:text-white transition'>
          <IoClose size={20} />
        </button>
      </div>

      {/* Chat area */}
      <div className='flex-1 overflow-y-auto p-3 space-y-3 no-scrollbar'>
        {chatHistory.length === 0 && (
          <div className='flex flex-col items-center justify-center h-full text-gray-500 text-sm space-y-2'>
            <span className='text-4xl'>🍽️</span>
            <p>Ask me anything!</p>
            <div className='flex flex-wrap gap-1.5 justify-center mt-2'>
              {["Best biryani nearby", "Healthy dinner options", "Cheap veg food", "Desserts under ₹200"].map(s => (
                <button key={s} className='text-[11px] bg-[#1f1f28] px-2.5 py-1 rounded-full border border-[#333] text-gray-300 hover:border-[#ff4d2d] transition'
                  onClick={() => { setQuery(s) }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {chatHistory.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'user' ? (
              <div className='bg-[#ff4d2d] text-white px-3 py-2 rounded-2xl rounded-br-sm max-w-[80%] text-sm'>
                {msg.text}
              </div>
            ) : (
              <div className='bg-[#1f1f28] text-gray-200 px-3 py-2 rounded-2xl rounded-bl-sm max-w-[90%] text-sm space-y-2'>
                <p>{msg.data?.message || "Here's what I found:"}</p>
                {msg.data?.results && msg.data.results.length > 0 && (
                  <div className='space-y-2 mt-2'>
                    {msg.data.results.slice(0, 5).map((item, i) => (
                      <div key={i} className='bg-[#14141a] rounded-lg p-2 border border-[#24242c] hover:border-[#ff4d2d] transition'>
                        <div className='flex items-center justify-between'>
                          <span className='font-semibold text-white text-xs truncate'>{item.menu_item || item.restaurant_name}</span>
                          {item.diet_type && (
                            item.diet_type === 'veg'
                              ? <FaLeaf className='text-green-500 text-xs' />
                              : <FaDrumstickBite className='text-red-500 text-xs' />
                          )}
                        </div>
                        <div className='flex items-center gap-2 mt-0.5'>
                          {item.restaurant_rating != null && <span className='flex items-center gap-0.5 text-[10px] text-yellow-400'><FaStar />{Number(item.restaurant_rating).toFixed(1)}</span>}
                          {item.price && <span className='text-[10px] text-gray-400'>₹{item.price}</span>}
                          {item.distance && <span className='text-[10px] text-gray-500'>{item.distance}</span>}
                        </div>
                        {item.restaurant_name && item.menu_item && (
                          <p className='text-[10px] text-gray-500 mt-0.5 truncate'>{item.restaurant_name}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {foodAssistantLoading && (
          <div className='flex justify-start'>
            <div className='bg-[#1f1f28] px-4 py-2 rounded-2xl rounded-bl-sm text-sm text-gray-400 animate-pulse'>
              Thinking...
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div className='px-3 py-2 border-t border-[#24242c] bg-[#1b1b23]'>
        <div className='flex items-center gap-2'>
          <input
            type='text'
            className='flex-1 bg-[#14141a] text-white px-3 py-2 rounded-full text-sm border border-[#333] focus:outline-none focus:border-[#ff4d2d] placeholder-gray-500'
            placeholder='Ask about food...'
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button
            onClick={handleSend}
            disabled={foodAssistantLoading || !query.trim()}
            className='bg-[#ff4d2d] hover:bg-[#e64526] disabled:bg-gray-600 text-white rounded-full w-9 h-9 flex items-center justify-center transition'
          >
            <IoSend size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}

export default FoodAssistant
