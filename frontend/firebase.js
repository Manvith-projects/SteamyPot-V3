// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCnZQl81hqZOCYAWeWr5xD2mrFlddpF800",
  authDomain: "steamy-pot.firebaseapp.com",
  projectId: "steamy-pot",
  storageBucket: "steamy-pot.firebasestorage.app",
  messagingSenderId: "211076992266",
  appId: "1:211076992266:web:d3d97ebe39812e4b0dfef3",
  measurementId: "G-8SCT1TL1DW"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth=getAuth(app)
export {app,auth}