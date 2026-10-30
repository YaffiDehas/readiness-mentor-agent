import { http } from "./http";
export type Vehicle = { id: string; plate: string; enteredAt: string };
// Vehicles list: the only service module so far; the parking facilities service is not written yet.
export const fetchVehicles = (q: string) => http.get<Vehicle[]>("/vehicles", { params: { q } }).then((r) => r.data);
