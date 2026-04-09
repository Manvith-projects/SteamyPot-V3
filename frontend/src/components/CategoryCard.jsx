import React from 'react'

function CategoryCard({ name, image, onClick, active }) {
  return (
    <button
      type="button"
      className={`group flex flex-col items-center gap-3 w-[120px] sm:w-[140px] shrink-0 focus-visible:outline-none transition-all duration-200 ${active ? 'scale-105' : ''}`}
      onClick={onClick}
    >
      <div className={`relative aspect-square w-full rounded-2xl overflow-hidden bg-[#1c1c1c] shadow-md transition-all duration-300 group-hover:-translate-y-1 ${active ? 'ring-3 ring-[#ff2e2e] shadow-[#ff2e2e]/30 shadow-lg' : ''}`}>
        <img src={image} alt={name} className="w-full h-full object-cover" />
      </div>
      <span className={`text-sm font-semibold text-center transition-colors ${active ? 'text-[#ff2e2e]' : 'text-white'}`}>{name}</span>
    </button>
  )
}

export default CategoryCard
