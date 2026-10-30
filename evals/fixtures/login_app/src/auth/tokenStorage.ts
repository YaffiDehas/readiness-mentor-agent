import AsyncStorage from '@react-native-async-storage/async-storage';
export const saveToken = (t: string) => AsyncStorage.setItem('accessToken', t);
export const getToken = () => AsyncStorage.getItem('accessToken');
