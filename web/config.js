// Set this to the exact HTTPS URL returned by the backend host after deployment.
export const API_BASE_URL = location.hostname === "localhost" || location.hostname === "127.0.0.1"
  ? location.origin
  : "";

export const firebaseConfig = {
  apiKey: "AIzaSyDq2LUe4BjH2Yr15M7NQnX36u5K0a-KtGw",
  authDomain: "jobs-tool.firebaseapp.com",
  projectId: "jobs-tool",
  storageBucket: "jobs-tool.firebasestorage.app",
  messagingSenderId: "294964555520",
  appId: "1:294964555520:web:bfac8030f53f5863808de5",
  measurementId: "G-GJXLTP0X3G"
};
