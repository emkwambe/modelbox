/**
 * Typed API client for the ModelBox AI backend.
 *
 * Thin axios wrapper exposing the synthesis + transform endpoints with the
 * shared DTO types from `@/types/schema`.
 */

import axios from 'axios';

import type {
  ExportFormat,
  ExportResponse,
  SynthesizeRequest,
  SynthesizeResponse,
  TransformParadigmRequest,
  TransformParadigmResponse,
  ValidationReport,
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

export async function exportArtifact(
  modelId: string,
  format: ExportFormat,
  dialect = 'snowflake',
): Promise<ExportResponse> {
  const { data } = await apiClient.get<ExportResponse>(
    `/model/${modelId}/export`,
    { params: { format, dialect } },
  );
  return data;
}

export async function validateModel(
  modelId: string,
): Promise<ValidationReport> {
  const { data } = await apiClient.post<ValidationReport>(
    `/model/${modelId}/validate`,
  );
  return data;
}
