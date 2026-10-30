import axios from 'axios';
import { getToken } from '../auth/tokenStorage';
export const apiClient = axios.create({ baseURL: process.env.API_URL });
apiClient.interceptors.request.use(async cfg => { cfg.headers.Authorization = `Bearer ${await getToken()}`; return cfg; });
