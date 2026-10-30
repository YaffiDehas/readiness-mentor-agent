import axios from 'axios';
export const apiClient = axios.create({ baseURL: process.env.API_URL });
apiClient.interceptors.request.use(cfg => { cfg.headers.Authorization = `Bearer ${getToken()}`; return cfg; });
export const getSensors = () => apiClient.get('/sensors');
export const getReadings = (id: string) => apiClient.get(`/sensors/${id}/readings`);
