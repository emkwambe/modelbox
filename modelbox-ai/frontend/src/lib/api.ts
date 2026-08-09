/**
 * Typed API client for the ModelBox AI backend.
 *
 * Thin axios wrapper exposing the synthesis + transform endpoints with the
 * shared DTO types from `@/types/schema`.
 */

import axios from 'axios';

import type {
  SynthesizeRequest,
  SynthesizeResponse,
  TransformParadigmRequest,
  TransformParadigmResponse,
} from '@/types/schema';

const baseURL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: `${baseURL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120_000,
});

export async function synthesizeModel(
  request: SynthesizeRequest,
): Promise<SynthesizeResponse> {
  const { data } = await apiClient.post<SynthesizeResponse>(
    '/model/synthesize',
    request,
  );
  return data;
}

export async function getModel(
  modelId: string,
): Promise<SynthesizeResponse> {
  const { data } = await apiClient.get<SynthesizeResponse>(`/model/${modelId}`);
  return data;
}

export async function transformParadigm(
  modelId: string,
  request: TransformParadigmRequest,
): Promise<TransformParadigmResponse> {
  const { data } = await apiClient.post<TransformParadigmResponse>(
    `/model/${modelId}/transform-paradigm`,
    request,
  );
  return data;
}
