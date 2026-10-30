import axios from "axios";
// All HTTP calls go through this instance (base URL and error mapping live here).
export const http = axios.create({ baseURL: import.meta.env.VITE_API_URL });
