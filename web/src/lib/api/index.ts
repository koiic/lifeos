// The only entry point features use for the API (plan 4.3).
import { apiRequest } from './client';

export { ApiError } from './client';
export type { ApiPath, FieldError, Method } from './client';
export type { components, paths } from './schema';
export { reportClientError } from './clientErrors';
export * from './dailyLogs';
export * from './symptoms';
export * from './health';
export * from './today';

export const api = { request: apiRequest };
