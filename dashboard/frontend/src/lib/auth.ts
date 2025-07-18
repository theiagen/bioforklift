/**
 * Authentication utilities for the Bioforklift Dashboard
 */

export interface User {
  email: string;
  name: string;
  picture: string;
  authenticated: boolean;
}

export interface AuthStatus {
  authenticated: boolean;
  user?: User;
  project?: {
    project_id: string;
    dataset_id: string;
  };
  login_url?: string;
}

/**
 * Check current authentication status
 */
export async function checkAuthStatus(): Promise<AuthStatus> {
  try {
    const response = await fetch('/auth/status', {
      credentials: 'include'
    });
    
    if (response.ok) {
      return await response.json();
    }
    
    return { authenticated: false, login_url: '/auth/login' };
  } catch (error) {
    console.error('Error checking auth status:', error);
    return { authenticated: false, login_url: '/auth/login' };
  }
}

/**
 * Get current user information (requires authentication)
 */
export async function getCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch('/auth/user', {
      credentials: 'include'
    });
    
    if (response.ok) {
      return await response.json();
    }
    
    return null;
  } catch (error) {
    console.error('Error getting current user:', error);
    return null;
  }
}

/**
 * Redirect to login page
 */
export function redirectToLogin(): void {
  window.location.href = '/auth/login';
}

/**
 * Logout user
 */
export function logout(): void {
  window.location.href = '/auth/logout';
}

/**
 * Handle authentication errors (401/403)
 */
export function handleAuthError(status: number): void {
  if (status === 401 || status === 403) {
    redirectToLogin();
  }
}