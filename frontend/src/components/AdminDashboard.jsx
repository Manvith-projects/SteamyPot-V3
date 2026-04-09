import React, { useEffect, useState } from 'react'
import Nav from './Nav'
import axios from 'axios'
import { serverUrl } from '../App'
import { useDispatch, useSelector } from 'react-redux'
import {
  setStats, setPendingShops, setAllShops, updateShopInList,
  setTickets, updateTicket, setRiders, setUnassignedOrders,
  removeUnassignedOrder, setActiveTab
} from '../redux/adminSlice'
import { FaChartBar, FaStore, FaTicketAlt, FaMotorcycle, FaCheck, FaTimes, FaSpinner } from 'react-icons/fa'

function AdminDashboard() {
  const dispatch = useDispatch()
  const { stats, pendingShops, allShops, tickets, riders, unassignedOrders, activeTab } = useSelector(state => state.admin)
  const [loading, setLoading] = useState(false)
  const [rejectReason, setRejectReason] = useState({})
  const [ticketNote, setTicketNote] = useState({})
  const [selectedRider, setSelectedRider] = useState(null)
  const [riderAssignments, setRiderAssignments] = useState([])

  // ─── Fetch helpers ───
  const fetchStats = async () => {
    try {
      const res = await axios.get(`${serverUrl}/api/admin/stats`, { withCredentials: true })
      dispatch(setStats(res.data))
    } catch (e) { console.log(e) }
  }

  const fetchPendingShops = async () => {
    try {
      const res = await axios.get(`${serverUrl}/api/admin/shops/pending`, { withCredentials: true })
      dispatch(setPendingShops(res.data))
    } catch (e) { console.log(e) }
  }

  const fetchAllShops = async () => {
    try {
      const res = await axios.get(`${serverUrl}/api/admin/shops/all`, { withCredentials: true })
      dispatch(setAllShops(res.data))
    } catch (e) { console.log(e) }
  }

  const fetchTickets = async () => {
    try {
      const res = await axios.get(`${serverUrl}/api/admin/tickets`, { withCredentials: true })
      dispatch(setTickets(res.data))
    } catch (e) { console.log(e) }
  }

  const fetchRiders = async () => {
    try {
      const res = await axios.get(`${serverUrl}/api/admin/riders`, { withCredentials: true })
      dispatch(setRiders(res.data))
    } catch (e) { console.log(e) }
  }

  const fetchUnassigned = async () => {
    try {
      const res = await axios.get(`${serverUrl}/api/admin/orders/unassigned`, { withCredentials: true })
      dispatch(setUnassignedOrders(res.data))
    } catch (e) { console.log(e) }
  }

  useEffect(() => {
    fetchStats()
  }, [])

  useEffect(() => {
    if (activeTab === 'restaurants') { fetchPendingShops(); fetchAllShops() }
    if (activeTab === 'tickets') fetchTickets()
    if (activeTab === 'riders') { fetchRiders(); fetchUnassigned() }
  }, [activeTab])

  // ─── Actions ───
  const handleApprove = async (shopId) => {
    setLoading(true)
    try {
      const res = await axios.put(`${serverUrl}/api/admin/shops/approve/${shopId}`, {}, { withCredentials: true })
      dispatch(updateShopInList(res.data))
      fetchStats()
    } catch (e) { console.log(e) }
    setLoading(false)
  }

  const handleReject = async (shopId) => {
    setLoading(true)
    try {
      const res = await axios.put(`${serverUrl}/api/admin/shops/reject/${shopId}`, { reason: rejectReason[shopId] || '' }, { withCredentials: true })
      dispatch(updateShopInList(res.data))
      fetchStats()
    } catch (e) { console.log(e) }
    setLoading(false)
  }

  const handleTicketUpdate = async (ticketId, status) => {
    try {
      const res = await axios.put(`${serverUrl}/api/admin/tickets/${ticketId}`, { status, adminNote: ticketNote[ticketId] || '' }, { withCredentials: true })
      dispatch(updateTicket(res.data))
    } catch (e) { console.log(e) }
  }

  const handleAssignRider = async (assignmentId, riderId) => {
    try {
      const res = await axios.post(`${serverUrl}/api/admin/riders/assign`, { assignmentId, riderId }, { withCredentials: true })
      dispatch(removeUnassignedOrder(assignmentId))
    } catch (e) { console.log(e) }
  }

  const viewRiderHistory = async (riderId) => {
    setSelectedRider(riderId)
    try {
      const res = await axios.get(`${serverUrl}/api/admin/riders/${riderId}/assignments`, { withCredentials: true })
      setRiderAssignments(res.data)
    } catch (e) { console.log(e) }
  }

  // ─── Tabs config ───
  const tabs = [
    { key: 'dashboard', label: 'Dashboard', icon: <FaChartBar /> },
    { key: 'restaurants', label: 'Restaurants', icon: <FaStore /> },
    { key: 'tickets', label: 'Support Tickets', icon: <FaTicketAlt /> },
    { key: 'riders', label: 'Rider Mapping', icon: <FaMotorcycle /> }
  ]

  return (
    <div className='w-full min-h-screen bg-gradient-to-br from-[#18181c] via-[#23232a] to-[#0b0b0f] flex flex-col items-center'>
      <Nav />
      <div className='w-full max-w-7xl mt-6 px-4'>
        {/* Tabs */}
        <div className='flex gap-2 mb-6 overflow-x-auto pb-2'>
          {tabs.map(t => (
            <button key={t.key} onClick={() => dispatch(setActiveTab(t.key))}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-full font-semibold text-sm transition whitespace-nowrap ${activeTab === t.key ? 'bg-[#ff4d2d] text-white shadow-lg' : 'bg-[#23232a] text-gray-400 hover:bg-[#2d2d36] hover:text-white border border-[#33333a]'}`}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* ─── Dashboard Tab ─── */}
        {activeTab === 'dashboard' && stats && (
          <div className='grid grid-cols-2 md:grid-cols-4 gap-4'>
            {[
              { label: 'Total Users', value: stats.totalUsers, color: 'from-blue-600 to-blue-800' },
              { label: 'Total Owners', value: stats.totalOwners, color: 'from-green-600 to-green-800' },
              { label: 'Total Riders', value: stats.totalRiders, color: 'from-purple-600 to-purple-800' },
              { label: 'Total Shops', value: stats.totalShops, color: 'from-yellow-600 to-yellow-800' },
              { label: 'Pending Approvals', value: stats.pendingShops, color: 'from-orange-600 to-orange-800' },
              { label: 'Total Orders', value: stats.totalOrders, color: 'from-pink-600 to-pink-800' },
              { label: 'Open Tickets', value: stats.openTickets, color: 'from-red-600 to-red-800' }
            ].map((card, i) => (
              <div key={i} className={`bg-gradient-to-br ${card.color} rounded-2xl p-6 shadow-xl`}>
                <div className='text-gray-200 text-sm'>{card.label}</div>
                <div className='text-3xl font-bold text-white mt-1'>{card.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* ─── Restaurants Tab ─── */}
        {activeTab === 'restaurants' && (
          <div className='flex flex-col gap-6'>
            <h2 className='text-xl font-bold text-[#ff4d2d]'>Pending Approvals ({pendingShops.length})</h2>
            {pendingShops.length === 0 && <div className='text-gray-400 bg-[#18181c] rounded-xl p-6 border border-[#24242c]'>No pending restaurants to approve.</div>}
            <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
              {pendingShops.map(shop => (
                <div key={shop._id} className='bg-[#18181c] rounded-2xl p-5 border border-[#24242c] shadow-lg'>
                  <div className='flex gap-4'>
                    <img src={shop.image} alt={shop.name} className='w-20 h-20 rounded-xl object-cover' />
                    <div className='flex-1'>
                      <h3 className='text-white font-bold text-lg'>{shop.name}</h3>
                      <p className='text-gray-400 text-sm'>{shop.city}, {shop.state}</p>
                      <p className='text-gray-500 text-sm'>{shop.address}</p>
                      <p className='text-gray-400 text-xs mt-1'>Owner: {shop.owner?.fullName} ({shop.owner?.email})</p>
                    </div>
                  </div>
                  <div className='mt-3 flex flex-col gap-2'>
                    <input type="text" placeholder='Rejection reason (optional)' value={rejectReason[shop._id] || ''} onChange={e => setRejectReason(prev => ({ ...prev, [shop._id]: e.target.value }))}
                      className='bg-[#23232a] text-white text-sm px-3 py-2 rounded-lg border border-[#33333a] outline-none w-full' />
                    <div className='flex gap-2'>
                      <button onClick={() => handleApprove(shop._id)} disabled={loading}
                        className='flex-1 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg font-medium flex items-center justify-center gap-2 transition'>
                        <FaCheck /> Approve
                      </button>
                      <button onClick={() => handleReject(shop._id)} disabled={loading}
                        className='flex-1 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg font-medium flex items-center justify-center gap-2 transition'>
                        <FaTimes /> Reject
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <h2 className='text-xl font-bold text-[#ff4d2d] mt-6'>All Restaurants ({allShops.length})</h2>
            <div className='overflow-x-auto'>
              <table className='w-full text-sm text-left text-gray-300'>
                <thead className='text-xs uppercase bg-[#23232a] text-gray-400'>
                  <tr>
                    <th className='px-4 py-3'>Name</th>
                    <th className='px-4 py-3'>City</th>
                    <th className='px-4 py-3'>Owner</th>
                    <th className='px-4 py-3'>Status</th>
                    <th className='px-4 py-3'>Rating</th>
                  </tr>
                </thead>
                <tbody>
                  {allShops.map(shop => (
                    <tr key={shop._id} className='border-b border-[#24242c] hover:bg-[#1a1a22]'>
                      <td className='px-4 py-3 text-white font-medium'>{shop.name}</td>
                      <td className='px-4 py-3'>{shop.city}</td>
                      <td className='px-4 py-3'>{shop.owner?.fullName}</td>
                      <td className='px-4 py-3'>
                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${shop.isApproved === 'approved' ? 'bg-green-600/20 text-green-400' : shop.isApproved === 'rejected' ? 'bg-red-600/20 text-red-400' : 'bg-yellow-600/20 text-yellow-400'}`}>
                          {shop.isApproved}
                        </span>
                      </td>
                      <td className='px-4 py-3'>{shop.avgRating?.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ─── Tickets Tab ─── */}
        {activeTab === 'tickets' && (
          <div className='flex flex-col gap-4'>
            <h2 className='text-xl font-bold text-[#ff4d2d]'>Support Tickets ({tickets.length})</h2>
            {tickets.length === 0 && <div className='text-gray-400 bg-[#18181c] rounded-xl p-6 border border-[#24242c]'>No support tickets.</div>}
            {tickets.map(ticket => (
              <div key={ticket._id} className='bg-[#18181c] rounded-2xl p-5 border border-[#24242c] shadow-lg'>
                <div className='flex justify-between items-start flex-wrap gap-2'>
                  <div>
                    <h3 className='text-white font-bold'>{ticket.subject}</h3>
                    <p className='text-gray-400 text-sm mt-1'>{ticket.description}</p>
                    <p className='text-gray-500 text-xs mt-2'>
                      By: {ticket.raisedBy?.fullName} ({ticket.raisedBy?.role}) &bull; {ticket.shop ? `Shop: ${ticket.shop.name}` : ''} &bull; {new Date(ticket.createdAt).toLocaleDateString()}
                    </p>
                    {ticket.adminNote && <p className='text-blue-400 text-xs mt-1'>Admin note: {ticket.adminNote}</p>}
                    {ticket.resolvedBy && <p className='text-green-400 text-xs'>Resolved by: {ticket.resolvedBy.fullName}</p>}
                  </div>
                  <span className={`px-3 py-1 rounded-full text-xs font-bold whitespace-nowrap ${ticket.status === 'open' ? 'bg-yellow-600/20 text-yellow-400' : ticket.status === 'in-progress' ? 'bg-blue-600/20 text-blue-400' : ticket.status === 'resolved' ? 'bg-green-600/20 text-green-400' : 'bg-gray-600/20 text-gray-400'}`}>
                    {ticket.status}
                  </span>
                </div>
                {ticket.status !== 'closed' && ticket.status !== 'resolved' && (
                  <div className='mt-3 flex flex-col gap-2'>
                    <input type="text" placeholder='Admin note...' value={ticketNote[ticket._id] || ''} onChange={e => setTicketNote(prev => ({ ...prev, [ticket._id]: e.target.value }))}
                      className='bg-[#23232a] text-white text-sm px-3 py-2 rounded-lg border border-[#33333a] outline-none w-full' />
                    <div className='flex gap-2 flex-wrap'>
                      {ticket.status === 'open' && (
                        <button onClick={() => handleTicketUpdate(ticket._id, 'in-progress')} className='bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition'>Mark In-Progress</button>
                      )}
                      <button onClick={() => handleTicketUpdate(ticket._id, 'resolved')} className='bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition'>Resolve</button>
                      <button onClick={() => handleTicketUpdate(ticket._id, 'closed')} className='bg-gray-600 hover:bg-gray-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition'>Close</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ─── Riders Tab ─── */}
        {activeTab === 'riders' && (
          <div className='flex flex-col gap-6'>
            {/* Unassigned orders */}
            <h2 className='text-xl font-bold text-[#ff4d2d]'>Unassigned Orders ({unassignedOrders.length})</h2>
            {unassignedOrders.length === 0 && <div className='text-gray-400 bg-[#18181c] rounded-xl p-6 border border-[#24242c]'>No unassigned orders right now.</div>}
            {unassignedOrders.map(assignment => (
              <div key={assignment._id} className='bg-[#18181c] rounded-2xl p-5 border border-[#24242c] shadow-lg'>
                <div className='flex justify-between items-start flex-wrap gap-2'>
                  <div>
                    <p className='text-white font-bold'>Order #{assignment.order?._id?.slice(-6)}</p>
                    <p className='text-gray-400 text-sm'>Shop: {assignment.shop?.name} ({assignment.shop?.city})</p>
                    <p className='text-gray-500 text-xs'>Broadcasted to {assignment.brodcastedTo?.length || 0} riders</p>
                  </div>
                  <span className='px-3 py-1 rounded-full text-xs font-bold bg-yellow-600/20 text-yellow-400'>{assignment.status}</span>
                </div>
                <div className='mt-3'>
                  <label className='text-gray-400 text-sm'>Assign to rider:</label>
                  <div className='flex gap-2 mt-1 flex-wrap'>
                    {riders.filter(r => r.isOnline).map(rider => (
                      <button key={rider._id} onClick={() => handleAssignRider(assignment._id, rider._id)}
                        className='bg-[#23232a] hover:bg-[#ff4d2d] text-white text-sm px-3 py-2 rounded-lg border border-[#33333a] transition'>
                        {rider.fullName} {rider.isOnline && <span className='text-green-400'>●</span>}
                      </button>
                    ))}
                    {riders.filter(r => r.isOnline).length === 0 && <span className='text-gray-500 text-sm'>No online riders</span>}
                  </div>
                </div>
              </div>
            ))}

            {/* All riders */}
            <h2 className='text-xl font-bold text-[#ff4d2d] mt-4'>All Riders ({riders.length})</h2>
            <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4'>
              {riders.map(rider => (
                <div key={rider._id} className='bg-[#18181c] rounded-2xl p-5 border border-[#24242c] shadow-lg cursor-pointer hover:border-[#ff4d2d]/50 transition' onClick={() => viewRiderHistory(rider._id)}>
                  <div className='flex items-center gap-3'>
                    <div className='w-12 h-12 rounded-full bg-[#ff4d2d] flex items-center justify-center text-white font-bold text-lg'>
                      {rider.fullName?.charAt(0)}
                    </div>
                    <div>
                      <h3 className='text-white font-bold'>{rider.fullName}</h3>
                      <p className='text-gray-400 text-sm'>{rider.email}</p>
                      <p className='text-gray-500 text-xs'>{rider.mobile}</p>
                    </div>
                    <div className='ml-auto'>
                      <span className={`px-2 py-1 rounded-full text-xs font-bold ${rider.isOnline ? 'bg-green-600/20 text-green-400' : 'bg-gray-600/20 text-gray-400'}`}>
                        {rider.isOnline ? 'Online' : 'Offline'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Rider assignment history */}
            {selectedRider && (
              <div className='mt-4'>
                <div className='flex items-center justify-between'>
                  <h2 className='text-xl font-bold text-[#ff4d2d]'>Assignment History</h2>
                  <button onClick={() => { setSelectedRider(null); setRiderAssignments([]) }} className='text-gray-400 hover:text-white text-sm'>Close</button>
                </div>
                {riderAssignments.length === 0 && <div className='text-gray-400 bg-[#18181c] rounded-xl p-6 border border-[#24242c] mt-2'>No assignments found.</div>}
                <div className='flex flex-col gap-3 mt-2'>
                  {riderAssignments.map(a => (
                    <div key={a._id} className='bg-[#23232a] rounded-xl p-4 border border-[#33333a]'>
                      <div className='flex justify-between items-center'>
                        <div>
                          <p className='text-white text-sm'>Order #{a.order?._id?.slice(-6)} &bull; {a.shop?.name}</p>
                          <p className='text-gray-500 text-xs'>{new Date(a.createdAt).toLocaleString()}</p>
                        </div>
                        <span className={`px-2 py-1 rounded-full text-xs font-bold ${a.status === 'completed' ? 'bg-green-600/20 text-green-400' : a.status === 'assigned' ? 'bg-blue-600/20 text-blue-400' : 'bg-yellow-600/20 text-yellow-400'}`}>
                          {a.status}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default AdminDashboard
