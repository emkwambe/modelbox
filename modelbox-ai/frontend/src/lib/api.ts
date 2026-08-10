/**
 * Typed API client for the ModelBox AI backend.
 *
 * Thin axios wrapper exposing the synthesis + transform endpoints with the
 * shared DTO types from `@/types/schema`.
 */

import axios from 'axios';

import { useAuthStore } from '@/store/authStore';
import type {
  Assignment,
  GradeResult,
  SocraticStep,
  TrainerGraph,
} from '@/types/trainer';
import type {
  ConnectionCreateRequest,
  ConnectionInfo,
  ContractExportResponse,
  ContractFormat,
  DiffRequest,
  DiffResponse,
  Entity,
  ExportFormat,
  ExportResponse,
  IntrospectRequest,
  JobCreatedResponse,
  JobStatus,
  ModelInfo,
  Relationship,
  SemanticEngine,
  SemanticExportResponse,
  SyntheticSeedRequest,
  SyntheticSeedResponse,
  SynthesizeRequest,
  SynthesizeResponse,
  TransformParadigmRequest,
  TransformParadigmResponse,
  ValidationReport,
  WorkspaceInfo,
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

// --- ModelBox Trainer (Pillar 3) ---
export async function listAssignments(): Promise<Assignment[]> {
  const { data } = await apiClient.get<Assignment[]>('/trainer/assignments');
  return data;
}

export async function getAssignment(id: string): Promise<Assignment> {
  const { data } = await apiClient.get<Assignment>(
    `/trainer/assignments/${id}`,
  );
  return data;
}

export async function submitSocraticStep(payload: {
  assignment_id: string;
  conversation_history: { role: string; content: string }[];
  current_graph: TrainerGraph;
}): Promise<SocraticStep> {
  const { data } = await apiClient.post<SocraticStep>(
    '/trainer/socratic/step',
    payload,
  );
  return data;
}

export async function gradeSubmission(payload: {
  assignment_id: string;
  submitted_graph: TrainerGraph;
}): Promise<GradeResult> {
  const { data } = await apiClient.post<GradeResult>('/trainer/grade', payload);
  return data;
}

// --- Workspaces & model management (RBAC) ---
export async function listWorkspaces(): Promise<WorkspaceInfo[]> {
  const { data } = await apiClient.get<WorkspaceInfo[]>('/workspaces');
  return data;
}

export async function deleteModel(modelId: string): Promise<void> {
  await apiClient.delete(`/model/${modelId}`);
}

export async function updateModel(
  modelId: string,
  payload: { title?: string; target_dialect?: string },
): Promise<ModelInfo> {
  const { data } = await apiClient.patch<ModelInfo>(
    `/model/${modelId}`,
    payload,
  );
  return data;
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

// --- Async synthesis jobs (FR-1.1) ---
export async function enqueueSynthesis(
  request: SynthesizeRequest,
): Promise<JobCreatedResponse> {
  const { data } = await apiClient.post<JobCreatedResponse>(
    '/jobs/synthesize',
    request,
  );
  return data;
}

export async function getJob(jobId: string): Promise<JobStatus> {
  const { data } = await apiClient.get<JobStatus>(`/jobs/${jobId}`);
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

export async function saveGraph(
  modelId: string,
  payload: { entities: Entity[]; relationships: Relationship[] },
): Promise<ValidationReport> {
  const { data } = await apiClient.put<ValidationReport>(
    `/model/${modelId}/graph`,
    payload,
  );
  return data;
}

// --- Connectors & brownfield introspection (FR-2.1) ---
export async function listConnections(): Promise<ConnectionInfo[]> {
  const { data } = await apiClient.get<ConnectionInfo[]>('/connectors');
  return data;
}

export async function createConnection(
  payload: ConnectionCreateRequest,
): Promise<ConnectionInfo> {
  const { data } = await apiClient.post<ConnectionInfo>('/connectors', payload);
  return data;
}

export async function introspectConnection(
  payload: IntrospectRequest,
): Promise<SynthesizeResponse> {
  const { data } = await apiClient.post<SynthesizeResponse>(
    '/connectors/introspect',
    payload,
  );
  return data;
}

// --- Schema diffing (FR-2.2) ---
export async function diffModels(payload: DiffRequest): Promise<DiffResponse> {
  const { data } = await apiClient.post<DiffResponse>('/model/diff', payload);
  return data;
}

// --- Synthetic seed data (FR-2.4) ---
export async function exportSyntheticData(
  modelId: string,
  payload: SyntheticSeedRequest,
): Promise<SyntheticSeedResponse> {
  const { data } = await apiClient.post<SyntheticSeedResponse>(
    `/model/${modelId}/export/synthetic-data`,
    payload,
  );
  return data;
}

// --- Data contracts & semantic layers (FR-2.3, Phase 3) ---
export async function exportContract(
  modelId: string,
  format: ContractFormat,
): Promise<ContractExportResponse> {
  const { data } = await apiClient.get<ContractExportResponse>(
    `/model/${modelId}/export/contract`,
    { params: { format } },
  );
  return data;
}

export async function exportSemantic(
  modelId: string,
  engine: SemanticEngine,
): Promise<SemanticExportResponse> {
  const { data } = await apiClient.get<SemanticExportResponse>(
    `/model/${modelId}/export/semantic`,
    { params: { engine } },
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
