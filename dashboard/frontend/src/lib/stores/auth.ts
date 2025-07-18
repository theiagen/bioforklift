/**
 * Authentication store for managing user state across the application
 */
import { writable, derived } from 'svelte/store';
import type { User, AuthStatus } from '$lib/auth';
import { checkAuthStatus, getCurrentUser } from '$lib/auth';

// Auth status store
export const authStatus = writable<AuthStatus>({ authenticated: false });

// User store
export const user = writable<User | null>(null);

// Loading state
export const authLoading = writable<boolean>(true);

// Derived store for authentication state
export const isAuthenticated = derived(
  authStatus,
  ($authStatus) => $authStatus.authenticated
);

// Derived store for project info
export const projectInfo = derived(
  authStatus,
  ($authStatus) => $authStatus.project
);

/**
 * Initialize authentication state
 */
export async function initAuth(): Promise<void> {
  try {
    authLoading.set(true);
    
    // Check authentication status
    const status = await checkAuthStatus();
    authStatus.set(status);
    
    // If authenticated, get user details
    if (status.authenticated) {
      const currentUser = await getCurrentUser();
      user.set(currentUser);
    } else {
      user.set(null);
    }
    
  } catch (error) {
    console.error('Error initializing auth:', error);
    authStatus.set({ authenticated: false });
    user.set(null);
  } finally {
    authLoading.set(false);
  }
}

/**
 * Clear authentication state
 */
export function clearAuth(): void {
  authStatus.set({ authenticated: false });
  user.set(null);
  authLoading.set(false);
}