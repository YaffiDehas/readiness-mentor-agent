import { Router } from 'express';
export const products = Router().get('/products', (_req, res) => res.json([]));
