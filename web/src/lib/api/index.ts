// The only entry point features use for the API (plan 4.3).
import { apiRequest } from './client';

export { ApiError } from './client';
export type { ApiPath, FieldError, Method } from './client';
export type { components, paths } from './schema';
export { reportClientError } from './clientErrors';

export const api = { request: apiRequest };
