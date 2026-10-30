import reducer from '../store/sensorsSlice';
test('initial state', () => expect(reducer(undefined, { type: 'x' }).items).toEqual([]));
