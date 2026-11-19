import axios from "axios";

const API = axios.create({
    baseURL: "https://ai-pdf-chatbox-mxdw.onrender.com/api/",
});

export default API;
