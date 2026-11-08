import {
  HealthResponse,
  LoginRequest,
  ProviderHealth,
  RegisterRequest,
  SystemStatus,
  TaskApproveRequest,
  TaskCancelRequest,
  TaskCreate,
  TaskDetail,
  TaskPlanRead,
  TaskRead,
  UserRead,
} from "@/types/backend";

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    let data: unknown;
    try {
      data = await res.json();
      if (data && typeof data === "object" && "detail" in data && typeof (data as { detail: unknown }).detail === "string") {
        detail = (data as { detail: string }).detail;
      }
    } catch {
      // Not JSON
    }
    throw new ApiError(detail, res.status, data);
  }

  return res.json();
}

export const api = {
  auth: {
    login: async (credentials: LoginRequest): Promise<{ user_id: string; email: string; role: string }> => {
      return fetchJson("/api/auth/login", {
        method: "POST",
        body: JSON.stringify(credentials),
      });
    },
    register: async (credentials: RegisterRequest): Promise<{ user_id: string; email: string; role: string }> => {
      return fetchJson("/api/auth/register", {
        method: "POST",
        body: JSON.stringify(credentials),
      });
    },
    logout: async (): Promise<{ success: boolean; message: string }> => {
      return fetchJson("/api/auth/logout", {
        method: "POST",
      });
    },
    me: async (): Promise<UserRead> => {
      return fetchJson("/api/auth/me", {
        method: "GET",
      });
    },
  },

  tasks: {
    list: async (): Promise<TaskRead[]> => {
      return fetchJson("/api/tasks", {
        method: "GET",
      });
    },
    create: async (payload: TaskCreate): Promise<TaskDetail> => {
      return fetchJson("/api/tasks", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    get: async (taskId: string): Promise<TaskDetail> => {
      return fetchJson(`/api/tasks/${encodeURIComponent(taskId)}`, {
        method: "GET",
      });
    },
    getPlan: async (taskId: string): Promise<TaskPlanRead> => {
      return fetchJson(`/api/tasks/${encodeURIComponent(taskId)}/plan`, {
        method: "GET",
      });
    },
    regeneratePlan: async (taskId: string): Promise<TaskPlanRead> => {
      return fetchJson(`/api/tasks/${encodeURIComponent(taskId)}/plan`, {
        method: "POST",
      });
    },
    approve: async (taskId: string, payload: TaskApproveRequest): Promise<TaskDetail> => {
      return fetchJson(`/api/tasks/${encodeURIComponent(taskId)}/approve`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    cancel: async (taskId: string, payload?: TaskCancelRequest): Promise<TaskDetail> => {
      return fetchJson(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
        method: "POST",
        body: JSON.stringify(payload || { reason: "Cancelled by user" }),
      });
    },
  },

  system: {
    health: async (): Promise<HealthResponse> => {
      return fetchJson("/api/health", {
        method: "GET",
      });
    },
    status: async (): Promise<SystemStatus> => {
      return fetchJson("/api/system/status", {
        method: "GET",
      });
    },
    inference: async (): Promise<ProviderHealth> => {
      return fetchJson("/api/system/inference", {
        method: "GET",
      });
    },
  },
};
