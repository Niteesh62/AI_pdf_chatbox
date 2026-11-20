import axios from "axios";

const API = axios.create({
    baseURL:
        // "https://ai-pdf-chatbox-mxdw.onrender.com/api/"
        "http://localhost:8000/api/",
});

export default API;
