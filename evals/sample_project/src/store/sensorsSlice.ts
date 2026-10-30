import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { getSensors } from '../services/apiClient';
export const fetchSensors = createAsyncThunk('sensors/fetch', async () => (await getSensors()).data);
export default createSlice({ name: 'sensors', initialState: { items: [] as any[] }, reducers: {},
  extraReducers: b => b.addCase(fetchSensors.fulfilled, (s, a) => { s.items = a.payload; }) }).reducer;
