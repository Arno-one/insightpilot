"use client";

export type ApiResponse<T> = {
  code: number;
  msg: string;
  data: T;
  total?: number | null;
};

export type CurrentUser = {
  tenant_id: string;
  user_id: string;
  username: string;
  real_name: string;
  role_codes: string[];
  permission_codes: string[];
};

export type LoginData = {
  token: string;
  token_type: string;
  user: CurrentUser;
};

const TOKEN_KEY = "insightpilot_token";
const USER_KEY = "insightpilot_user";

export function apiBaseUrl() {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8088";
}

export function saveSession(data: LoginData) {
  localStorage.setItem(TOKEN_KEY, data.token);
  localStorage.setItem(USER_KEY, JSON.stringify(data.user));
}

export function saveStoredUser(user: CurrentUser) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getToken() {
  if (typeof window === "undefined") {
    return null;
  }
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): CurrentUser | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    return JSON.parse(raw) as CurrentUser;
  } catch {
    clearSession();
    return null;
  }
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function hasAnyPermission(user: CurrentUser | null, permissions: string[]) {
  if (!user) {
    return false;
  }
  return permissions.some((permission) => user.permission_codes.includes(permission));
}

export function getDefaultRoute(user: CurrentUser | null) {
  if (hasAnyPermission(user, ["crm:customer:read:self"])) {
    return "/dashboard";
  }
  if (hasAnyPermission(user, ["system:rbac:manage", "system:user_role:manage"])) {
    return "/system/access-control";
  }
  return "/login";
}

function shouldUseJsonContentType(body: BodyInit | null | undefined) {
  if (!body) {
    return false;
  }
  if (typeof FormData !== "undefined" && body instanceof FormData) {
    return false;
  }
  return true;
}

async function requestWithAuth(path: string, init: RequestInit = {}) {
  const token = getToken();
  const headers = new Headers(init.headers);
  // 中文注释：只有普通 JSON 请求才补 Content-Type，FormData 要交给浏览器自动追加 boundary。
  if (!headers.has("Content-Type") && shouldUseJsonContentType(init.body)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${apiBaseUrl()}${path}`, {
    ...init,
    headers,
    cache: "no-store"
  });

  if (response.status === 401) {
    clearSession();
  }

  return response;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}) {
  const response = await requestWithAuth(path, init);

  const body = (await response.json().catch(() => null)) as ApiResponse<T> | null;
  if (!response.ok || !body || body.code !== 200) {
    throw new Error(body?.msg || `请求失败：${response.status}`);
  }
  return body;
}

export async function apiFetchBlob(path: string, init: RequestInit = {}) {
  const response = await requestWithAuth(path, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiResponse<null> | null;
    throw new Error(body?.msg || `请求失败：${response.status}`);
  }

  const fileName = response.headers
    .get("Content-Disposition")
    ?.match(/filename="?([^"]+)"?/)?.[1] || "download.csv";

  return {
    blob: await response.blob(),
    fileName
  };
}

export async function login(username: string, password: string) {
  return apiFetch<LoginData>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password })
  });
}

export async function fetchCurrentUser() {
  return apiFetch<CurrentUser>("/api/auth/me");
}
