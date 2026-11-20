import axios from "axios";

console.log("API_BASE_URL:", import.meta.env.API_BASE_URL, "VITE_API_BASE_URL:", import.meta.env.VITE_API_BASE_URL);
const API = axios.create({
    baseURL:
        import.meta.env.API_BASE_URL ||
        import.meta.env.VITE_API_BASE_URL ||
        "http://127.0.0.1:8000/api/",
});

export default API;
