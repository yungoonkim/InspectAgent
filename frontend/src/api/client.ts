/**
 * VisionInsight API Client
 * Manages base URL, credentials, origin, and session CSRF token
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

class ApiClient {
  private baseUrl: string;
  private csrfToken: string | null = null;
  private sessionExpiresAt: number = 0;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  getBaseUrl(): string {
    return this.baseUrl;
  }

  setCsrfToken(token: string, ttlSeconds: number) {
    this.csrfToken = token;
    this.sessionExpiresAt = Date.now() + (ttlSeconds * 1000);
  }

  getCsrfToken(): string | null {
    if (this.csrfToken && Date.now() > this.sessionExpiresAt) {
      this.csrfToken = null;
    }
    return this.csrfToken;
  }

  clearSession() {
    this.csrfToken = null;
    this.sessionExpiresAt = 0;
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string> || {}),
    };

    // Include credentials (cookies) by default for security & session
    const response = await fetch(url, {
      ...options,
      headers,
      credentials: 'include',
    });

    if (!response.ok) {
      let errorBody: any = null;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = { message: await response.text().catch(() => 'Unknown error') };
      }
      const error = new Error(
        errorBody?.detail?.error_code || errorBody?.detail || errorBody?.message || `HTTP ${response.status}`
      );
      (error as any).status = response.status;
      (error as any).data = errorBody;
      throw error;
    }

    // If response is json
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return response.json() as Promise<T>;
    }
    return response as unknown as T;
  }

  async fetchBlob(endpoint: string, options: RequestInit = {}): Promise<Blob> {
    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      credentials: 'include',
    });

    if (!response.ok) {
      let errorMsg = `HTTP ${response.status}`;
      try {
        const json = await response.json();
        errorMsg = json?.detail?.error_code || json?.detail || errorMsg;
      } catch {
        // ignore
      }
      const error = new Error(errorMsg);
      (error as any).status = response.status;
      throw error;
    }

    return response.blob();
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
