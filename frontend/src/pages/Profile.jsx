import React, { useState, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { serverUrl } from '../App'
import { clearUserData, setUserData } from '../redux/userSlice'
import Nav from '../components/Nav'
import { FaCamera, FaUser, FaEnvelope, FaPhone, FaLock, FaAddressBook, FaTrash, FaPlus, FaChevronRight, FaSignOutAlt, FaFileCsv, FaCloudUploadAlt } from 'react-icons/fa'
import { ClipLoader } from 'react-spinners'

function Profile() {
  const { userData } = useSelector(state => state.user)
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const fileRef = useRef(null)
  const csvRef = useRef(null)
  const [csvDragging, setCsvDragging] = useState(false)
  const [csvMsg, setCsvMsg] = useState('')

  // Edit profile
  const [editMode, setEditMode] = useState(false)
  const [fullName, setFullName] = useState(userData?.fullName || '')
  const [mobile, setMobile] = useState(userData?.mobile || '')
  const [profileImage, setProfileImage] = useState(null)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [profileLoading, setProfileLoading] = useState(false)

  // Change password
  const [showPasswordSection, setShowPasswordSection] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordLoading, setPasswordLoading] = useState(false)
  const [passwordMsg, setPasswordMsg] = useState({ text: '', error: false })

  // Contacts
  const [showContacts, setShowContacts] = useState(false)
  const [contacts, setContacts] = useState(userData?.contacts || [])
  const [newContactName, setNewContactName] = useState('')
  const [newContactPhone, setNewContactPhone] = useState('')
  const [contactsLoading, setContactsLoading] = useState(false)

  // Delete account
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const [msg, setMsg] = useState({ text: '', error: false })

  const handleImageSelect = (e) => {
    const file = e.target.files[0]
    if (file) {
      setProfileImage(file)
      setPreviewUrl(URL.createObjectURL(file))
    }
  }

  const handleUpdateProfile = async () => {
    setProfileLoading(true)
    try {
      const formData = new FormData()
      if (fullName !== userData.fullName) formData.append('fullName', fullName)
      if (mobile !== userData.mobile) formData.append('mobile', mobile)
      if (profileImage) formData.append('profileImage', profileImage)

      const { data } = await axios.put(`${serverUrl}/api/user/update-profile`, formData, {
        withCredentials: true,
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      dispatch(setUserData(data))
      setEditMode(false)
      setProfileImage(null)
      setPreviewUrl(null)
      setMsg({ text: 'Profile updated!', error: false })
    } catch (error) {
      setMsg({ text: error?.response?.data?.message || 'Update failed', error: true })
    }
    setProfileLoading(false)
  }

  const handleChangePassword = async () => {
    setPasswordLoading(true)
    try {
      const { data } = await axios.put(`${serverUrl}/api/user/change-password`, {
        currentPassword, newPassword
      }, { withCredentials: true })
      setPasswordMsg({ text: data.message, error: false })
      setCurrentPassword('')
      setNewPassword('')
      setTimeout(() => setShowPasswordSection(false), 1500)
    } catch (error) {
      setPasswordMsg({ text: error?.response?.data?.message || 'Failed', error: true })
    }
    setPasswordLoading(false)
  }

  const handleAddContact = () => {
    if (!newContactName.trim() || !newContactPhone.trim()) return
    setContacts(prev => [...prev, { name: newContactName.trim(), phone: newContactPhone.trim() }])
    setNewContactName('')
    setNewContactPhone('')
  }

  const handleRemoveContact = (index) => {
    setContacts(prev => prev.filter((_, i) => i !== index))
  }

  const parseCsvContacts = (text) => {
    const lines = text.split(/\r?\n/).filter(l => l.trim())
    if (lines.length < 2) return []

    const header = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/['"]/g, ''))

    // Support Google Contacts CSV format and generic name,phone CSVs
    const nameIdx = header.findIndex(h =>
      h === 'name' || h === 'first name' || h === 'given name' || h === 'fullname' || h === 'full name'
    )
    const lastNameIdx = header.findIndex(h =>
      h === 'last name' || h === 'family name' || h === 'surname'
    )
    const phoneIdx = header.findIndex(h =>
      h.includes('phone') || h.includes('mobile') || h.includes('number') || h === 'tel'
    )

    if (nameIdx === -1 || phoneIdx === -1) return null // indicates parse error

    const parsed = []
    for (let i = 1; i < lines.length; i++) {
      // Handle quoted CSV fields
      const cols = lines[i].match(/(".*?"|[^",]+)(?=\s*,|\s*$)/g)
      if (!cols) continue
      const clean = cols.map(c => c.trim().replace(/^"|"$/g, ''))

      let name = clean[nameIdx] || ''
      if (lastNameIdx !== -1 && clean[lastNameIdx]) {
        name = `${name} ${clean[lastNameIdx]}`.trim()
      }
      const phone = clean[phoneIdx] || ''

      if (name && phone) {
        // Normalize phone: strip spaces, dashes
        const normalizedPhone = phone.replace(/[\s\-()]/g, '')
        parsed.push({ name, phone: normalizedPhone })
      }
    }
    return parsed
  }

  const handleCsvFile = (file) => {
    if (!file || !file.name.endsWith('.csv')) {
      setCsvMsg('Please upload a .csv file')
      return
    }
    const reader = new FileReader()
    reader.onload = (e) => {
      const parsed = parseCsvContacts(e.target.result)
      if (parsed === null) {
        setCsvMsg('Could not find "Name" and "Phone" columns. Make sure your CSV has those headers.')
        return
      }
      if (parsed.length === 0) {
        setCsvMsg('No contacts found in the file.')
        return
      }
      // Merge with existing, avoiding duplicate phones
      const existingPhones = new Set(contacts.map(c => c.phone))
      const newContacts = parsed.filter(c => !existingPhones.has(c.phone))
      setContacts(prev => [...prev, ...newContacts])
      setCsvMsg(`Added ${newContacts.length} new contacts (${parsed.length - newContacts.length} duplicates skipped)`)
    }
    reader.readAsText(file)
  }

  const handleCsvDrop = (e) => {
    e.preventDefault()
    setCsvDragging(false)
    const file = e.dataTransfer.files[0]
    handleCsvFile(file)
  }

  const handleSaveContacts = async () => {
    setContactsLoading(true)
    try {
      const { data } = await axios.put(`${serverUrl}/api/user/contacts`, { contacts }, { withCredentials: true })
      dispatch(setUserData(data))
      setMsg({ text: 'Contacts saved!', error: false })
    } catch (error) {
      setMsg({ text: error?.response?.data?.message || 'Save failed', error: true })
    }
    setContactsLoading(false)
  }

  const handleLogout = async () => {
    try {
      await axios.get(`${serverUrl}/api/auth/signout`, { withCredentials: true })
      dispatch(clearUserData())
      if (window.localStorage) {
        window.localStorage.removeItem('persist:user');
      }
      navigate('/signin');
    } catch (e) { console.log(e) }
  }

  const handleDeleteAccount = async () => {
    try {
      await axios.delete(`${serverUrl}/api/user/delete-account`, { withCredentials: true })
      dispatch(clearUserData())
      if (window.localStorage) {
        window.localStorage.removeItem('persist:user');
      }
      navigate('/signin');
    } catch (e) { console.log(e) }
  }

  const avatarUrl = previewUrl || userData?.profileImage

  return (
    <div className="min-h-screen w-full bg-[#0b0b0a] text-white">
      <Nav />
      <main className="pt-[84px] pb-20 px-4 max-w-2xl mx-auto flex flex-col gap-6">

        {/* Profile Header */}
        <div className="flex flex-col items-center gap-4 py-6">
          <div className="relative group">
            <div className="w-28 h-28 rounded-full overflow-hidden bg-[#1c1c1c] border-4 border-[#ff2e2e]/30 shadow-xl flex items-center justify-center">
              {avatarUrl ? (
                <img src={avatarUrl} alt="avatar" className="w-full h-full object-cover" />
              ) : (
                <span className="text-5xl font-bold text-[#ff2e2e]">{userData?.fullName?.charAt(0)}</span>
              )}
            </div>
            {editMode && (
              <button
                onClick={() => fileRef.current?.click()}
                className="absolute bottom-0 right-0 w-9 h-9 rounded-full bg-[#ff2e2e] flex items-center justify-center shadow-lg hover:bg-[#cc2424] transition"
              >
                <FaCamera size={14} />
              </button>
            )}
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleImageSelect} />
          </div>
          <div className="text-center">
            <h1 className="text-2xl font-bold">{userData?.fullName}</h1>
            <p className="text-sm text-gray-400">{userData?.email}</p>
            <span className="mt-1 inline-block px-3 py-0.5 rounded-full bg-[#ff2e2e]/15 text-[#ff2e2e] text-xs font-semibold uppercase tracking-wide">
              {userData?.role}
            </span>
          </div>
        </div>

        {/* Status message */}
        {msg.text && (
          <div className={`text-center text-sm font-medium py-2 rounded-xl ${msg.error ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
            {msg.text}
          </div>
        )}

        {/* Edit Profile Section */}
        <section className="rounded-2xl bg-[#161616] border border-[#252525] overflow-hidden">
          <button
            className="w-full flex items-center justify-between p-4 hover:bg-[#1c1c1c] transition"
            onClick={() => { setEditMode(!editMode); setMsg({ text: '', error: false }) }}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-[#ff2e2e]/10 flex items-center justify-center">
                <FaUser className="text-[#ff2e2e]" />
              </div>
              <span className="font-semibold">Edit Profile</span>
            </div>
            <FaChevronRight className={`text-gray-500 transition-transform ${editMode ? 'rotate-90' : ''}`} />
          </button>

          {editMode && (
            <div className="px-4 pb-4 flex flex-col gap-4 border-t border-[#252525] pt-4">
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Full Name</label>
                <div className="flex items-center gap-2 bg-[#1c1c1c] rounded-xl px-3 py-2.5 border border-[#2d2d2d]">
                  <FaUser className="text-gray-500" size={14} />
                  <input
                    type="text" value={fullName} onChange={(e) => setFullName(e.target.value)}
                    className="flex-1 bg-transparent outline-none text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Mobile</label>
                <div className="flex items-center gap-2 bg-[#1c1c1c] rounded-xl px-3 py-2.5 border border-[#2d2d2d]">
                  <FaPhone className="text-gray-500" size={14} />
                  <input
                    type="text" value={mobile} onChange={(e) => setMobile(e.target.value)}
                    className="flex-1 bg-transparent outline-none text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Email (read only)</label>
                <div className="flex items-center gap-2 bg-[#1c1c1c] rounded-xl px-3 py-2.5 border border-[#2d2d2d] opacity-60">
                  <FaEnvelope className="text-gray-500" size={14} />
                  <span className="text-sm">{userData?.email}</span>
                </div>
              </div>
              <button
                onClick={handleUpdateProfile}
                disabled={profileLoading}
                className="w-full py-2.5 rounded-xl bg-[#ff2e2e] text-white font-semibold hover:bg-[#cc2424] transition disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {profileLoading ? <ClipLoader size={18} color="#fff" /> : 'Save Changes'}
              </button>
            </div>
          )}
        </section>

        {/* Change Password */}
        <section className="rounded-2xl bg-[#161616] border border-[#252525] overflow-hidden">
          <button
            className="w-full flex items-center justify-between p-4 hover:bg-[#1c1c1c] transition"
            onClick={() => { setShowPasswordSection(!showPasswordSection); setPasswordMsg({ text: '', error: false }) }}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
                <FaLock className="text-orange-400" />
              </div>
              <span className="font-semibold">Change Password</span>
            </div>
            <FaChevronRight className={`text-gray-500 transition-transform ${showPasswordSection ? 'rotate-90' : ''}`} />
          </button>

          {showPasswordSection && (
            <div className="px-4 pb-4 flex flex-col gap-4 border-t border-[#252525] pt-4">
              {passwordMsg.text && (
                <p className={`text-sm font-medium ${passwordMsg.error ? 'text-red-400' : 'text-green-400'}`}>
                  {passwordMsg.text}
                </p>
              )}
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Current Password</label>
                <input
                  type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)}
                  className="w-full bg-[#1c1c1c] rounded-xl px-3 py-2.5 border border-[#2d2d2d] outline-none text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">New Password</label>
                <input
                  type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full bg-[#1c1c1c] rounded-xl px-3 py-2.5 border border-[#2d2d2d] outline-none text-sm"
                />
              </div>
              <button
                onClick={handleChangePassword}
                disabled={passwordLoading || !currentPassword || !newPassword}
                className="w-full py-2.5 rounded-xl bg-orange-500 text-white font-semibold hover:bg-orange-600 transition disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {passwordLoading ? <ClipLoader size={18} color="#fff" /> : 'Update Password'}
              </button>
            </div>
          )}
        </section>

        {/* Contacts Section */}
        <section className="rounded-2xl bg-[#161616] border border-[#252525] overflow-hidden">
          <button
            className="w-full flex items-center justify-between p-4 hover:bg-[#1c1c1c] transition"
            onClick={() => setShowContacts(!showContacts)}
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
                <FaAddressBook className="text-blue-400" />
              </div>
              <div className="text-left">
                <span className="font-semibold block">My Contacts</span>
                <span className="text-xs text-gray-500">{contacts.length} contacts · Get recommendations from friends</span>
              </div>
            </div>
            <FaChevronRight className={`text-gray-500 transition-transform ${showContacts ? 'rotate-90' : ''}`} />
          </button>

          {showContacts && (
            <div className="px-4 pb-4 flex flex-col gap-4 border-t border-[#252525] pt-4">

              {/* CSV Upload Zone */}
              <div
                onDragOver={(e) => { e.preventDefault(); setCsvDragging(true) }}
                onDragLeave={() => setCsvDragging(false)}
                onDrop={handleCsvDrop}
                onClick={() => csvRef.current?.click()}
                className={`flex flex-col items-center gap-2 p-5 rounded-xl border-2 border-dashed cursor-pointer transition-all duration-200 ${
                  csvDragging
                    ? 'border-blue-400 bg-blue-500/10'
                    : 'border-[#2d2d2d] bg-[#1c1c1c] hover:border-blue-400/50'
                }`}
              >
                <div className="flex items-center gap-3">
                  <FaCloudUploadAlt className="text-blue-400" size={22} />
                  <div>
                    <p className="text-sm font-semibold text-gray-200">Upload Contacts CSV</p>
                    <p className="text-xs text-gray-500">Drag & drop or click · Google Contacts CSV supported</p>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 mt-1">
                  <FaFileCsv className="text-green-400" size={12} />
                  <span className="text-[11px] text-gray-500">Expects columns: Name, Phone (or First Name, Phone 1)</span>
                </div>
              </div>
              <input
                ref={csvRef} type="file" accept=".csv"
                className="hidden"
                onChange={(e) => { handleCsvFile(e.target.files[0]); e.target.value = '' }}
              />
              {csvMsg && (
                <p className={`text-xs font-medium ${csvMsg.includes('Could not') || csvMsg.includes('Please') ? 'text-red-400' : 'text-green-400'}`}>
                  {csvMsg}
                </p>
              )}

              {/* Contact list */}
              {contacts.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs text-gray-400 font-medium">{contacts.length} contacts</p>
                    <button
                      onClick={() => { setContacts([]); setCsvMsg('') }}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Clear all
                    </button>
                  </div>
                  <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto">
                    {contacts.map((c, i) => (
                      <div key={i} className="flex items-center justify-between px-3 py-2 bg-[#1c1c1c] rounded-xl border border-[#2d2d2d]">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-blue-500/15 flex items-center justify-center text-xs font-bold text-blue-400">
                            {c.name.charAt(0)}
                          </div>
                          <div>
                            <p className="text-sm font-medium">{c.name}</p>
                            <p className="text-xs text-gray-500">{c.phone}</p>
                          </div>
                        </div>
                        <button onClick={() => handleRemoveContact(i)} className="text-red-400 hover:text-red-300 p-1">
                          <FaTrash size={12} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add contact form */}
              <div className="flex flex-col gap-2">
                <p className="text-xs text-gray-400 font-medium">Add a contact</p>
                <div className="flex gap-2">
                  <input
                    type="text" placeholder="Name" value={newContactName}
                    onChange={(e) => setNewContactName(e.target.value)}
                    className="flex-1 bg-[#1c1c1c] rounded-xl px-3 py-2 border border-[#2d2d2d] outline-none text-sm"
                  />
                  <input
                    type="text" placeholder="Phone" value={newContactPhone}
                    onChange={(e) => setNewContactPhone(e.target.value)}
                    className="flex-1 bg-[#1c1c1c] rounded-xl px-3 py-2 border border-[#2d2d2d] outline-none text-sm"
                  />
                  <button
                    onClick={handleAddContact}
                    className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center text-white hover:bg-blue-600 transition shrink-0"
                  >
                    <FaPlus size={14} />
                  </button>
                </div>
              </div>

              <button
                onClick={handleSaveContacts}
                disabled={contactsLoading}
                className="w-full py-2.5 rounded-xl bg-blue-500 text-white font-semibold hover:bg-blue-600 transition disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {contactsLoading ? <ClipLoader size={18} color="#fff" /> : 'Save Contacts'}
              </button>
            </div>
          )}
        </section>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 p-4 rounded-2xl bg-[#161616] border border-[#252525] hover:bg-[#1c1c1c] transition"
        >
          <div className="w-10 h-10 rounded-xl bg-gray-500/10 flex items-center justify-center">
            <FaSignOutAlt className="text-gray-400" />
          </div>
          <span className="font-semibold text-gray-300">Log Out</span>
        </button>

        {/* Delete Account */}
        <section className="rounded-2xl bg-[#161616] border border-red-900/30 overflow-hidden">
          {!showDeleteConfirm ? (
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="w-full flex items-center gap-3 p-4 hover:bg-red-500/5 transition"
            >
              <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center">
                <FaTrash className="text-red-400" size={14} />
              </div>
              <span className="font-semibold text-red-400">Delete Account</span>
            </button>
          ) : (
            <div className="p-4 flex flex-col gap-3">
              <p className="text-sm text-red-400 font-medium">Are you sure? This cannot be undone.</p>
              <div className="flex gap-3">
                <button
                  onClick={() => setShowDeleteConfirm(false)}
                  className="flex-1 py-2 rounded-xl bg-[#252525] text-gray-300 font-semibold hover:bg-[#2d2d2d] transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteAccount}
                  className="flex-1 py-2 rounded-xl bg-red-600 text-white font-semibold hover:bg-red-700 transition"
                >
                  Delete
                </button>
              </div>
            </div>
          )}
        </section>

      </main>
    </div>
  )
}

export default Profile
