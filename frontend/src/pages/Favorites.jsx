import React from 'react';
import { useSelector } from 'react-redux';
import FoodCard from '../components/FoodCard';
import Nav from '../components/Nav';

function Favorites() {
  const { userData, favorites, itemsInMyCity } = useSelector(state => state.user);
  if (userData?.role !== 'user') {
    return (
      <>
        <Nav />
        <div className='min-h-screen w-full flex flex-col items-center justify-center px-4' style={{background: 'var(--bg)', color: 'var(--text)'}}>
          <h1 className='text-3xl font-bold text-[#ff2e2e] mt-8 mb-6'>Favorites are only available for users.</h1>
        </div>
      </>
    );
  }
  const favoriteItems = itemsInMyCity?.filter(i => favorites.includes(i._id)) || [];

  return (
    <>
      <Nav />
      <div className='min-h-screen w-full flex flex-col items-center px-4' style={{background: 'var(--bg)', color: 'var(--text)'}}>
        <h1 className='text-3xl font-bold text-[#ff2e2e] mt-8 mb-6'>My Favorites</h1>
        {favoriteItems.length === 0 ? (
          <div className='text-gray-400 text-lg mt-12'>No favorites yet.</div>
        ) : (
          <div className='flex flex-wrap justify-center gap-8 w-full max-w-5xl'>
            {favoriteItems.map(item => (
              <FoodCard key={item._id} data={item} />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

export default Favorites;
