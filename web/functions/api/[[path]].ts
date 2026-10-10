import { handleProxy, type ProxyEnv } from './proxy';

interface EventContext<Env, P extends string, Data> {
  request: Request;
  functionPath: string;
  waitUntil: (promise: Promise<unknown>) => void;
  next: (input?: Request | string, init?: RequestInit) => Promise<Response>;
  env: Env;
  params: Record<P, string | string[]>;
  data: Data;
}

export const onRequest = async (
  context: EventContext<ProxyEnv, 'path', unknown>,
): Promise<Response> => {
  return handleProxy(context.request, context.env);
};
