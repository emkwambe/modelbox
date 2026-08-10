/**
 * Typed API client for the ModelBox AI backend.
 *
 * Thin axios wrapper exposing the synthesis + transform endpoints with the
 * shared DTO types from `@/types/schema`.
 */

import axios from 'axios';

import { useAuthStore } from '@/store/authStore';
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

// Attach the bearer token to every request when authenticated.
apiClient.interceptors.request.use((config) => {
  const { token } = useAuthStore.getState();
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

// On 401, clear the session and prompt for sign-in.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      const auth = useAuthStore.getState();
      auth.logout();
      auth.openModal();
    }
    return Promise.reject(error);
  },
);

// --- Auth ---
export async function login(email: string, password: string): Promise<string> {
  const form = new URLSearchParams();
  form.set('username', email);
  form.set('password', password);
  const { data } = await apiClient.post<{ access_token: string }>(
    '/auth/token',
    form,
    { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
  );
  return data.access_token;
}

export async function fetchMe(): Promise<{ email: string }> {
  const { data } = await apiClient.get<{ email: string }>('/auth/me');
  return data;
}

export async function register(
  email: string,
  password: string,
  fullName?: string,
): Promise<string> {
  const { data } = await apiClient.post<{ access_token: string }>(
    '/auth/register',
    { email, password, full_name: fullName ?? null },
  );
  return data.access_token;
}

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

/** Fetch a zipped artifact bundle and trigger a browser download. */
export async function downloadExportZip(
  modelId: string,
  format: ExportFormat,
  dialect = 'snowflake',
): Promise<void> {
  const response = await apiClient.get(`/model/${modelId}/export/zip`, {
    params: { format, dialect },
    responseType: 'blob',
  });
  const blob = new Blob([response.data as BlobPart], {
    type: 'application/zip',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `modelbox_${format}_${modelId}.zip`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
